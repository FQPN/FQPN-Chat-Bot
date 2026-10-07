"""The watchdog: keeps the bot honest and alive.

"Connected" in the app only means the bot started and nothing crashed. If the connection to Twitch dies quietly (after the PC
sleeps, or the internet blips) the bot can stop hearing chat while still saying Connected. Every half minute this checks that
Twitch still has the bot's chat connection registered and that its Twitch login still works. If the check fails twice in a row
the bot is restarted by itself. It never restarts the bot just because the internet is down (nothing would improve), and it
stops after a few restarts an hour and says so, instead of looping forever."""

import asyncio
import logging
import time

import aiohttp

from . import auth, botauth, notify

log = logging.getLogger("watchdog")

CHECK_EVERY = 30          # seconds between checks
BAD_LIMIT = 2             # failed checks in a row before the bot is restarted
GRACE = 45                # seconds a freshly started bot gets before it is judged
MAX_RESTARTS = 6          # automatic restarts within an hour; after that it only reports the problem
HOUR = 3600
NOTICE_EVERY = 600        # at most one pop-up every 10 minutes
CALIBRATE = 4             # checks that never see the chat registration: this token cannot list it, so the check is not used
SUBS_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"


class Watchdog:
    def __init__(self, state: dict, store, restart, sleep=asyncio.sleep, clock=time.time):
        self.state, self.store, self.restart = state, store, restart
        self.sleep, self.clock = sleep, clock
        self.bad = 0
        self.grace_until = 0.0
        self.restarts: list = []
        self.last_notice = 0.0
        self._bot = None
        self.seen_ok = False          # the chat registration was seen as enabled at least once on this connection
        self.unseen = 0
        self.subs_usable = True
        self.set("ok")

    # ---------------------------------------------------------------- what the dashboard shows
    def set(self, kind: str, detail: str = "", warn: str = "") -> None:
        prev = self.state.get("health") or {}
        since = prev.get("since") if (prev.get("state") == kind and prev.get("detail") == detail) else self.clock()
        now = self.clock()
        self.state["health"] = {"state": kind, "detail": detail, "warn": warn, "since": since, "checked": now,
                                "restarts": len([t for t in self.restarts if now - t < HOUR])}

    # ---------------------------------------------------------------- asking Twitch
    def token_for(self, bot) -> str:
        """The newest token of the account that reads chat (TwitchIO saves refreshed ones to the same files)."""
        stored = (botauth.load_token() if getattr(bot, "separate", False) else auth.load_token()) or {}
        return stored.get("access_token") or bot.bot_account.get("access_token")

    async def http_validate(self, token: str) -> str:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(auth.VALIDATE_URL, headers={"Authorization": f"OAuth {token}"}) as r:
                    return "ok" if r.status == 200 else "invalid" if r.status == 401 else "unknown"
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return "offline"

    async def http_subs(self, token: str, owner_id) -> str:
        """enabled | bad:<status> | missing | login | unavailable | unknown | offline, for the bot's chat registration."""
        headers = {"Authorization": f"Bearer {token}", "Client-Id": auth.CLIENT_ID}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(SUBS_URL, params={"type": "channel.chat.message", "first": "100"}, headers=headers) as r:
                    if r.status == 401:
                        return "login"
                    if r.status in (400, 403, 404):
                        return "unavailable"
                    if r.status != 200:
                        return "unknown"
                    data = await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return "offline"
        statuses = []
        for sub in (data or {}).get("data", []):
            cond = sub.get("condition") or {}
            if str(cond.get("broadcaster_user_id")) == str(owner_id) and (sub.get("transport") or {}).get("method") == "websocket":
                statuses.append(str(sub.get("status")))
        if not statuses:
            return "missing"
        return "enabled" if "enabled" in statuses else "bad:" + statuses[0]

    async def probe(self, bot):
        """(kind, detail): ok | unknown | bad | offline | login."""
        token = self.token_for(bot)
        v = await self.http_validate(token)
        if v == "offline":
            return "offline", "No internet connection"
        if v == "invalid":
            return "login", "Your Twitch login is no longer valid"
        if v != "ok" or not self.subs_usable:
            return "unknown", ""
        s = await self.http_subs(token, bot.owner_id)
        if s == "enabled":
            self.seen_ok, self.unseen = True, 0
            return "ok", ""
        if s == "offline":
            return "offline", "No internet connection"
        if s == "login":
            return "login", "Your Twitch login is no longer valid"
        if s.startswith("bad:"):
            return "bad", f"Twitch dropped the chat connection ({s[4:]})"
        if s == "missing" and self.seen_ok:
            return "bad", "Twitch no longer has the bot's chat connection"
        if s in ("missing", "unavailable"):      # never seen: this token may simply not be able to list it, so do not guess
            self.unseen += 1
            if self.unseen >= CALIBRATE:
                self.subs_usable = False
                log.info("Twitch does not list the chat connection for this login: that check is switched off for this session")
        return "unknown", ""

    # ---------------------------------------------------------------- deciding
    def warning(self, bot) -> str:
        return "live" if getattr(bot, "live_fail", 0) >= 3 else ""      # the live check keeps failing: timers may be waiting

    async def tick(self, woke: bool = False) -> None:
        bot, now = self.state.get("bot"), self.clock()
        if bot is None or not getattr(bot, "connected", False):
            self.bad = 0
            if now >= self.grace_until:
                self.set("idle")               # nothing to watch right now
            return
        if bot is not self._bot:               # a new connection: it starts fresh, and gets a moment to settle
            self._bot, self.seen_ok, self.unseen, self.subs_usable, self.bad = bot, False, 0, True, 0
            self.grace_until = max(self.grace_until, now + GRACE)
        if now < self.grace_until:
            if (self.state.get("health") or {}).get("state") == "reconnecting":
                self.set("ok")                 # the new connection is up: stop saying "reconnecting" (checked for real after the grace)
            return
        if woke:                               # the PC just woke up: give the bot's own reconnect a moment, then judge quickly
            await self.sleep(15)
            self.bad = max(self.bad, BAD_LIMIT - 1)
        kind, detail = await self.probe(bot)
        if kind in ("ok", "unknown"):
            self.bad = 0
            self.set("ok", warn=self.warning(bot))
        elif kind in ("offline", "login"):
            self.bad = 0
            self.set(kind, detail)
        else:
            self.bad += 1
            log.warning("Check failed (%s), %d of %d", detail, self.bad, BAD_LIMIT)
            if self.bad >= BAD_LIMIT:
                self.do_restart(detail, bot)

    def do_restart(self, detail: str, bot) -> None:
        now = self.clock()
        self.restarts = [t for t in self.restarts if now - t < HOUR]
        self.bad = 0
        if len(self.restarts) >= MAX_RESTARTS:
            self.set("problem", detail)        # it keeps failing: stop thrashing and say so
            return
        self.restarts.append(now)
        self.grace_until = now + GRACE
        self.set("reconnecting", detail)
        heard = getattr(bot, "last_chat", 0)
        log.warning("The bot was not really connected (%s; last chat heard %s): restarting it", detail,
                    f"{int(now - heard)} s ago" if heard else "never")
        self.restart()
        if now - self.last_notice > NOTICE_EVERY:
            self.last_notice = now
            try:
                notify.error(self.store.get("prefs"), "The bot had lost its connection to Twitch and was reconnected automatically.")
            except Exception:
                log.exception("Notification failed")

    async def run(self) -> None:
        last = self.clock()
        while True:
            await self.sleep(CHECK_EVERY)
            now = self.clock()
            woke, last = (now - last) > CHECK_EVERY * 3, now      # a long gap between checks means the PC slept
            try:
                await self.tick(woke)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Watchdog check failed")
