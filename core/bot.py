"""The bot core: commands, aliases, variables, timers, blocklist,
permissions, announcements, title/game, stream detection.
Everything is driven by the JSON files in data/."""

import asyncio
import copy
import logging
import re
import time
from collections import deque
from datetime import datetime, timezone

import aiohttp
import twitchio
from twitchio import eventsub
from twitchio.ext import commands

from . import auth, botauth, events, greetings, manage, moderation, notify
from .manage import CommandError
from .store import Store
from .stream import StreamSession
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
    def __init__(self, account: dict, store: Store | None = None, bot_account: dict | None = None):
        # account = your channel account. bot_account = a separate account that writes the replies ("Use a separate bot
        # account" in Settings > Bot); without it the bot talks as your own account, exactly as before.
        self.account = account
        self.bot_account = bot_account or account
        self.separate = bot_account is not None and str(bot_account["user_id"]) != str(account["user_id"])
        self.store = store or Store()
        self.connected = False
        self.live_fail = 0          # live checks that failed in a row (the watchdog warns when timers may be waiting because of it)
        self.last_chat = 0.0        # when a chat message was last heard
        self._live_wake = asyncio.Event()      # Twitch saying "online" or "offline" makes the live check run right now
        self.session = StreamSession(          # the messages for when the stream starts, comes back and ends (Events > Stream)
            self.store, send=lambda text: self._send(text), followers=lambda: self._follower_total(), channel=account["login"],
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

    async def _send(self, text: str, payload=None) -> None:
        """Sends to chat. Text starting with /announce, /announceblue,
        /announcegreen, /announceorange or /announcepurple becomes an announcement."""
        text = text.strip()
        if not text:
            return
        owner = self.create_partialuser(self.owner_id)

        m = ANNOUNCE.match(text)
        if m:
            color = (m.group(1) or "primary").lower()
            body = m.group(2).strip()[:500]
            try:
                await owner.send_announcement(moderator=self.bot_id, message=body, color=color)
                return
            except Exception:
                log.exception("Announcement failed (reconnect Twitch to grant the permission); sending as a normal message")
            text = body

        text = text[:500]
        if payload is not None and not self.separate:
            sent = await payload.respond(text)
        else:   # a separate bot account (or a message with no trigger): say who sends it
            sent = await owner.send_message(text, sender=self.bot_id)
        self._remember(text, sent)

    async def send_test(self) -> str:
        """The dashboard's "Send test message": says hello from the account the replies come from."""
        name = self.bot_account["login"]
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
        if not uid or uid in (str(self.owner_id), str(self.bot_account["user_id"])):
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
        await self._mod_api("DELETE", "moderation/chat", {"message_id": str(payload.id)})
        did = "delete:0"
        if step:
            await self._mod_api("POST", "moderation/bans", {}, {"data": {"user_id": uid, "duration": int(step), "reason": f"{self.LABEL[filt]} filter"}})
            did = f"timeout:{int(step)}"
        elif step == 0:
            lang = "ar" if (self.store.get("ui") or {}).get("language") == "ar" else "en"
            text = (cfg.get("warn_text") or "").strip() or self.WARN[lang][filt]
            await self._send(text.replace("$(user)", str(user)), payload)
            did = "warn:0"
        self._log_activity("moderation", f"{filt}:{did}", user)     # the Logs page turns this into words, in the app's language
        return True

    async def _mod_api(self, method: str, path: str, params: dict, body=None) -> bool:
        """A Twitch moderation call made by whoever moderates: the separate bot account, or the channel account."""
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
        await self._send(await expand(template, ctx))

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
            await self._send(await expand(template, ctx))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Greeting failed")

    # ---------- chat ----------

    async def event_message(self, payload) -> None:
        self.last_chat = time.time()      # proof that chat is arriving (the watchdog quotes it when it has to reconnect)
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
        if self.separate and str(getattr(payload.chatter, "id", "")) == str(self.bot_id):
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

        text = payload.text.strip()
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
            await (self._set_game if action == "game" else self._set_title)(cmd["response"], payload)
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
                log.exception("Live check failed")
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
        """How many followers the channel has right now (None if Twitch will not say)."""
        owner = self.create_partialuser(self.owner_id)
        result = await owner.followers(first=1, token_for=self.owner_id)
        total = getattr(result, "total", None)
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
                        self._log_activity("timer", key)
                        ctx = self._ctx(self.account["login"], counter_key=f"timer:{key}")
                        await self._send(await expand(t["message"], ctx))
                        last[key] = now
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Timer loop error")