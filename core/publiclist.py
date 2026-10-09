"""Public command list: keeps a copy of the channel's public commands on the command-list website, so viewers can open one
short link (SITE/<channel>) that always shows the latest list. It is off until the streamer switches it on (Commands page).

What is sent: only the names of the switched-on commands that are not hidden from the public list, and who can use them.
The channel's Twitch login goes with it so the website can ask Twitch whose channel it is; the website does not keep it.
Nothing else in the app depends on the website: if it is down or switched off, the bot and !cmlist work as before."""
import asyncio
import hashlib
import json
import logging
import time

import aiohttp

from . import auth, manage
from .version import VERSION

log = logging.getLogger("twitchbot.publiclist")

# The website's address, with no slash at the end, e.g. "https://fqpn-commands.fqpn.workers.dev".
# Empty = the feature is not set up in this build (the page says so and nothing is ever sent).
SITE = "https://fqpn-asoom-commands.aymanxxxcrd.workers.dev"

FORMAT = 1              # the version of the data format; the website reads older formats too (room to add fields later)
CHECK_EVERY = 5         # seconds between looks at the commands (a save in the app wakes it straight away)
SETTLE = 4              # the list must stop changing for this long first, so a burst of edits becomes one save
RETRY = (30, 60, 120, 300, 600)   # after a failure, wait this long (seconds) before the next try
TIMEOUT = 15
MAX_COMMANDS = 500      # the website refuses more (it keeps lists small)


def page_url(login: str) -> str:
    return f"{SITE}/{login}" if SITE and login else ""


def build(commands, settings) -> dict:
    """The data the website gets: switched-on commands that are not hidden, by name, with who can use them."""
    hidden = set((settings or {}).get("public_hidden") or [])
    out = []
    for name in sorted(commands or {}, key=lambda n: (n.lower(), n)):
        c = commands[name]
        if not isinstance(c, dict) or c.get("enabled") is False or name in hidden:
            continue
        out.append({"name": name, "perm": manage.effective_permission(c)})
    return {"v": FORMAT, "commands": out[:MAX_COMMANDS]}


def digest(payload: dict, login: str) -> str:
    raw = json.dumps([login, payload], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def http_send(method: str, token: str, payload):
    """(HTTP status, JSON body, Retry-After seconds or None). Status 0 = the website could not be reached."""
    headers = {"Authorization": f"OAuth {token}", "User-Agent": f"FQPN-Chat-Bot/{VERSION}"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as s:
            async with s.request(method, SITE + "/api/list", headers=headers, json=payload) as r:
                try:
                    body = await r.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    body = {}
                retry = r.headers.get("Retry-After")
                return r.status, body if isinstance(body, dict) else {}, int(retry) if retry and retry.isdigit() else None
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return 0, {}, None


class Syncer:
    """Runs for as long as the app runs. One pass (step) at a time, so it can be tested without a network."""

    def __init__(self, store, state, send=None, clock=time.time):
        self.store, self.state = store, state
        self.send = send or http_send
        self.clock = clock
        self.wake = asyncio.Event()
        self.pending = None          # (digest, first seen) of a list that has not been sent yet
        self.fails = 0
        self.next_try = 0.0
        self.status = {"state": "off", "url": "", "error": "", "at": None}
        state["publist"] = self.status
        state["publist_wake"] = self.wake

    def set(self, kind: str, url: str = "", error: str = "", at=None) -> None:
        self.status.update(state=kind, url=url, error=error, at=at)

    def sync_now(self) -> None:
        """The "Try again" button: no more waiting for a retry."""
        self.next_try = 0.0
        if self.pending:
            self.pending = (self.pending[0], 0.0)
        self.wake.set()

    def _failed(self, kind: str, error: str, retry_after=None) -> None:
        wait = RETRY[min(self.fails, len(RETRY) - 1)]
        if retry_after:
            wait = max(wait, min(int(retry_after), 3600))
        self.fails += 1
        self.next_try = self.clock() + wait
        self.set(kind, error=error)

    def _remember(self, **kw) -> None:
        saved = dict(self.store.get("publist_state") or {})
        saved.update(kw)
        self.store.save("publist_state", saved)

    async def step(self) -> None:
        if not SITE:
            self.set("nosite")
            return
        settings = self.store.get("settings") or {}
        saved = self.store.get("publist_state") or {}
        token = ((auth.load_token() or {}).get("access_token")) or ""
        login = self.state.get("account") or ""
        now = self.clock()

        if not settings.get("public_list"):
            self.pending = None
            if saved.get("uploaded") and token and login and saved.get("login") == login:
                # switched off: take the list off the website too (once it can be reached)
                if now < self.next_try:
                    return
                code, body, retry = await self.send("DELETE", token, None)
                if code in (200, 204, 404):
                    self.fails, self.next_try = 0, 0.0
                    self._remember(uploaded=False, digest="")
                elif code == 0:
                    self._failed("off", "offline", retry)
                    return
                else:
                    self._failed("off", str(body.get("error") or code), retry)
                    return
            self.set("off")
            return

        if not token or not login:
            self.set("login")
            return
        payload = build(self.store.get("commands"), settings)
        d = digest(payload, login)
        if saved.get("uploaded") and saved.get("digest") == d and saved.get("login") == login:
            self.pending = None
            self.set("ok", url=page_url(login), at=saved.get("at"))
            return
        if self.pending is None or self.pending[0] != d:
            self.pending = (d, now)          # changed: wait until it stops changing
            if self.status["state"] not in ("error", "login", "offline"):
                self.set("waiting")
            return
        if now - self.pending[1] < SETTLE or now < self.next_try:
            return
        self.set("saving")
        code, body, retry = await self.send("PUT", token, payload)
        if code == 200 and body.get("ok"):
            who = str(body.get("login") or login)
            self.fails, self.next_try, self.pending = 0, 0.0, None
            self._remember(uploaded=True, digest=d, login=login, at=int(now))
            self.set("ok", url=page_url(who), at=int(now))
        elif code == 0:
            self._failed("offline", "offline", retry)
        elif code == 401:
            self._failed("login", str(body.get("error") or "Twitch did not accept the login."), retry)
        else:
            self._failed("error", str(body.get("error") or f"The website answered {code}."), retry)

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Public command list: a sync pass failed")
            try:
                await asyncio.wait_for(self.wake.wait(), CHECK_EVERY)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()
