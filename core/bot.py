"""The bot core: commands, aliases, variables, timers, blocklist,
permissions, announcements, title/game, stream detection.
Everything is driven by the JSON files in data/."""

import asyncio
import copy
import logging
import re
import sys
import time
import types
from collections import deque
from datetime import datetime, timezone

import aiohttp
import twitchio
from twitchio import eventsub
from twitchio.ext import commands

from . import auth, botauth, events, greetings, logsafe, manage, minigames, moderation, notify, publiclist
from .manage import CommandError
from .store import Store
from .stream import StreamSession

# 1.12.0: someone asks which app the bot is (the whole message): «app?» / «برنامج؟» (either question mark, any capitals)
APP_ASK = re.compile(r"^\s*(app|برنامج)\s*[?؟？]\s*$", re.IGNORECASE)


def clean_chat(text: str) -> str:
    """The message without invisible characters (1.12.0). Chat tools add some: 7TV / Chatterino put U+E0000 after a message
    you send twice in a row (so Twitch accepts the duplicate: an unassigned character), and many keyboards put a right-to-left mark (U+200F) before
    Arabic. Left in, «برنامج؟» or a command typed twice didn't match. Moderation still sees the original message."""
    import unicodedata
    return "".join(ch for ch in str(text or "") if unicodedata.category(ch) not in ("Cf", "Cn") and ch not in "\u034f\u2800").strip()
from .variables import Context, expand, uses_variable

log = logging.getLogger("twitchbot")

PERMISSION_LEVELS = {"everyone": 0, "subscriber": 1, "vip": 2, "moderator": 3, "broadcaster": 4}
ANNOUNCE = re.compile(r"^/announce(blue|green|orange|purple)?\s+(.+)$", re.IGNORECASE | re.DOTALL)
URLFETCH = re.compile(r"\$\(\s*urlfetch", re.IGNORECASE)
MANAGE_ACTIONS = {"add": "add", "edit": "edit", "options": "options",
                  "delete": "delete", "remove": "delete", "del": "delete"}
SHORTCUTS = {"addcom": "add", "editcom": "edit", "delcom": "delete"}


def user_level(chatter) -> int:
    if chatter.broadcaster:
        return 4
    if chatter.moderator:
        return 3
    if chatter.vip:
        return 2
    if chatter.subscriber:
        return 1
    return 0


SEARCH_URL = "https://api.twitch.tv/helix/search/categories"


def _plain(name: str) -> str:
    """A game name without capitals, spaces or punctuation, to compare "pubg battlegrounds" with "PUBG: BATTLEGROUNDS"."""
    return re.sub(r"[\W_]+", "", str(name).casefold())


def _tier_label(tier, prime: bool = False) -> str:
    if prime:
        return "Prime"
    return {"1000": "Tier 1", "2000": "Tier 2", "3000": "Tier 3"}.get(str(tier), str(tier) or "Tier 1")


def _twitchio_version() -> tuple:
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", str(getattr(twitchio, "__version__", "")))
    return tuple(int(x or 0) for x in m.groups()) if m else ()


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class TwitchBot(commands.Bot):
    def __init__(self, account: dict, store: Store | None = None, bot_account: dict | None = None, sender=None):
        # account = your channel account. bot_account = a separate account that writes the replies ("Use a separate bot
        # account" in Settings > Bot); without it the bot talks as your own account, exactly as before.
        self.account = account
        self.bot_account = bot_account or account
        self.separate = bot_account is not None and str(bot_account["user_id"]) != str(account["user_id"])
        # 1.12.0: a shared bot account sends this channel's replies (core/botsender.py). This bot then reads its own chat
        # with the channel's login, and hands every reply / announcement / moderation action to that sender.
        self.sender = sender
        self.sender_problem = ""          # why the bot account couldn't send (then the channel's own account did): shown in the app
        self._sender_warned = 0.0
        # the account whose messages and moderation are the bot's OWN (never answered as commands, never logged twice)
        self.writer_id = str(sender.bot_id) if sender is not None else str(self.bot_account["user_id"])
        self.store = store or Store()
        self.connected = False
        self.live_fail = 0          # live checks that failed in a row (the watchdog warns when timers may be waiting because of it)
        self.last_chat = 0.0        # when a chat message was last heard
        self._live_wake = asyncio.Event()      # Twitch saying "online" or "offline" makes the live check run right now
        self.session = StreamSession(          # the messages for when the stream starts, comes back and ends (Events > Stream)
            self.store, send=lambda text: self._send(text, why="stream"), followers=lambda: self._follower_total(), channel=account["login"],
            paused=lambda: bool(self.store.get("settings").get("paused")),
            log_event=lambda kind: self._log_activity("event", "stream " + kind))
        self.is_live = False
        self.viewers = 0            # how many people are watching right now ($(viewers)), from the live check
        self.live_since: datetime | None = None
        self._cooldowns: dict[str, float] = {}
        self._sent_ids: set[str] = set()
        self._recent_sent: deque[tuple[str, float]] = deque(maxlen=20)
        self._tasks: list[asyncio.Task] = []
        self._chan = None
        self._chan_ts = 0.0
        self._follow_cache: dict[str, tuple[float, object]] = {}
        self.activity = self.store.activity.items   # recent activity (also saved to disk by the store)
        self._dash_closed = False
        self._greet_tasks: set[asyncio.Task] = set()
        self.moderator = moderation.Moderator()          # the Moderation page's filters (strikes and recent messages live here)
        self.mod_problem = None                           # why Twitch refused the last delete/timeout (shown on the page)
        self.request_restart = None                       # set by main.py: reconnect the bot (re-reads the saved login)
        self._throttle = logsafe.Throttle()               # repeated errors once a minute in bot.log
        self._login_heal_at = 0.0
        self._chat_at = 0.0                               # last chat message heard (the quiet-chat check)
        self._chat_seen = 0
        self._quiet_restarts: list = []
        self.round = None                                 # the Mini games round in progress (minigames.Round)
        self._round_task = None
        self._last_round_end = time.time()
        self._filtered: deque = deque(maxlen=50)          # (time, name) of people a filter just acted on, so Twitch's echo isn't logged twice
        self._seen_events: deque = deque(maxlen=50)   # so a repeated delivery of the same notice is answered once
        self.event_problems: dict[str, str] = {}      # events Twitch refused to send (usually a missing permission)
        self._hype_level = 0

        super().__init__(
            client_id=auth.CLIENT_ID,
            client_secret=None,  # Public client: no secret
            bot_id=self.bot_account["user_id"],     # who writes in chat
            owner_id=account["user_id"],            # whose channel it is
            prefix=manage.BUILTIN_PREFIX,   # only used for the built-in commands
        )

    # ---------- lifecycle ----------

    async def setup_hook(self) -> None:
        # Hand the token(s) to TwitchIO so it keeps them refreshed.
        await self.add_token(self.account["access_token"], self.account["refresh_token"])
        if self.separate:
            await self.add_token(self.bot_account["access_token"], self.bot_account["refresh_token"])

        await self.subscribe_websocket(
            payload=eventsub.ChatMessageSubscription(
                broadcaster_user_id=self.owner_id, user_id=self.bot_id
            )
        )
        try:   # Watch Streaks arrive as chat notifications
            await self.subscribe_websocket(
                payload=eventsub.ChatNotificationSubscription(
                    broadcaster_user_id=self.owner_id, user_id=self.bot_id
                )
            )
        except Exception:
            log.exception("Could not subscribe to chat notifications; Watch Streaks won't be detected")
        ver = _twitchio_version()
        if ver and ver < (3, 3, 0):
            log.warning("Watch Streak detection needs TwitchIO 3.3 or newer (you have %s). Run: pip install -U twitchio",
                        ".".join(map(str, ver)))
        await self._subscribe_optional()
        self._tasks.append(asyncio.create_task(self._live_loop()))
        self._tasks.append(asyncio.create_task(self._timer_loop()))

    async def event_ready(self) -> None:
        self.connected = True
        if self.separate:
            log.info("Bot ready: %s writes in the chat of %s", self.bot_account["login"], self.account["login"])
        else:
            log.info("Bot ready, connected as %s", self.account["login"])

    async def event_token_refreshed(self, payload) -> None:
        # Keep our saved token in sync with what TwitchIO refreshed (each account has its own file).
        uid = str(payload.user_id)
        if self.separate and uid == str(self.bot_id):
            botauth.save_token(
                {
                    "access_token": payload.token,
                    "refresh_token": payload.refresh_token,
                    "expires_at": time.time() + int(payload.expires_in),
                    "scopes": list(payload.scopes) if payload.scopes else botauth.SCOPES,
                }
            )
        elif uid == str(self.owner_id):
            auth.save_token(
                {
                    "access_token": payload.token,
                    "refresh_token": payload.refresh_token,
                    "expires_at": time.time() + int(payload.expires_in),
                    "scopes": list(payload.scopes) if payload.scopes else auth.SCOPES,
                }
            )

    async def close(self, *args, **kwargs) -> None:
        if self._dash_closed:   # the dashboard's Disconnect and main.py may both call close()
            return
        self._dash_closed = True
        self.connected = False
        for t in [*self._tasks, *self._greet_tasks]:
            t.cancel()
        await super().close(*args, **kwargs)

    def _log_activity(self, kind: str, name: str, user: str = "") -> None:
        self.store.activity.add(kind, name, user)    # kind: command | timer | manage | greeting | event | chat

    def _log_chat(self, payload) -> None:
        """'Log chat messages' in Settings: keeps what viewers wrote next to the bot's own actions."""
        try:
            if not self.store.get("prefs").get("log_chat", False):
                return
            text = (payload.text or "").strip()
            chatter = payload.chatter
            if text:
                self.store.activity.add("chat", text, chatter.display_name or chatter.name)
        except Exception:
            log.exception("Could not log a chat message")

    # ---------- sending ----------

    def _remember(self, text: str, sent) -> None:
        self._recent_sent.append((text, time.time()))
        sid = getattr(sent, "id", None)
        if sid:
            self._sent_ids.add(sid)
            if len(self._sent_ids) > 200:
                self._sent_ids.clear()

    def _log_bot(self, text: str, payload, why, user) -> None:
        """The Logs page's Bot tab: what the bot said, and why ("cmd:!discord", "timer:name", "event:follow", ...)."""
        try:
            if why is None and payload is not None and getattr(payload, "text", None):
                why = "cmd:" + str(payload.text).split(" ", 1)[0][:60]
            if user is None and payload is not None and getattr(payload, "chatter", None) is not None:
                user = payload.chatter.display_name or payload.chatter.name
            self.store.activity.add("bot", text[:300], user or "", why=why or "")
        except Exception:
            log.exception("Could not log a bot message")

    async def _send(self, text: str, payload=None, why: str | None = None, user: str | None = None) -> None:
        """Sends to chat. Text starting with /announce, /announceblue,
        /announcegreen, /announceorange or /announcepurple becomes an announcement.
        `why` and `user` only label the message in the Logs page's Bot tab."""
        text = text.strip()
        if not text:
            return
        owner = self.create_partialuser(self.owner_id)

        m = ANNOUNCE.match(text)
        if self.sender is not None and await self._send_as_bot(text, m, payload, why, user):
            return
        if self.sender is not None:
            text = (m.group(2).strip() if m else text)[:500]      # the bot account couldn't: the channel's own account sends it
            m = None
        if m:
            color = (m.group(1) or "primary").lower()
            body = m.group(2).strip()[:500]
            try:
                await owner.send_announcement(moderator=self.bot_id, message=body, color=color)
                self._log_bot(body, payload, why, user)
                return
            except Exception:
                log.exception("Announcement failed (reconnect Twitch to grant the permission); sending as a normal message")
            text = body

        text = text[:500]
        try:
            if payload is not None and not self.separate:
                sent = await payload.respond(text)
            else:   # a separate bot account (or a message with no trigger): say who sends it
                sent = await owner.send_message(text, sender=self.bot_id)
        except Exception as e:
            self._login_trouble(e)          # a rejected login heals itself (reconnect with the saved login)
            raise
        self._remember(text, sent)
        self._log_bot(text, payload, why, user)

    async def _send_as_bot(self, text: str, m, payload, why, user) -> bool:
        """Sends through the shared bot account. False = it couldn't (the caller then sends with the channel's own account:
        replies never just stop). Twitch refusing one message (a chat mode, ...) is not retried."""
        from . import botsender
        try:
            if m:
                body = m.group(2).strip()[:500]
                try:
                    await self.sender.announce(self.owner_id, body, (m.group(1) or "primary").lower())
                    self.sender_problem = ""
                    self._log_bot(body, payload, why, user)
                    return True
                except botsender.SendError as e:
                    if e.code not in ("notmod", "scopes"):
                        raise
                    log.warning("The bot account can't post announcements here (%s): sending a normal message", e.code)
                    text = body
            text = text[:500]
            mid = await self.sender.send(self.owner_id, text, reply_to=getattr(payload, "id", None) if payload is not None else None)
            self.sender_problem = ""
            self._remember(text, types.SimpleNamespace(id=mid))
            self._log_bot(text, payload, why, user)
            return True
        except botsender.SendError as e:
            if e.code == "dropped":
                log.info("Twitch did not post the bot account's message: %s", e.detail)
                return True
            self.sender_problem = e.code
            if time.time() - self._sender_warned > 600:
                self._sender_warned = time.time()
                log.warning("The bot account %s couldn't send (%s): the channel's own account sends instead", self.sender.login, e.code)
                notify.error(self.store.get("prefs"), f"The bot account {self.sender.login} can't send in your chat ({e.code}). "
                                                       "Your own account sends the replies until it is fixed (Bot accounts page).")
            return False

    async def send_test(self) -> str:
        """The dashboard's "Send test message": says hello from the account the replies come from."""
        name = self.sender.login if self.sender is not None else self.bot_account["login"]
        await self._send(f"Hello from {name}!")
        self._log_activity("manage", "test message", name)
        return name

    def _is_own_echo(self, payload) -> bool:
        if payload.id in self._sent_ids:
            return True
        now = time.time()
        return any(t == payload.text and now - ts < 15 for t, ts in self._recent_sent)

    # ---------- checks ----------

    def _is_blocked(self, payload) -> bool:
        block = self.store.get("blocklist")
        login = (payload.chatter.name or "").lower()
        return login in {u.lower() for u in block.get("users", [])}     # (blocked words moved to Moderation > Bad words in 1.5.0)

    # ---------- moderation (the Moderation page) ----------

    WARN = {
        "en": {"badwords": "@$(user), please keep the chat friendly.", "links": "@$(user), only links to trusted sites are allowed here.",
               "caps": "@$(user), please don't write in all capitals.", "emotes": "@$(user), that's too many emotes in one message.",
               "symbols": "@$(user), that's too many symbols in one message.", "repeats": "@$(user), please don't repeat yourself."},
        "ar": {"badwords": "‏@$(user) رجاءً حافظ على أسلوب لطيف في الدردشة.", "links": "‏@$(user) يُسمح فقط بروابط المواقع الموثوقة هنا.",
               "caps": "‏@$(user) رجاءً لا تكتب بالأحرف الكبيرة فقط.", "emotes": "‏@$(user) عدد الإيموجيات كثير في رسالة واحدة.",
               "symbols": "‏@$(user) عدد الرموز كثير في رسالة واحدة.", "repeats": "‏@$(user) رجاءً لا تكرر الكلام."},
    }
    LABEL = {"badwords": "Bad words", "links": "Links", "caps": "Excess caps", "emotes": "Excess emotes", "symbols": "Excess symbols", "repeats": "Repetitions"}

    async def _moderate(self, payload) -> bool:
        """Runs the filters. True when the message broke one: it is then deleted (and the person warned or timed out), so
        nothing else answers it. Never touches the channel owner, the bot itself, mods or (by default) VIPs."""
        if self.store.get("settings").get("paused"):
            return False
        settings = self.store.get("moderation") or {}
        if not any((settings.get(f) or {}).get("enabled") for f in moderation.FILTERS):
            return False
        chatter = payload.chatter
        uid = str(getattr(chatter, "id", "") or "")
        if not uid or uid in (str(self.owner_id), self.writer_id):
            return False
        roles = {k: bool(getattr(chatter, k, False)) for k in ("broadcaster", "moderator", "vip", "subscriber")}
        frags = getattr(payload, "fragments", None) or []
        emote_words = [str(getattr(f, "text", "")) for f in frags if str(getattr(f, "type", "")) == "emote"]
        hit = self.moderator.check(settings, payload.text or "", uid, roles, len(emote_words), emote_words)
        if not hit:
            return False
        filt, _detail = hit
        cfg = settings.get(filt) or {}
        step = self.moderator.punishment(cfg, filt, uid)
        user = chatter.display_name or chatter.name
        self._filtered.append((time.time(), str(chatter.display_name or chatter.name).lower()))
        await self._mod_api("DELETE", "moderation/chat", {"message_id": str(payload.id)})
        did = "delete:0"
        if step:
            await self._mod_api("POST", "moderation/bans", {}, {"data": {"user_id": uid, "duration": int(step), "reason": f"{self.LABEL[filt]} filter"}})
            did = f"timeout:{int(step)}"
        elif step == 0:
            lang = "ar" if (self.store.get("ui") or {}).get("language") == "ar" else "en"
            text = (cfg.get("warn_text") or "").strip() or self.WARN[lang][filt]
            await self._send(text.replace("$(user)", str(user)), payload, why="warn:" + filt, user=str(user))
            did = "warn:0"
        self.store.activity.add("moderation", f"{filt}:{did}", user, text=(payload.text or "")[:300], by="", shared=payload.source_broadcaster is not None)   # the page turns the name into words
        return True

    async def _mod_api(self, method: str, path: str, params: dict, body=None) -> bool:
        """A Twitch moderation call made by whoever moderates: the separate bot account, or the channel account."""
        if self.sender is not None:       # 1.12.0: the shared bot account moderates (it must be a moderator here)
            ok = await self.sender.moderate(method, path, self.owner_id, params, body)
            self.mod_problem = None if ok else "scopes"
            return ok
        if self.separate:
            data = botauth.load_token() or {}
            token = data.get("access_token") or self.bot_account.get("access_token")
        else:
            data = auth.load_token() or {}
            token = data.get("access_token") or self.account.get("access_token")
        q = dict(params, broadcaster_id=str(self.owner_id), moderator_id=str(self.bot_account["user_id"]))
        headers = {"Authorization": f"Bearer {token}", "Client-Id": auth.CLIENT_ID}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.request(method, "https://api.twitch.tv/helix/" + path, params=q, headers=headers, json=body) as r:
                    if r.status in (200, 204):
                        self.mod_problem = None
                        return True
                    self.mod_problem = "scopes" if r.status in (401, 403) else f"twitch {r.status}"
                    log.warning("Moderation %s %s answered %s", method, path, r.status)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            log.warning("Moderation %s %s could not reach Twitch", method, path)
        return False

    def _on_cooldown(self, key: str, seconds: float) -> bool:
        now = time.time()
        if now - self._cooldowns.get(key, 0) < seconds:
            return True
        self._cooldowns[key] = now
        return False

    # ---------- variables ----------

    def _bump(self, key: str) -> int:
        counters = self.store.get("counters")
        counters[key] = int(counters.get(key, 0)) + 1
        self.store.save("counters", counters)
        return counters[key]

    async def _channel_info(self):
        if self._chan is None or time.time() - self._chan_ts > 20:
            infos = await self.fetch_channels([self.owner_id], token_for=self.owner_id)
            self._chan, self._chan_ts = infos[0], time.time()
        return self._chan

    async def _game(self) -> str:
        try:
            return (await self._channel_info()).game_name or "(no game set)"
        except Exception:
            log.exception("Could not read the current game")
            return "(unknown)"

    async def _title(self) -> str:
        try:
            return (await self._channel_info()).title or "(no title set)"
        except Exception:
            log.exception("Could not read the current title")
            return "(unknown)"

    async def _followed_at(self, chatter_id: str):
        """When this user followed the channel, or None. Cached so chat spam doesn't hammer Twitch."""
        hit = self._follow_cache.get(chatter_id)
        if hit and time.time() < hit[0]:
            return hit[1]
        owner = self.create_partialuser(self.owner_id)
        result = await owner.fetch_followers(user=chatter_id, token_for=self.owner_id)
        when = None
        async for f in result.followers:
            when = f.followed_at
            break
        # Followers are cached for 10 minutes; "not following" only for 1 minute.
        self._follow_cache[chatter_id] = (time.time() + (600 if when else 60), when)
        if len(self._follow_cache) > 500:
            self._follow_cache.clear()
        return when

    def _ctx(self, user: str, query: str = "", counter_key: str | None = None, chatter=None) -> Context:
        uptime = (
            format_duration((datetime.now(timezone.utc) - self.live_since).total_seconds())
            if self.live_since else "offline"
        )
        return Context(
            user=user,
            login=(getattr(chatter, "name", None) or user) if chatter is not None else user,
            query=query,
            channel=self.account["login"],
            uptime=uptime,
            viewers=self.viewers,
            count=(lambda: self._bump(counter_key)) if counter_key else (lambda: 0),
            game=self._game,
            title=self._title,
            followed_at=(lambda: self._followed_at(str(chatter.id))) if chatter is not None else None,
            is_owner=bool(chatter is not None and chatter.broadcaster),
            lang="ar" if (self.store.get("ui") or {}).get("language") == "ar" else "en",
        )

    # ---------- Twitch events ----------

    async def _subscribe_optional(self) -> None:
        """Follows and Hype Trains need extra Twitch permissions. If Twitch refuses, the rest of the bot keeps working."""
        async def attempt(name, *makers):
            try:
                for make in makers:
                    if self.separate:   # these belong to the channel: they use your channel account's login, not the bot's
                        await self.subscribe_websocket(payload=make(), token_for=self.owner_id)
                    else:
                        await self.subscribe_websocket(payload=make())
                self.event_problems.pop(name, None)
            except Exception as e:
                self.event_problems[name] = str(e)[:160] or e.__class__.__name__
                log.warning("Can't listen for %s events (%s). They need an extra Twitch permission: add it to auth.py and reconnect.",
                            name, e.__class__.__name__)
        owner = self.owner_id
        # online / offline only wake the live check up early; the check itself is what decides, so if this is refused nothing is lost
        await attempt("stream",
                      lambda: eventsub.StreamOnlineSubscription(broadcaster_user_id=owner),
                      lambda: eventsub.StreamOfflineSubscription(broadcaster_user_id=owner))
        # you are always allowed to see your own followers, so with a separate bot account you are the "moderator" here
        await attempt("follow", lambda: eventsub.ChannelFollowSubscription(broadcaster_user_id=owner, moderator_user_id=owner))
        await attempt("hype_train",
                      lambda: eventsub.HypeTrainBeginSubscription(broadcaster_user_id=owner),
                      lambda: eventsub.HypeTrainProgressSubscription(broadcaster_user_id=owner),
                      lambda: eventsub.HypeTrainEndSubscription(broadcaster_user_id=owner))
        # what your human mods do (bans, timeouts, deletes, warnings, chat modes...) for the Logs page's Moderation tab
        maker = getattr(eventsub, "ChannelModerateSubscription", None)
        if maker is None:
            self.event_problems["modlog"] = "This TwitchIO version can't listen for moderation actions."
        else:
            await attempt("modlog", lambda: maker(broadcaster_user_id=owner, moderator_user_id=owner))

    @staticmethod
    def _names(user):
        """(display name, login) of a TwitchIO user, tolerant of missing attributes."""
        login = (getattr(user, "name", None) or "").lower()
        return (getattr(user, "display_name", None) or getattr(user, "name", None) or login or ""), login

    async def _fire_event(self, key, value, user, login="", extra=None, dedupe=None) -> None:
        """Answers one Twitch event with the best matching reply from the Events page."""
        blocked = {u.lower() for u in self.store.get("blocklist").get("users", [])}
        if login and login.lower() in blocked:
            return
        if dedupe is not None:
            if dedupe in self._seen_events:
                return
            self._seen_events.append(dedupe)
        try:   # a desktop pop-up, whether or not a chat reply is set up for this event
            notify.event(self.store.get("prefs"), key, user, value, extra)
        except Exception:
            log.exception("Notification failed")
        if self.store.get("settings").get("paused") or (extra or {}).get("_no_reply"):
            return
        template = events.pick_reply(self.store.get("events"), key, value)
        if template is None:
            return
        ctx = self._ctx(user, "", counter_key=f"event:{key}")
        ctx.login = login or user
        ctx.extra = dict(extra or {})
        if key == "watch_streak":
            ctx.streak = value
        label = key.replace("_", " ")
        if key == "donation":
            self._log_activity("event", f"donation {ctx.extra.get('amount', value)} {ctx.extra.get('currency', '')}".strip(), user)
        else:
            self._log_activity("event", f"{label} {value}" if value else label, user)
        await self._send(await expand(template, ctx), why="event:" + key, user=user)

    async def on_donation(self, d: dict) -> None:
        """A donation arrived from Streamlabs or StreamElements (see donations.py): thank the donor in chat."""
        amount = d["amount"]
        shown = f"{int(amount)}" if amount == int(amount) else f"{amount:.2f}"
        block = self.store.get("blocklist")
        text = f"{d['user']} {d['message']}".lower()
        muted = any(w.lower() in text for w in block.get("words", []) if w)    # a blocked word in the name or note: no public reply
        extra = {"amount": shown, "currency": d["currency"], "message": d["message"]}
        if muted:
            extra["_no_reply"] = True
        login = d["user"].lower().replace(" ", "_")
        await self._fire_event("donation", amount, d["user"], login, extra=extra,
                               dedupe=f"{d['service']}:{d['id']}" if d.get("id") else None)

    async def event_chat_notification(self, payload) -> None:
        """Subs, gifts, raids and watch streaks arrive here (needs no extra permission)."""
        try:
            await self._on_notification(payload)
        except Exception:
            log.exception("Chat notification handling failed")

    async def _on_notification(self, payload) -> None:
        if getattr(payload, "source_broadcaster", None) is not None:
            return                                          # a viewer from another channel in a shared chat
        nid = str(getattr(payload, "id", None) or "")
        chatter = getattr(payload, "chatter", None)
        user, login = self._names(chatter)
        anonymous = bool(getattr(payload, "chatter_is_anonymous", False)) or chatter is None

        ws = getattr(payload, "watch_streak", None)
        if ws is not None:
            streak = int(getattr(ws, "streak", 0) or 0)
            if streak > 0:
                await self._fire_event("watch_streak", streak, user or "viewer", login, dedupe=nid or f"streak:{login}:{streak}")
            return

        sub = getattr(payload, "sub", None) or getattr(payload, "resub", None)
        if sub is not None:
            try:
                months = int(getattr(sub, "cumulative_months", None) or getattr(sub, "months", None) or 1)
            except (TypeError, ValueError):
                months = 1
            months = max(1, months)
            await self._fire_event(
                "subscription", months, user or "viewer", login,
                {"tier": _tier_label(getattr(sub, "tier", ""), getattr(sub, "prime", False)), "months": months,
                 "message": str(getattr(payload, "text", "") or "")},
                dedupe=nid or f"sub:{login}:{months}")
            return

        group = getattr(payload, "community_sub_gift", None)
        single = getattr(payload, "sub_gift", None)
        # One gift bomb arrives as a group notice plus one notice per gift: only the group is answered.
        if group is not None or (single is not None and not getattr(single, "community_gift_id", None)):
            count = max(1, int(getattr(group, "total", 1) or 1)) if group is not None else 1
            source = group if group is not None else single
            await self._fire_event(
                "gift_sub", count, "Anonymous" if anonymous else (user or "Someone"), "" if anonymous else login,
                {"gifts": count, "tier": _tier_label(getattr(source, "tier", ""))},
                dedupe=nid or f"gift:{login}:{count}")
            return

        raid = getattr(payload, "raid", None)
        if raid is not None:
            raider, raider_login = self._names(getattr(raid, "user", None))
            viewers = int(getattr(raid, "viewer_count", 0) or 0)
            await self._fire_event(
                "raid", viewers, raider or "someone", raider_login,
                {"raider": raider or "someone", "viewers": viewers},
                dedupe=nid or f"raid:{raider_login}:{viewers}")

    async def event_mod_action(self, payload) -> None:
        """Twitch "channel.moderate": a moderator (or you) did something in chat. Written to Logs > Moderation.
        The bot's own filter actions are already there with more detail, so its own account's actions are skipped."""
        try:
            mid = str(getattr(getattr(payload, "moderator", None), "id", "") or "")
            if mid and mid == self.writer_id and (self.separate or self.sender is not None):
                return
            e = moderation.describe_action(payload)
            if e is None:
                return
            if mid == self.writer_id and e["name"].split(":")[0] in ("delete", "timeout") and self._recently_filtered(e["user"]):
                return      # a filter just did this (as the moderating account): already logged with the filter's details
            self.store.activity.add("modaction", e["name"], e["user"], by=e["by"], text=e["text"], shared=e["shared"])
        except Exception:
            log.exception("Could not log a moderation action")

    def _recently_filtered(self, user: str) -> bool:
        now, who = time.time(), str(user).lower()
        return any(u == who and now - at < 30 for at, u in list(self._filtered))

    async def event_follow(self, payload) -> None:
        try:
            user, login = self._names(getattr(payload, "user", None))
            await self._fire_event("follow", 0, user or "viewer", login, dedupe=f"follow:{login}")
        except Exception:
            log.exception("Follow handling failed")

    async def event_hype_train(self, payload) -> None:        # a Hype Train begins
        self._hype_level = 0
        await self._hype(payload)

    async def event_hype_train_progress(self, payload) -> None:
        await self._hype(payload)

    async def event_hype_train_end(self, payload) -> None:
        self._hype_level = 0

    async def _hype(self, payload) -> None:
        """Answers once per level, not on every contribution."""
        try:
            level = int(getattr(payload, "level", 0) or 0)
            if level <= self._hype_level:
                return
            self._hype_level = level
            await self._fire_event("hype_train", level, self.account["login"], "", {"level": level})
        except Exception:
            log.exception("Hype train handling failed")

    async def _on_cheer(self, payload) -> None:
        """Bits arrive inside the chat message itself (needs no extra permission)."""
        cheer = getattr(payload, "cheer", None)
        bits = int(getattr(cheer, "bits", 0) or 0) if cheer is not None else 0
        if bits <= 0:
            return
        user, login = self._names(getattr(payload, "chatter", None))
        await self._fire_event(
            "bits", bits, user or "viewer", login,
            {"bits": bits, "message": str(getattr(payload, "text", "") or "")},
            dedupe=str(getattr(payload, "id", "") or f"bits:{login}:{bits}"))

    # ---------- greetings ----------

    def _maybe_greet(self, payload) -> None:
        """A person on the greetings list writes in chat while live: greet them once per stream, a few seconds later."""
        if not self.is_live or self.live_since is None:
            return
        chatter = payload.chatter
        login = (getattr(chatter, "name", None) or "").lower()
        if not login or self.store.get("settings").get("paused"):
            return
        g = self.store.get("greetings")
        messages = (greetings.messages_for(g, login)
                    or greetings.developer_messages(g, login, getattr(chatter, "id", None), self.owner_id))
        if not messages:
            return
        state, text = greetings.claim(self.store.get("greeted"), self.live_since.isoformat(), login, messages)
        if text is None:
            return
        self.store.save("greeted", state)   # kept on disk, so restarting the bot can't greet twice in one stream
        task = asyncio.create_task(self._greet_later(login, chatter, text))
        self._greet_tasks.add(task)
        task.add_done_callback(self._greet_tasks.discard)

    async def _greet_later(self, login, chatter, template) -> None:
        try:
            await asyncio.sleep(greetings.GREETING_DELAY)
            if (self.store.get("settings").get("paused") or not self.is_live
                    or not self.store.get("greetings").get("enabled", True)):
                self.store.save("greeted", greetings.release(self.store.get("greeted"), login))   # try again on their next message
                return
            user = chatter.display_name or chatter.name
            self._log_activity("greeting", login, user)
            ctx = self._ctx(user, "", counter_key=f"greet:{login}", chatter=chatter)
            await self._send(await expand(template, ctx), why="greeting", user=user)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Greeting failed")

    # ---------- chat ----------

    # ---------- staying alive: a rejected login heals itself, and a chat that went silent reconnects ----------

    @staticmethod
    def _is_login_failure(exc) -> bool:
        """True when Twitch rejected the login (the chain of errors mentions an invalid token / refresh token / a 401)."""
        seen = 0
        while exc is not None and seen < 6:
            t = str(exc)
            if "scope" in t.lower():      # "Missing scope ...": a permission Twitch wants, not a dead login (a reconnect can't fix it)
                return False
            if "Invalid refresh token" in t or "Invalid OAuth token" in t or "status 401" in t:
                return True
            exc, seen = exc.__cause__ or exc.__context__, seen + 1
        return False

    def _login_trouble(self, exc) -> None:
        """The login the bot holds was rejected (usually: it was renewed elsewhere and this copy is now stale). Reconnect: the
        restart re-reads the saved login, which is the newest one; if that's dead too, the app asks to connect Twitch again."""
        if not self._is_login_failure(exc) or self.request_restart is None or time.time() - self._login_heal_at < 120:
            return
        self._login_heal_at = time.time()
        log.warning("Twitch rejected the bot's login: reconnecting with the saved login")
        self.request_restart("login")

    def _quiet_check(self) -> None:
        """Live, chat was active, and then nothing at all for 15 minutes: the chat connection probably died silently."""
        now = time.time()
        seen, last, hook = getattr(self, "_chat_seen", 0), getattr(self, "_chat_at", 0.0), getattr(self, "request_restart", None)
        if not getattr(self, "is_live", False) or seen < 5 or not last or now - last < 900 or hook is None:
            return
        self._quiet_restarts = [t for t in self._quiet_restarts if now - t < 3600]
        if len(self._quiet_restarts) >= 3:
            return
        verified = getattr(self, "chat_verified", None)
        if verified is not None and verified():
            self._chat_at = now              # Twitch confirmed the chat connection a moment ago: the chat is just quiet
            log.info("No chat messages for 15 minutes, but Twitch confirms the chat connection: no reconnect")
            return
        self._quiet_restarts.append(now)
        self._chat_at = now
        log.warning("No chat messages for 15 minutes while live: reconnecting the bot to be safe")
        self.request_restart("quiet")

    async def event_message(self, payload) -> None:
        self.last_chat = time.time()      # proof that chat is arriving (the watchdog quotes it when it has to reconnect)
        if not self._is_own_echo(payload):
            self._chat_at = self.last_chat; self._chat_seen += 1   # the quiet-chat check
        # Note: we do NOT ignore the streamer's own messages (the bot IS the
        # streamer's account), only the bot's own replies.
        if self._is_own_echo(payload):
            return
        if payload.source_broadcaster is not None:     # a message from a channel sharing this chat (Shared Chat)
            if (self.store.get("moderation") or {}).get("shared_chat"):
                try:
                    await self._moderate(payload)
                except Exception:
                    log.exception("Moderation failed")
            return
        if (self.separate or self.sender is not None) and str(getattr(payload.chatter, "id", "")) == self.writer_id:
            return      # whatever the bot account writes is never treated as a command
        try:
            if await self._moderate(payload):
                return      # removed by a Moderation filter: nothing else answers it
        except Exception:
            log.exception("Moderation failed")
        if self._is_blocked(payload):
            return
        self._log_chat(payload)
        if self.store.get("settings").get("paused"):   # paused from the dashboard: stay silent
            return
        try:
            self._maybe_greet(payload)
        except Exception:
            log.exception("Greeting check failed")
        try:
            await self._on_cheer(payload)
        except Exception:
            log.exception("Bits handling failed")
        try:
            if await self._game_message(payload):
                return          # a game command, or the winning answer: nothing else answers it
        except Exception:
            log.exception("Mini game failed")

        text = clean_chat(payload.text)
        chatter = payload.chatter
        user = chatter.display_name or chatter.name
        level = user_level(chatter)

        # Built-in commands always start with "!"
        if text.startswith(manage.BUILTIN_PREFIX):
            name, _, rest = text[len(manage.BUILTIN_PREFIX):].partition(" ")
            name, rest = name.lower(), rest.strip()
            key = manage.BY_TYPED.get(name)          # what was typed (!cmadd) -> the built-in's internal name (addcom)
            if key:
                if key in (self.store.get("settings").get("disabled_builtins") or []):
                    return          # switched off in the dashboard (Commands > Built-in): stay silent
                await self._builtin(payload, key, rest, user, level, manage.BUILTIN_PREFIX)
                return

        # Custom commands: the creator chose the exact name (any symbol or none, spaces allowed)
        found = manage.match_command(self.store.get("commands"), text)
        if found:
            await self._custom(payload, found[0], found[1], user, level)
            return
        # 1.12.0: «app?» / «برنامج؟» -> the app's website (a built-in; your own command with that name wins)
        ask = APP_ASK.match(text)
        if ask and "app" not in (self.store.get("settings").get("disabled_builtins") or []) and not self._on_cooldown("builtin:app", 60):
            await self._send(f"Chatbot app: {publiclist.SITE}", payload, why="cmd:" + text)

    async def _custom(self, payload, owner, rest, user, level) -> None:
        cmd = self.store.get("commands").get(owner)
        if not cmd or not cmd.get("enabled", True):
            return
        if level < PERMISSION_LEVELS.get(manage.effective_permission(cmd), 0):
            return          # (a shortcut always needs a moderator or the broadcaster)
        if self._on_cooldown(f"cmd:{owner}", cmd.get("cooldown", 0)):
            return
        action = cmd.get("action", "text")
        if action in ("game", "title"):
            self._log_activity("command", owner, user)
            value = cmd["response"]
            if "$(" in value:      # e.g. !g with "$(query)": "!g Valorant" changes the game to what was typed
                value = (await expand(value, self._ctx(user, rest, chatter=payload.chatter))).strip()
            if not value:          # "!g" with nothing after it: say the current game / title instead
                await self._send(f"Game: {await self._game()}" if action == "game" else f"Title: {await self._title()}", payload)
                return
            await (self._set_game if action == "game" else self._set_title)(value, payload)
            return
        if uses_variable(cmd["response"], "uptime") and not self.live_since:
            await self._send(f"{self.account['login']} is offline right now.", payload)
            return
        self._log_activity("command", owner, user)
        ctx = self._ctx(user, rest, counter_key=f"cmd:{owner}", chatter=payload.chatter)
        await self._send(await expand(cmd["response"], ctx), payload)

    # ---------- built-in commands ----------

    async def _builtin(self, payload, name, rest, user, level, prefix) -> None:
        is_mod = level >= 3

        if name in SHORTCUTS:
            if is_mod:
                await self._manage(payload, SHORTCUTS[name], rest, user, level, prefix)
            return

        if name == "commands":
            sub, _, args = rest.partition(" ")
            action = MANAGE_ACTIONS.get(sub.lower())
            if action:
                if is_mod:
                    await self._manage(payload, action, args, user, level, prefix)
                return
            if self._on_cooldown("builtin:commands", 10):
                return
            url = (self.store.get("settings").get("commands_url") or "").strip()
            if url:
                await self._send(f"Commands: {url}", payload)
                return
            visible = [
                n for n, c in self.store.get("commands").items()
                if c.get("enabled", True) and level >= PERMISSION_LEVELS.get(manage.effective_permission(c), 0)
            ]
            await self._send("Commands: " + (", ".join(visible) if visible else "none yet"), payload)
            return

        if name == "title":
            if rest and is_mod:
                await self._set_title(rest, payload)
            elif not rest and not self._on_cooldown("builtin:title", 5):
                await self._send(f"Title: {await self._title()}", payload)
            return

        if name == "game":
            if rest and is_mod:
                await self._set_game(rest, payload)
            elif not rest and not self._on_cooldown("builtin:game", 5):
                await self._send(f"Game: {await self._game()}", payload)
            return

    # ---------- changing the game and title (the built-ins and the shortcut commands) ----------

    async def _set_title(self, text: str, payload) -> None:
        text = " ".join(text.split())[:140]
        try:
            await self.create_partialuser(self.owner_id).modify_channel(title=text)
            self._chan_ts = 0
            await self._send(f"Title updated to: {text}", payload)
        except Exception:
            log.exception("Title change failed")
            await self._send("Couldn't change the title. Reconnect Twitch to grant the new permission.", payload)

    async def _set_game(self, query: str, payload) -> None:
        query = " ".join(query.split())[:100]
        try:
            game = await self._find_game(query)
            if game is None:
                await self._send(f"Couldn't find a game called '{query}' on Twitch.", payload)
                return
            await self.create_partialuser(self.owner_id).modify_channel(game_id=game[0])
            self._chan_ts = 0
            await self._send(f"Game updated to: {game[1]}", payload)
        except Exception:
            log.exception("Game change failed")
            await self._send("Couldn't change the game. Reconnect Twitch to grant the new permission.", payload)

    async def _find_game(self, query: str):
        """(id, name) of the game people mean, or None. The exact name first (any capitals); otherwise Twitch's own search,
        preferring a name that only differs in spaces and punctuation, then Twitch's best match: "pubg" -> PUBG: BATTLEGROUNDS."""
        games = await self.fetch_games(names=[query], token_for=self.owner_id)
        if games:
            return str(games[0].id), games[0].name
        found = await self._search_games(query)
        if not found:
            return None
        want = _plain(query)
        for g in found:
            if _plain(g["name"]) == want:
                return g["id"], g["name"]
        return found[0]["id"], found[0]["name"]

    async def _search_games(self, query: str) -> list:
        """Twitch's Search Categories, asked directly (like the watchdog does). [] if it can't be reached."""
        token = (auth.load_token() or {}).get("access_token") or self.account.get("access_token")
        headers = {"Authorization": f"Bearer {token}", "Client-Id": auth.CLIENT_ID}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(SEARCH_URL, params={"query": query, "first": "10"}, headers=headers) as r:
                    if r.status != 200:
                        log.warning("Game search answered %s", r.status)
                        return []
                    data = await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            log.warning("Game search could not reach Twitch")
            return []
        return [{"id": str(g.get("id")), "name": str(g.get("name"))} for g in (data or {}).get("data", []) if g.get("id") and g.get("name")]

    # ---------- Mini games: «اسم، جماد، نبات، حيوان، بلاد» (letters) and «رتب» (scramble). One round at a time. ----------

    def _level_of(self, chatter) -> int:
        return 4 if chatter.broadcaster else 3 if chatter.moderator else 2 if chatter.vip else 1 if chatter.subscriber else 0

    def _game_cfg(self, key: str) -> dict:
        """A game's settings ("letters", "scramble", or "shared" = All games), with the defaults for anything missing."""
        return dict(minigames.defaults()[key], **((self.store.get("games") or {}).get(key) or {}))

    def _stream_id(self):
        """Which stream this is (the stream messages' session: a short drop or an app restart is still the same stream)."""
        session = getattr(self, "session", None)
        return (getattr(session, "s", None) or {}).get("stream_id")

    def _rounds_used(self) -> int:
        st = self.store.get("game_rounds") or {}
        return int(st.get("rounds") or 0) if st.get("stream") == self._stream_id() else 0      # a new stream: refilled

    def _count_round(self) -> None:
        sid = self._stream_id()
        st = dict(self.store.get("game_rounds") or {})
        n = int(st.get("rounds") or 0) + 1 if st.get("stream") == sid else 1
        self.store.save("game_rounds", dict(st, stream=sid, rounds=n))

    def _round_ended(self) -> None:
        """A round just ended (won or time's up): the cooldown counts from now. Saved, so a reconnect keeps it."""
        self._last_round_end = time.time()
        self.store.save("game_rounds", dict(self.store.get("game_rounds") or {}, ended_at=self._last_round_end))

    def _round_block(self, shared=None):
        """Why a new round can't start now: ("limit", rounds) | ("cooldown", seconds left) | None. Settings: All games."""
        sh = shared if shared is not None else self._game_cfg("shared")
        limit, cool = int(sh.get("rounds_per_stream") or 0), int(sh.get("cooldown_seconds") or 0)
        if limit and self._rounds_used() >= limit:
            return "limit", limit
        ended = float((self.store.get("game_rounds") or {}).get("ended_at") or 0)
        left = cool - (time.time() - ended) if ended else 0
        if cool and left > 0:
            return "cooldown", left
        return None

    @staticmethod
    def _wait_text(seconds: float) -> str:
        s = max(1, int(seconds + 0.999))
        return f"{s} ثانية" if s < 60 else f"{s // 60}:{s % 60:02d} دقيقة"

    def game_limits(self) -> dict:
        """For the page (All games): rounds used this stream, the limit, and the cooldown still to wait."""
        sh = self._game_cfg("shared")
        block = self._round_block(sh)
        return {"used": self._rounds_used(), "limit": int(sh.get("rounds_per_stream") or 0),
                "wait": round(block[1]) if block and block[0] == "cooldown" else 0}

    async def _game_message(self, payload) -> bool:
        cfgs = {k: self._game_cfg(k) for k in minigames.GAME_KEYS}
        if not any(c.get("enabled") for c in cfgs.values()):
            return False
        lc, sh = cfgs["letters"], self._game_cfg("shared")      # !فوز and !الأوائل: All games (any of their names)
        text = (payload.text or "").strip()
        first, _, arg = text.partition(" ")
        key = minigames.cmd_key(first)
        ch = payload.chatter
        user, uid, level = ch.display_name or ch.name, str(ch.id), self._level_of(ch)
        for game, cfg in cfgs.items():
            if cfg.get("enabled") and key in minigames.aliases(cfg.get("start_cmd")):
                if level >= PERMISSION_LEVELS.get(cfg.get("who_starts", "moderator"), 3):
                    block = None if level >= 4 else self._round_block(sh)     # the broadcaster can always start one
                    if self.round and not self.round.over:
                        if not self._on_cooldown("game:busy", 10):
                            await self._send("في جولة شغالة الحين! ⏳", payload, why="game")
                    elif block and block[0] == "limit":
                        if not self._on_cooldown("game:limit", 30):
                            await self._send(f"🚫 خلصت جولات هالبث ({block[1]}/{block[1]}). ترجع الجولات مع البث الجاي!", payload, why="game")
                    elif block:
                        if not self._on_cooldown("game:cool", 10):
                            await self._send(f"⏳ الجولة الجاية بعد {self._wait_text(block[1])}", payload, why="game")
                    else:
                        await self._game_start(game, cfg)
                return True
        if key in minigames.aliases(sh.get("wins_cmd")):
            if not self._on_cooldown(f"game:wins:{uid}", 5):
                e = (self.store.get("game_wins") or {}).get(uid) or {}
                n, parts = minigames.wins_of(e), minigames.breakdown(e)
                await self._send((f"‏@{user} عندك {n} فوز 🏆" + (f" ({parts})" if parts else ""))
                                 if n else f"‏@{user} ما عندك فوز بعد، جرّب في الجولة الجاية!", payload, why="game")
            return True
        if key in minigames.aliases(sh.get("top_cmd")):
            game = minigames.game_named(arg) if arg.strip() else None
            if not self._on_cooldown(f"game:top:{game or 'all'}", 10):
                best = minigames.top(self.store.get("game_wins") or {}, 5, game)
                head = f"🏆 الأوائل في {minigames.GAME_NAMES[game]}: " if game else "🏆 الأوائل: "
                await self._send(head + " | ".join(f"{i}. {n} ({w})" for i, (n, w) in enumerate(best, 1)) if best else "ما في فائزين بعد.", payload, why="game")
            return True
        r = self.round
        if key in minigames.aliases(lc.get("approve_cmd")) and lc.get("enabled"):
            if level >= 3 and r and getattr(r, "key", "letters") == "letters" and not r.over:
                who = arg.strip().lstrip("@").lower()
                pick = next((p for p in reversed(r.pending) if not who or p[1].lower() == who), None)
                if pick is None:
                    await self._send("ما في كلمة تنتظر الموافقة.", payload, why="game")
                else:
                    games = self.store.get("games")
                    words = games["letters"].setdefault("words", {}).setdefault(r.cat, [])
                    if minigames.norm(pick[2]) not in {minigames.norm(w) for w in words}:
                        words.append(pick[2])
                        self.store.save("games", games)       # the approved word joins the list for next time
                    await self._game_win(pick[0], pick[1], pick[2])
            return True
        if r is None or r.over or text.startswith("!") or not cfgs.get(getattr(r, "key", "letters"), {}).get("enabled"):
            return False
        if getattr(r, "key", "letters") == "scramble":
            if r.check(text) == "win":
                await self._game_win(uid, user, r.word)
                return True
            return False
        verdict = r.check(text, (lc.get("words") or {}).get(r.cat, []))
        if verdict == "win":
            await self._game_win(uid, user, text)
            return True
        if verdict == "unknown":
            r.pending = [p for p in r.pending if p[0] != uid][-9:] + [(uid, user, text)]
        return False

    async def _game_start(self, game="letters", cfg=None) -> None:
        if isinstance(game, dict):          # older callers passed only the letters game's settings
            game, cfg = "letters", game
        cfg = cfg if cfg is not None else self._game_cfg(game)
        if game == "scramble":
            recent = getattr(self, "_recent_words", None)
            if recent is None:
                recent = self._recent_words = deque(maxlen=40)       # no word comes back until 40 others were played
            self.round = r = minigames.new_scramble(cfg, recent)
            recent.append(r.word)
            cat = f" — الفئة: {r.category}" if r.category and cfg.get("show_category", True) else ""      # 1.10.0: makes it easier
            await self._send(self._game_ann(cfg) + f"🔀 رتب الحروف: {minigames.tiles_text(r.tiles)}{cat} — أول واحد يكتب الكلمة يفوز! ({int(r.ends - time.time() + 0.5)} ثانية)", why="game")
            self._log_activity("game", f"start:رتب:{''.join(r.tiles)}")
        else:
            self.round = r = minigames.new_round(cfg)
            await self._send(self._game_ann(cfg) + f"🎲 الفئة: {r.cat} — بحرف: {r.letter}. أول واحد يكتب الإجابة الصحيحة يفوز! ({int(r.ends - time.time() + 0.5)} ثانية)", why="game")
            self._log_activity("game", f"start:{r.cat}:{r.letter}")
        self._auto_started()[game] = time.time()       # an automatic round of this game waits its full time again
        self._count_round()                             # counts toward "rounds per stream" (All games)
        self._round_task = asyncio.create_task(self._game_timeout(r))

    async def _game_timeout(self, r) -> None:
        game = getattr(r, "key", "letters")
        if game == "scramble" and self._game_cfg("scramble").get("hint", True):
            await asyncio.sleep(max(0.0, r.hint_at - time.time()))
            if self.round is r and not r.over and not r.hinted:      # halfway: the first letter
                r.hinted = True
                await self._send(f"💡 تلميح: الكلمة تبدأ بحرف «{r.word[0]}»", why="game")
        await asyncio.sleep(max(0.0, r.ends - time.time()))
        if self.round is r and not r.done:
            r.done = True
            self._round_ended()
            cfg = self._game_cfg(game)
            if game == "scramble":
                await self._send(self._game_ann(cfg) + f"⏰ انتهى الوقت! الكلمة كانت «{r.word}»", why="game")
                return
            ex = minigames.examples(r.cat, r.letter, (cfg.get("words") or {}).get(r.cat, []))
            await self._send(self._game_ann(cfg) + "⏰ انتهى الوقت! ما أحد فاز." + (f" أمثلة: {'، '.join(ex)}" if ex else ""), why="game")

    async def _game_win(self, uid, user, word) -> None:
        r = self.round
        if r is None or r.done:
            return
        r.done = True
        self._round_ended()
        if self._round_task:
            self._round_task.cancel()
        game = getattr(r, "key", "letters")
        wins = self.store.get("game_wins") or {}
        n = minigames.add_win(wins, uid, user, game)
        self.store.save("game_wins", wins)
        cfg = self._game_cfg(game)
        tail = "أول فوز له 🥇" if n == 1 else f"هذا فوزه رقم {n}"
        if game == "scramble":
            self._log_activity("game", f"win:رتب:{word}", user)
            await self._send(self._game_ann(cfg) + f"🎉 ‏@{user} رتّب الكلمة «{word}»! " + tail, why="game", user=user)
            return
        self._log_activity("game", f"win:{r.cat}:{word}", user)
        await self._send(self._game_ann(cfg) + f"🎉 ‏@{user} فاز بكلمة «{word}»! " + tail, why="game", user=user)

    @staticmethod
    def _game_ann(cfg) -> str:
        """Rounds, winners and "time's up" are announcements (the highlighted box), unless switched off in the game's settings."""
        return "/announce " if cfg.get("announce", True) else ""

    def game_view(self):
        """The round in progress, for the page (the game card's live box), or None."""
        r = self.round
        if r is None or r.over:
            return None
        now = time.time()
        out = {"game": getattr(r, "key", "letters"), "left": max(0, round(r.ends - now, 1)), "seconds": getattr(r, "seconds", 0) or max(1, round(r.ends - now))}
        if out["game"] == "scramble":
            out["tiles"] = list(r.tiles)
            out["hint"] = r.word[0] if r.hinted else ""
            out["category"] = getattr(r, "category", "") if self._game_cfg("scramble").get("show_category", True) else ""
        else:
            out["cat"], out["letter"] = r.cat, r.letter
        return out

    def _game_auto(self) -> None:
        """Automatic rounds while live: each game every N minutes of its own (its settings; 0 = off), counted from that
        game's last round. Never two rounds at once, and at least a minute after any round ended (no rounds back to back)."""
        if not getattr(self, "is_live", False) or self.store.get("settings").get("paused"):
            return
        if self.round is not None and not self.round.over:
            return
        now = time.time()
        if now - self._last_round_end < 60 and getattr(self, "_auto_last", None) is not None:
            return
        if self._round_block() is not None:             # the round limit or the cooldown (All games) applies here too
            return
        last = self._auto_started()
        due = []
        for game in minigames.GAME_KEYS:
            cfg = self._game_cfg(game)
            every = int(cfg.get("auto_minutes") or 0)
            if cfg.get("enabled") and every and now - last[game] >= every * 60:
                due.append((last[game], game, cfg))
        if due:
            _, game, cfg = min(due, key=lambda d: d[0])      # the game that waited longest goes first
            self._last_round_end = now
            asyncio.create_task(self._game_start(game, cfg))

    def _auto_started(self) -> dict:
        """When each game last had a round (for automatic rounds). Starts at the app's start (or the last round's end)."""
        last = getattr(self, "_auto_last", None)
        if last is None:
            last = self._auto_last = {k: self._last_round_end for k in minigames.GAME_KEYS}
        return last

    async def _manage(self, payload, action, args, user, level, prefix) -> None:
        if action in ("add", "edit") and level < 4 and URLFETCH.search(args):
            await self._send(f"@{user} Only the broadcaster can use $(urlfetch) in a command.", payload)
            return
        work = copy.deepcopy(self.store.get("commands"))
        try:
            if action == "add":
                name = manage.add_command(work, args, prefix)
                msg = f"Command {name} added."
            elif action in ("edit", "options"):
                name = manage.edit_command(work, args, prefix, options_only=(action == "options"))
                msg = f"Command {name} updated."
            else:
                name, whole = manage.delete_command(work, args, prefix)
                msg = f"Command {name} deleted." if whole else f"Alias {name} removed."
                if whole:
                    counters = self.store.get("counters")
                    if counters.pop(f"cmd:{name}", None) is not None:
                        self.store.save("counters", counters)
            if action in ("add", "edit"):
                games = minigames.command_names(self.store.get("games") or {})
                mine = [name] + list((work.get(name) or {}).get("aliases", []))
                clash = next((n for n in mine if n in games), None)
                if clash:          # a mini game would answer first and the command would never work
                    raise CommandError(f"{clash} is a mini game command. Choose another name.")
        except CommandError as e:
            await self._send(f"@{user} {e}", payload)
            return
        self.store.save("commands", work)
        self._log_activity("manage", msg, user)
        await self._send(f"@{user} {msg}", payload)

    # ---------- stream detection ----------

    async def _live_loop(self) -> None:
        while True:
            try:
                TwitchBot._quiet_check(self)        # (works for any bot object, also the tests' minimal ones)
                if hasattr(self, "_game_auto"):
                    self._game_auto()
                stream = None
                async for s in self.fetch_streams(user_ids=[self.owner_id], type="live"):
                    stream = s
                    break
                self.live_fail = 0
                was_live = self.is_live
                self.is_live = stream is not None
                self.viewers = int(getattr(stream, "viewer_count", 0) or 0) if stream is not None else 0
                self.live_since = stream.started_at if stream else None
                try:
                    await self.session.step(stream is not None, self._stream_info(stream))
                except Exception:
                    log.exception("Stream messages failed")
                if self.is_live and not was_live:
                    log.info("Stream went LIVE - bot active")
                elif was_live and not self.is_live:
                    log.info("Stream went offline - bot waiting")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.live_fail += 1
                self._throttle.exception(log, "live", "Live check failed")
                self._login_trouble(sys.exc_info()[1])
            try:   # sleep until the next check, or until Twitch announces that the stream went online or offline
                await asyncio.wait_for(self._live_wake.wait(), timeout=max(15, self.store.get("settings").get("live_check_seconds", 60)))
            except asyncio.TimeoutError:
                pass
            self._live_wake.clear()

    @staticmethod
    def _stream_info(stream) -> dict | None:
        if stream is None:
            return None
        started = getattr(stream, "started_at", None)
        return {"started_at": started.timestamp() if started else None, "title": getattr(stream, "title", "") or "",
                "category": getattr(stream, "game_name", "") or ""}

    async def _follower_total(self):
        """How many followers the channel has right now (None if Twitch will not say). Asked directly (TwitchIO 3's
        PartialUser has no .followers, which is why the "new followers" stream message never worked before 1.7.0)."""
        token = (auth.load_token() or {}).get("access_token") or self.account.get("access_token")
        headers = {"Authorization": f"Bearer {token}", "Client-Id": auth.CLIENT_ID}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get("https://api.twitch.tv/helix/channels/followers", params={"broadcaster_id": str(self.owner_id), "first": "1"}, headers=headers) as r:
                    if r.status != 200:
                        log.warning("Follower total: Twitch answered %s", r.status)
                        return None
                    total = (await r.json()).get("total")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return None
        return int(total) if total is not None else None

    async def event_stream_online(self, payload) -> None:
        self._live_wake.set()

    async def event_stream_offline(self, payload) -> None:
        self._live_wake.set()

    # ---------- timers ----------

    async def _timer_loop(self) -> None:
        last: dict[str, float] = {}
        was_live = False
        while True:
            await asyncio.sleep(10)
            try:
                if self.is_live != was_live:
                    last.clear()  # restart timers' clocks on live/offline change
                    was_live = self.is_live
                if self.store.get("settings").get("paused"):
                    last.clear()   # timers start counting again from zero after Resume
                    continue
                if self.store.get("settings").get("only_when_live", True) and not self.is_live:
                    continue
                now = time.time()
                for t in self.store.get("timers"):
                    if not t.get("enabled", True):
                        continue
                    key = t["name"]
                    if key not in last:
                        last[key] = now
                        continue
                    if now - last[key] >= t["interval_minutes"] * 60:
                        ctx = self._ctx(self.account["login"], counter_key=f"timer:{key}")
                        await self._send(await expand(t["message"], ctx), why="timer:" + key, user="")   # (shown in the Bot tab)
                        last[key] = now
            except asyncio.CancelledError:
                raise
            except Exception:
                self._throttle.exception(log, "timer", "Timer loop error")
                self._login_trouble(sys.exc_info()[1])