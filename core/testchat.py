"""Test chat (1.13.0): try commands, chat tools and event replies inside the app, with nothing sent to Twitch.

A pretend bot (SimBot) runs the REAL bot code (core/bot.py: commands, built-ins, variables, games, greetings, moderation,
Pin first message, event replies) on a SANDBOX copy of the channel's data: it reads the real data, but everything it
saves (counters, wins, who was first, totals, a command added with !cmadd, ...) stays in memory and is thrown away with
Clear. What it would send or do in chat is written into the test chat instead: replies, announcements, deleted messages,
timeouts, pins, title/game changes. Lookups that only READ Twitch (the game, the title, follow dates, account age,
followers) go through the real bot when it is connected, so the answers are real.

The page asks for the chat every second (/api/test), so greetings and game hints that come a few seconds later show up."""

import asyncio
import copy
import itertools
import logging
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from . import pinfirst
from .bot import ANNOUNCE, TwitchBot

log = logging.getLogger("twitchbot.testchat")
ROLES = ("viewer", "subscriber", "vip", "moderator", "broadcaster")
MAX_LINES = 200
EVENT_KEYS = ("follow", "watch_streak", "subscription", "gift_sub", "raid", "hype_train", "bits", "donation", "falkorie_level", "falkorie_streak", "follow_anniversary")
_ids = itertools.count(1)


class _Log:
    """The sandbox's Logs: nothing is written; a moderation filter's action becomes a line in the test chat."""
    items: list = []

    def __init__(self, sim):
        self.sim = sim

    def add(self, kind, name, user="", **kw):
        if kind == "moderation":
            filt, _, did = str(name).partition(":")
            self.sim.note("mod", f=filt, did=did, u=user)

    def recent(self, *a, **k):
        return []


class SandboxStore:
    """Reads the channel's real data; saves stay in memory (thrown away with Clear). `temp` = commands tried without saving."""

    def __init__(self, real, sim):
        self.real, self.mem, self.temp = real, {}, None
        self.channel = getattr(real, "channel", None)
        self.activity = _Log(sim)

    def get(self, name):
        if name == "commands":         # your real commands (edited in the app: seen at once) + what the test changed
            data = copy.deepcopy(self.real.get(name) or {})
            delta = self.mem.get("commands")
            if delta:
                for k in delta["removed"]:
                    data.pop(k, None)
                data.update(copy.deepcopy(delta["set"]))
            if self.temp:
                data.update(copy.deepcopy(self.temp))
            return data
        return copy.deepcopy(self.mem[name] if name in self.mem else self.real.get(name))

    def save(self, name, data, allow_empty=False, by="you"):
        if name == "commands":
            real = self.real.get(name) or {}
            data = {k: v for k, v in (data or {}).items() if not (self.temp and k in self.temp)}
            self.mem[name] = {"set": copy.deepcopy({k: v for k, v in data.items() if real.get(k) != v}),
                              "removed": [k for k in real if k not in data]}
            return
        self.mem[name] = copy.deepcopy(data)


class SimBot(TwitchBot):
    count_stats = False             # 1.14.0: the Test chat never counts in Stream stats
    _cb_on = False                  # 1.18.0: the Test chat never reaches the Chat box on your stream
    pin_window_applies = False      # 1.14.0: Pin first message's "first minutes" don't apply in Test chat (try it any time)
    owner_id = None          # (plain values here: the real ones come from TwitchIO, which a pretend bot never starts)

    async def _make_clip(self) -> tuple:
        """1.15.0 $(clip): the Test chat never makes a real clip (nothing reaches Twitch): a pretend link instead."""
        return "https://clips.twitch.tv/(test-clip)", None
    bot_id = None

    def __init__(self, account: dict, store, live=None):
        self._fqpn_init(account, SandboxStore(store, self))
        self.owner_id = self.bot_id = str(account.get("user_id") or "0")
        self.writer_id = "sim-bot"
        self.live = live
        self.lines: list = []
        self.connected = True
        self.set_live(True)
        self.bot_name = (getattr(getattr(live, "sender", None), "login", "") or account.get("login") or "bot")

    # ---------- the test chat ----------
    def add(self, **line) -> dict:
        line.setdefault("id", next(_ids))
        line.setdefault("at", time.time())
        self.lines.append(line)
        del self.lines[:-MAX_LINES]
        return line

    def note(self, code: str, **values) -> None:
        self.add(kind="note", code=code, v=values)

    def set_live(self, on: bool) -> None:
        live = self.live
        self.is_live = bool(on)
        real = getattr(live, "live_since", None) if live is not None else None
        self.live_since = (real or datetime.now(timezone.utc) - timedelta(hours=1, minutes=12)) if on else None
        self.viewers = int(getattr(live, "viewers", 0) or 0) if live is not None else 0

    def view(self) -> dict:
        return {"lines": self.lines[-MAX_LINES:], "live": self.is_live, "bot": self.bot_name,
                "paused": bool(self.store.get("settings").get("paused")), "connected": self.live is not None}

    @staticmethod
    def chatter(name: str, role: str):
        name = "".join(c for c in str(name or "") if c.isalnum() or c == "_")[:25] or "test_viewer"
        role = role if role in ROLES else "viewer"
        lv = ROLES.index(role)
        return NS(name=name.lower(), display_name=name, id="sim:" + name.lower(), broadcaster=lv == 4, moderator=lv == 3,
                  vip=lv == 2, subscriber=lv == 1)

    async def say(self, name: str, role: str, text: str, temp=None, first: bool = False) -> dict:
        """One chat message from a pretend viewer, answered by the real bot code."""
        chatter = self.chatter(name, role)
        if role == "broadcaster":
            chatter.id = self.owner_id
        text = str(text or "").strip()[:500]
        line = self.add(kind="chat", who=chatter.display_name, role=role, text=text)
        payload = NS(id=f"t{line['id']}", text=text, chatter=chatter, source_broadcaster=None, fragments=[], cheer=None,
                     chatter_is_anonymous=False, _first=bool(first),      # 1.18.0: "First time" = their first message ever
                     badges=[NS(set_id=b, id="1") for b in {"subscriber": ["subscriber"], "vip": ["vip"], "moderator": ["moderator"],
                                                             "broadcaster": ["broadcaster"]}.get(role, [])])   # (a sub / VIP / mod is never "new")
        before, greets, welcomes = len(self.lines), len(self._greet_tasks), getattr(self, "_welcomes", 0)
        self.store.temp = temp or None
        try:
            if self.store.get("settings").get("paused"):
                self.note("paused")
            else:
                await self.event_message(payload)
        except Exception as e:
            log.exception("Test chat: the message failed")
            self.note("error", e=str(e)[:200])
        finally:
            self.store.temp = None
        if getattr(self, "_welcomes", 0) > welcomes:
            self.note("welcome")
        elif len(self._greet_tasks) > greets:
            self.note("greet")
        elif len(self.lines) == before:
            self.note("noreply")
        return line

    async def fake_event(self, key: str, value, name: str, currency: str = "USD") -> None:
        """A pretend Twitch event or donation, answered exactly like a real one ({total} counted in the sandbox)."""
        if key not in EVENT_KEYS:
            raise ValueError("Unknown event")
        chatter = self.chatter(name, "viewer")
        user, login = chatter.display_name, chatter.name
        try:
            n = float(value)
        except (TypeError, ValueError):
            n = 1
        n = max(0.0, min(n, 1_000_000))
        whole = max(1, int(n))
        self.add(kind="event", key=key, who=user, n=(round(n, 2) if key == "donation" else whole))
        before = len(self.lines)
        if self.store.get("settings").get("paused"):
            self.note("paused")
            return
        if key == "follow":
            if not hasattr(self, "_fake_follows"):
                self._fake_follows = {}
            self._fake_follows[str(login).lower()] = datetime.now(timezone.utc)    # 1.18.0: "just followed" for First-time chatters
            if await self._on_follow(user, login):    # 1.18.0: the same wait as a real follow (First-time chatters)
                self.note("followhold", s=self.FOLLOW_HOLD)
                return
        elif key == "watch_streak":
            await self._fire_event("watch_streak", whole, user, login)
        elif key == "subscription":
            await self._fire_event("subscription", whole, user, login, {"tier": "Tier 1", "months": whole, "total": whole, "message": ""})
        elif key == "gift_sub":
            await self._fire_event("gift_sub", whole, user, login, {"gifts": whole, "tier": "Tier 1", "total": self._add_total("gift_sub", login, whole)})
        elif key == "raid":
            await self._fire_event("raid", whole, user, login, {"raider": user, "viewers": whole})
        elif key == "hype_train":
            await self._fire_event("hype_train", whole, self.account["login"], "", {"level": whole})
        elif key == "bits":
            await self._fire_event("bits", whole, user, login, {"bits": whole, "message": "", "total": self._add_total("bits", login, whole)})
        elif key == "follow_anniversary":                         # 1.18.0: as if they chatted on their follow anniversary
            await self._fire_event(key, whole, user, login, {"years": whole})
        elif key in ("falkorie_level", "falkorie_streak"):      # 1.17.1: as if Falkorie wrote it in chat
            await self._fire_event(key, whole, user, login, {"level": whole} if key == "falkorie_level" else {"streak": whole})
        elif key == "donation":
            await self.on_donation({"service": "test", "id": None, "user": user, "amount": round(n, 2), "currency": (currency or "USD").upper()[:8],
                                    "message": "", "test": False})
        if len(self.lines) == before:
            self.note("noevent", k=key)

    async def try_text(self, text: str, name: str, role: str, query: str = "") -> str:
        """What a reply text becomes for this pretend viewer (the Variables helper). Nothing is said in the test chat."""
        from .variables import expand
        chatter = self.chatter(name, role)
        ctx = self._ctx(chatter.display_name, str(query or "")[:400], counter_key="try", chatter=chatter)
        return (await expand(str(text or "")[:500], ctx))[:500]

    def clear(self) -> None:
        for t in list(self._greet_tasks) + ([self._round_task] if self._round_task else []):
            t.cancel()
        self.round = None
        self.lines.clear()
        self.store.mem.clear()
        self._cooldowns.clear()
        self._chatters.clear()
        self._chat_info.clear()

    # ---------- what would go to Twitch ----------
    async def _send(self, text: str, payload=None, why=None, user=None, reply: bool = False) -> None:
        text = str(text or "").strip()
        if not text:
            return
        m = ANNOUNCE.match(text)
        to = getattr(getattr(payload, "chatter", None), "display_name", None) if reply else None
        if m:
            self.add(kind="ann", who=self.bot_name, color=(m.group(1) or "primary").lower(), text=m.group(2).strip()[:500])
        else:
            self.add(kind="bot", who=self.bot_name, text=text[:500], reply=to)

    async def _mod_api(self, method: str, path: str, params: dict, body=None) -> bool:
        if method == "DELETE" and path == "moderation/chat":
            mid = str(params.get("message_id", ""))
            for ln in self.lines:
                if f"t{ln.get('id')}" == mid:
                    ln["deleted"] = True
        elif method == "POST" and path == "moderation/bans":
            d = (body or {}).get("data") or {}
            self.note("timeout", s=int(d.get("duration") or 0))
        return True

    async def _pin(self, message_id: str, seconds: int) -> bool:
        for ln in self.lines:
            if f"t{ln.get('id')}" == message_id:
                ln["pinned"] = True
        self.note("pin", s=int(seconds or 0))
        return True

    async def _set_title(self, text: str, payload) -> None:
        self.note("title", t=" ".join(str(text).split())[:140])

    async def _set_game(self, query: str, payload) -> None:
        self.note("game", t=" ".join(str(query).split())[:100])

    def _log_activity(self, *a, **k) -> None:
        pass

    def _log_bot(self, *a, **k) -> None:
        pass

    def _log_chat(self, payload) -> None:
        pass

    def _notify_event(self, *a, **k) -> None:
        pass                                  # no desktop pop-up for a pretend event

    def _is_own_echo(self, payload) -> bool:
        return False

    def _stream_id(self):
        return "test-stream" if self.is_live else None

    def _on_cooldown(self, key: str, seconds: float) -> bool:
        if TwitchBot._on_cooldown(self, key, seconds):
            self.note("cooldown", s=int(seconds))      # on Twitch it would wait: the test answers anyway
            self._cooldowns[key] = 0
            self._cooldowns[key] = time.time()
        return False

    def _is_blocked(self, payload) -> bool:
        if TwitchBot._is_blocked(self, payload):
            self.note("blocked", u=payload.chatter.display_name)
            return True
        return False

    async def _custom(self, payload, owner, rest, user, level) -> None:
        from . import manage
        from .bot import PERMISSION_LEVELS
        cmd = self.store.get("commands").get(owner) or {}
        if cmd and cmd.get("enabled", True) is False:
            self.note("off", c=owner)
            return
        if cmd and cmd.get("action") != pinfirst.ACTION and level < PERMISSION_LEVELS.get(manage.effective_permission(cmd), 0):
            self.note("level", c=owner, l=manage.effective_permission(cmd))
            return
        await TwitchBot._custom(self, payload, owner, rest, user, level)

    # ---------- lookups that only READ Twitch: the real bot answers them ----------
    async def _game(self) -> str:
        return await self.live._game() if self.live is not None else "(no game set)"

    async def _title(self) -> str:
        return await self.live._title() if self.live is not None else "(no title set)"

    async def _followed_at(self, chatter_id: str):
        login = str(chatter_id).split(":", 1)[-1]
        hit = getattr(self, "_fake_follows", {}).get(login.lower())
        if hit:                                     # 1.18.0: followed here with "Pretend an event > Follow"
            return hit
        live = self.live
        if live is None or not login:
            return None
        users = await live.fetch_users(logins=[login])
        return await live._followed_at(str(users[0].id)) if users else None

    async def _followed_of(self, login: str):
        if self.live is None:
            return True, None
        return await self.live._followed_of(login)

    async def _account_created(self, login, chatter):
        if self.live is None:
            return None
        return await self.live._account_created(login or getattr(chatter, "name", None), None)

    async def _followers_cached(self):
        return await self.live._followers_cached() if self.live is not None else None


def get(state, store) -> SimBot:
    """The channel's Test chat (made on first use; it follows the real bot when that one restarts)."""
    live = state.get("bot")
    sim = state.get("test_sim")
    if sim is None:
        acct = getattr(live, "account", None) or {"login": state.get("account") or "you", "user_id": state.get("account_id") or "0"}
        sim = SimBot(acct, store, live)
        state["test_sim"] = sim
    elif sim.live is not live:
        sim.live = live
        sim.bot_name = getattr(getattr(live, "sender", None), "login", "") or sim.account.get("login") or sim.bot_name
    return sim
