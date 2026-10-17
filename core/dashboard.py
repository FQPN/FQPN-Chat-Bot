"""Local web dashboard (shown only inside the app window; it listens on this PC only, usually on port 5000).

It only edits the JSON files through Store. The bot re-reads those files
automatically, so changes apply without restarting anything."""

import asyncio
import copy
import os
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiohttp import web

from . import accounts, auth, botauth, desktop, events, greetings, manage, minigames, moderation, notify, publiclist, support, updater
from .store import EmptySaveRefused, Store

log = logging.getLogger("twitchbot.dashboard")

HOST = "127.0.0.1"   # this PC only - never exposed to the network
PORT = 5000          # the first port tried. Another program (a Flask app, for example) may already use it: start() then takes
PORT_TRIES = 25      # the next free one, and PORT is updated to the one really in use.
PORT_FILE = None     # the launcher sets a file here; the port in use is written to it so a second launch can find this copy
ready = threading.Event()   # set once the server is listening (or has failed): the launcher waits for it
start_error = None


def origin_ok(origin: str, port: int) -> bool:
    """True if a request really comes from this dashboard's own page (the same port: another local website is not)."""
    return origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}")


async def bind_first_free(first: int, tries: int, bind) -> int:
    """Starts listening on the first free port from `first`. bind(port) is a coroutine that raises OSError when the
    port is busy. Returns the port that worked."""
    last = None
    for port in range(first, first + tries):
        try:
            await bind(port)
            return port
        except OSError as e:
            last = e
    raise OSError(f"No free port between {first} and {first + tries - 1}") from last
PAGE = Path(__file__).resolve().parent / "dashboard.html"
ICON = Path(__file__).resolve().parent.parent / "icon.ico"   # next to main.py (and inside the installed program folder)
PERMISSIONS = ("everyone", "subscriber", "vip", "moderator", "broadcaster")
SECTIONS = ("commands", "timers", "greetings", "events", "blocklist", "settings", "ui", "prefs", "stream", "moderation", "games", "game_wins")
_LOGIN = re.compile(r"[a-z0-9_]{1,25}")


class ValidationError(Exception):
    pass


# ---------- Twitch connect / disconnect (used by the dashboard buttons) ----------

async def _login(state: dict, role: str = "streamer") -> None:
    bot_role = role == "bot"
    login = state["bot_login"] if bot_role else state["login"]
    login.update(status="waiting", code=None, uri=None, message="")

    def on_code(code, uri):
        login.update(code=code, uri=uri)
        print(f"\nGo to {uri} and enter code: {code}\n")

    try:
        if bot_role:    # never opens the browser by itself: it is usually logged in as YOU, not as the bot account
            await botauth.device_login(on_code=on_code)
            account = await botauth.get_account()
            state["bot_account"] = account["login"] if account else None
            state["bot_mod"] = None
            login.update(status="idle", code=None, uri=None, message="")
            store = state.get("store")
            if store is not None and store.get("settings").get("separate_bot"):
                restart_bot(state)   # the option is on: (re)start the bot so it talks from the new bot account
        else:
            await auth.device_login(on_code=on_code, open_browser=True)
            login.update(status="idle", code=None, uri=None, message="")
            state["wake"].set()          # tells main.py to start the bot
    except asyncio.CancelledError:
        login.update(status="idle", code=None, uri=None, message="")
        raise
    except auth.AuthError as e:
        login.update(status="error", code=None, uri=None, message=str(e))
    except Exception:
        log.exception("Twitch login failed")
        login.update(status="error", code=None, uri=None, message="Could not reach Twitch. Try again.")


async def fetch_avatar(account: dict) -> str | None:
    """The account's Twitch profile picture URL, or None if it can't be read."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(
                "https://api.twitch.tv/helix/users",
                params={"id": account["user_id"]},
                headers={"Authorization": f"Bearer {account['access_token']}", "Client-Id": auth.CLIENT_ID},
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
        url = data["data"][0]["profile_image_url"]
        return url if isinstance(url, str) and url.startswith("https://") else None
    except Exception:
        log.exception("Could not load the Twitch profile picture")
        return None


async def load_avatar(state: dict, account: dict) -> None:
    state["avatar"] = await fetch_avatar(account)


async def _register_bot(state) -> None:
    """"Add bot account" (1.12.0): the bot's Twitch login, the browser opened on Twitch's activation page, then the bot
    account joins the shared list. Every step is in state["bot_add"] for the page: waiting (code) / connected / error."""
    import webbrowser
    state["bot_add"] = {"status": "waiting", "code": None, "uri": None, "login": "", "message": ""}
    opened = False
    while True:
        bl = state.get("bot_login") or {}
        if bl.get("code") and not opened:
            opened = True
            state["bot_add"].update(code=bl.get("code"), uri=bl.get("uri"))
            try:   # Twitch's page for the code (the page says to sign in as the BOT, not your main account)
                await asyncio.to_thread(webbrowser.open, bl.get("uri") or "https://www.twitch.tv/activate")
            except Exception:
                log.exception("Could not open the browser")
        task = state.get("bot_login_task")
        if task is not None and task.done() and bl.get("status") != "waiting":
            break
        await asyncio.sleep(0.4)
    bl = state.get("bot_login") or {}
    if bl.get("status") == "error":
        state["bot_add"] = {"status": "error", "message": bl.get("message") or "The Twitch login failed. Try again."}
        return
    acc = await botauth.get_account()
    if not acc:
        state["bot_add"] = {"status": "error", "message": "The Twitch login didn't finish (cancelled or the code expired). Try again."}
        return
    reg = accounts.load()
    cid = str(accounts.current_channel())
    if reg is None:
        state["bot_add"] = {"status": "error", "message": "This app runs a single channel."}
        return
    if str(acc["user_id"]) in [c["id"] for c in reg["channels"]]:
        state["bot_add"] = {"status": "error", "message": f"{acc['login']} is one of your channels, not a bot account. Sign in with the bot account (a private window helps)."}
        return
    bid = str(acc["user_id"])
    accounts.bot_token_file(bid).parent.mkdir(parents=True, exist_ok=True)
    accounts._copy_checked(botauth.token_file(), accounts.bot_token_file(bid))
    if bid not in [b["id"] for b in reg["bots"]]:
        reg["bots"].append({"id": bid, "login": acc["login"], "added": int(time.time())})
    accounts.save(reg)
    from . import botsender
    botsender.forget(bid)              # (a fresh login: the next send loads it)
    state["bot_add"] = {"status": "connected", "login": acc["login"], "id": bid}
    log.info("Added the bot account %s (choose it in Who sends this channel's replies)", acc["login"])


def start_login(state: dict, role: str = "streamer") -> None:
    key, task_key = ("bot_login", "bot_login_task") if role == "bot" else ("login", "login_task")
    login = state.setdefault(key, {"status": "idle"})
    if login.get("status") == "waiting":
        return
    state[task_key] = asyncio.create_task(_login(state, role))


def restart_bot(state: dict) -> None:
    """Starts the bot again at once, so a changed setting (separate bot account on/off, a new bot account) takes effect.
    main.py reads the settings each time it starts the bot."""
    state["restart"] = True
    wake = state.get("wake")
    if wake is not None:
        wake.set()
    bot = state.get("bot")
    if bot is not None:
        state["close_task"] = asyncio.create_task(bot.close())


def channels_info(state):
    """The channels for the page (None when the app runs a single channel the old way, or in tests): who each one is,
    whether its bot runs, and WHO SENDS its replies (its own account, or which bot account)."""
    runtimes = state.get("runtimes") if hasattr(state, "get") else None
    if not runtimes or accounts.load() is None and "pending" not in runtimes:
        return None
    out = []
    for cid, rt in runtimes.items():
        st = rt.state
        bot = st.get("bot")
        reg = accounts.load()
        entry = next((c for c in (reg or {}).get("channels", []) if c.get("id") == str(cid)), None)
        if entry is not None:          # 1.12.0: who sends comes from the shared bot list
            sid = entry.get("sender") or "own"
            blogin = next((b.get("login", "") for b in reg.get("bots", []) if b.get("id") == sid), "") if sid != "own" else ""
            sender, sender_ok = blogin, not (bot is not None and getattr(bot, "sender_problem", ""))
        else:
            separate = bool(rt.store.get("settings").get("separate_bot")) if cid != "pending" else False
            sender, sender_ok = ((st.get("bot_account") or "") if separate else ""), (bool(st.get("bot_account")) if separate else True)
        out.append({"id": str(cid), "login": st.get("account") or (entry or {}).get("login", ""), "avatar": st.get("avatar") or "",
                    "pending": cid == "pending", "running": bool(bot is not None and getattr(bot, "connected", False)),
                    "live": bool(bot is not None and getattr(bot, "is_live", False)),
                    "sender": sender,                     # "" = the channel's own account
                    "sender_ok": sender_ok, "note": (entry or {}).get("sender_note")})
    return {"active": str(accounts.ACTIVE["id"]), "list": out}


def bots_info(state):
    """1.12.0, the Bot accounts page: every bot account and the channels it sends for; every channel and its sender."""
    reg = accounts.load()
    if reg is None:
        return None
    runtimes = state.get("runtimes") or {}
    def login_of(c):
        rt = runtimes.get(c.get("id"))
        return (rt.state.get("account") if rt else "") or c.get("login", "")
    chans = [{"id": c["id"], "login": login_of(c), "sender": c.get("sender") or "own", "note": c.get("sender_note")} for c in reg["channels"]]
    bots = [{"id": b["id"], "login": b.get("login", ""), "channels": [c["id"] for c in chans if c["sender"] == b["id"]]} for b in reg.get("bots", [])]
    return {"active": str(accounts.ACTIVE["id"]), "channels": chans, "bots": bots}


def game_command_clash(games, commands):
    """A plain reason when a game command and one of your own commands have the same name, else None. The game would
    answer first and your command would silently stop working, so the save is refused instead."""
    used = manage.names_in_use(commands or {})
    for name in minigames.command_names(games or {}):
        if name in used:
            return f"{name} is both a mini game command and your command {used[name]}. Rename one of them."
    return None


def keep_tour_flag(section: str, raw, store: Store):
    """A save of the appearance settings that does not mention the tour or the checklist keeps the stored values
    (so neither of them comes back by mistake)."""
    if section == "ui" and isinstance(raw, dict):
        stored, raw = store.get("ui"), dict(raw)
        for key in ("tourDone", "gsDone"):
            if key not in raw:
                raw[key] = bool(stored.get(key, False))
        if "wnSeen" not in raw:
            raw["wnSeen"] = str(stored.get("wnSeen", ""))          # the last version whose "What's new" was seen (1.8.0)
    return raw


def publist_info(state: dict) -> dict:
    """Where the public command list stands, for the page: off | nosite | login | waiting | saving | ok | offline | error."""
    p = state.get("publist") or {}
    return {"state": p.get("state", "off"), "url": p.get("url", ""), "error": p.get("error", ""), "at": p.get("at"),
            "site": publiclist.SITE}


def health_info(state: dict) -> dict:
    """What the watchdog says about the bot's connection, for the page (never anything private)."""
    h = state.get("health") or {}
    return {"state": h.get("state", "ok"), "detail": h.get("detail", ""), "warn": h.get("warn", ""),
            "since": h.get("since"), "restarts": h.get("restarts", 0)}


def donation_status(state: dict) -> dict:
    """Streamlabs / StreamElements connection status for the page. Never contains a token."""
    manager = state.get("donations")
    if manager is None:
        return {"streamlabs": {"state": "none", "detail": "", "account": ""},
                "streamelements": {"state": "none", "detail": "", "account": ""}, "encrypted": False}
    return manager.public()


def bot_account_info(state: dict, settings: dict) -> dict:
    """What the dashboard shows about the separate bot account."""
    bl = state.get("bot_login") or {"status": "idle"}
    login = state.get("bot_account")
    if bl.get("status") == "waiting":
        st = "connecting"
    elif login:
        st = "connected"
    else:
        st = "none"
    bot = state.get("bot")
    return {
        "enabled": bool(settings.get("separate_bot")),
        "state": st,
        "login": login,
        "is_mod": (state.get("bot_mod") or {}).get("is_mod"),
        "running": bool(bot and getattr(bot, "separate", False) and bot.connected),
        "code": bl.get("code"),
        "uri": bl.get("uri"),
        "error": bl.get("message") if bl.get("status") == "error" else None,
        "problem": botauth.last_problem,
    }


async def refresh_bot_mod(state: dict) -> None:
    """Asks Twitch whether the bot account is a moderator of your channel."""
    if state.get("mod_busy"):
        return
    owner = state.get("account_id")
    if not owner or not state.get("bot_account"):
        state["bot_mod"] = None
        return
    state["mod_busy"] = True
    try:
        state["bot_mod"] = {"is_mod": await botauth.is_moderator(owner), "at": time.time()}
    except Exception:
        log.exception("Could not check whether the bot account is a moderator")
        state["bot_mod"] = {"is_mod": None, "at": time.time()}
    finally:
        state["mod_busy"] = False


# ---------- validation ----------

def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v, what: str, max_len: int = 500, required: bool = True) -> str:      # 500 = Twitch's limit for a chat message (1.12.0, was 450)
    if not isinstance(v, str):
        raise ValidationError(f"{what} must be text.")
    v = v.strip()
    if required and not v:
        raise ValidationError(f"{what} can't be empty.")
    if len(v) > max_len:
        raise ValidationError(f"{what} is too long (max {max_len} characters).")
    return v


def _number(v, what: str, lo: float, hi: float = 100000):
    if not _is_num(v) or not lo <= v <= hi:
        raise ValidationError(f"{what} must be a number between {lo} and {hi}.")
    return v


def _bool(v, what: str) -> bool:
    if not isinstance(v, bool):
        raise ValidationError(f"{what} must be on or off.")
    return v


def validate(section: str, data, prefix: str = "!"):
    if section == "commands":
        if not isinstance(data, dict):
            raise ValidationError("Commands must be a list.")
        out = {}
        for name, c in data.items():
            _text(name, "Command name", 60)
            try:
                name = manage.clean_name(name)
            except manage.CommandError as e:
                raise ValidationError(str(e))
            if not isinstance(c, dict):
                raise ValidationError(f"Command '{name}' is invalid.")
            raw_aliases = c.get("aliases", [])
            if not isinstance(raw_aliases, list):
                raise ValidationError(f"Aliases for '{name}' must be a list.")
            aliases = []
            for a in raw_aliases:
                a = _text(a, f"Alias for '{name}'", 60, required=False)
                if not a:
                    continue
                try:
                    a = manage.clean_name(a)
                except manage.CommandError as e:
                    raise ValidationError(str(e))
                if a not in aliases:
                    aliases.append(a)
            if c.get("permission") not in PERMISSIONS:
                raise ValidationError(f"Command '{name}' has an unknown permission.")
            action = c.get("action", "text")
            if action not in manage.ACTIONS:
                raise ValidationError(f"Command '{name}' has an unknown reply type.")
            if action != "text" and len(str(c.get("response") or "").strip()) > manage.ACTION_MAX[action]:
                raise ValidationError(f"The {'game name' if action == 'game' else 'title'} of '{name}' can be at most {manage.ACTION_MAX[action]} characters.")
            out[name] = {
                "response": _text(c.get("response"), f"Response for '{name}'"),
                "permission": c["permission"],
                "cooldown": _number(c.get("cooldown"), f"Cooldown for '{name}'", 0, 86400),
                "enabled": _bool(c.get("enabled"), f"Enabled for '{name}'"),
                "aliases": aliases,
            }
            if action != "text":
                out[name]["action"] = action      # only shortcuts carry it, so plain commands stay exactly as before
        used = {}
        for n, c in out.items():
            for key in [n, *c["aliases"]]:
                if manage.is_reserved(key):
                    raise ValidationError(f"'{key}' is a built-in command and can't be used as a name.")
                if key in used:
                    raise ValidationError(f"'{key}' is used by more than one command.")
                used[key] = n
        return out

    if section == "timers":
        if not isinstance(data, list):
            raise ValidationError("Timers must be a list.")
        out, seen = [], set()
        for t in data:
            name = _text(t.get("name"), "Timer name", 40)
            if name.lower() in seen:
                raise ValidationError(f"Two timers are named '{name}'.")
            seen.add(name.lower())
            out.append({
                "name": name,
                "message": _text(t.get("message"), f"Message for '{name}'"),
                "interval_minutes": _number(t.get("interval_minutes"), f"Interval for '{name}'", 1, 1440),
                "enabled": _bool(t.get("enabled"), f"Enabled for '{name}'"),
            })
        return out

    if section == "events":
        if not isinstance(data, dict):
            raise ValidationError("Events are invalid.")
        out = {}
        for key in events.EVENT_KEYS:
            ev = data.get(key)
            if ev is None:
                continue
            if not isinstance(ev, dict):
                raise ValidationError(f"The {key.replace('_', ' ')} settings are invalid.")
            raw = ev.get("tiers")
            if raw is None and "response" in ev:    # the old single-reply format
                raw = [{"min": ev.get("min_streak", 1), "response": ev["response"]}]
            if not isinstance(raw, list) or not raw:
                raise ValidationError(f"Add at least one reply for {key.replace('_', ' ')}.")
            if len(raw) > 12:
                raise ValidationError("Too many replies for one event (the most is 12).")
            if key in events.SINGLE:        # a follow has one reply; extra ones are ignored
                raw = raw[:1]
            tiers, seen = [], set()
            for t in raw:
                if not isinstance(t, dict):
                    raise ValidationError("A reply is invalid.")
                low = _number(t.get("min", 0), "The 'from' number", 0, 1000000)
                low = round(float(low), 2) if key in events.DECIMAL else int(low)      # a donation can have cents
                if key in events.SINGLE:
                    low = 0
                if low in seen:
                    raise ValidationError(f"Two replies start from {low}. Each one needs a different number.")
                seen.add(low)
                tiers.append({"min": low, "response": _text(t.get("response"), "Reply", 500)})
            tiers.sort(key=lambda t: t["min"])
            out[key] = {"enabled": _bool(ev.get("enabled", True), f"{key.replace('_', ' ')} reply"), "tiers": tiers}
        return out

    if section == "greetings":
        if not isinstance(data, dict):
            raise ValidationError("Greetings are invalid.")
        raw_users = data.get("users", [])
        if not isinstance(raw_users, list):
            raise ValidationError("Greetings must be a list.")
        if len(raw_users) > 200:
            raise ValidationError("Too many people (the most is 200).")
        users, seen = [], set()
        for g in raw_users:
            if not isinstance(g, dict):
                raise ValidationError("A greeting is invalid.")
            user = _text(g.get("user"), "Username", 40).lstrip("@").strip().lower()
            if not _LOGIN.fullmatch(user):
                raise ValidationError(f"'{user}' isn't a Twitch username (letters, numbers and underscores only).")
            if user in seen:
                raise ValidationError(f"{user} already has a greeting. Add more messages to it instead.")
            seen.add(user)
            raw_msgs = g.get("messages")
            if not isinstance(raw_msgs, list):
                raise ValidationError(f"Messages for '{user}' must be a list.")
            msgs = []
            for m in raw_msgs:
                m = _text(m, f"Message for '{user}'", 500, required=False)
                if m and m not in msgs:
                    msgs.append(m)
            if not msgs:
                raise ValidationError(f"Add at least one message for '{user}'.")
            if len(msgs) > 30:
                raise ValidationError(f"Too many messages for '{user}' (the most is 30).")
            users.append({"user": user, "messages": msgs, "enabled": _bool(g.get("enabled", True), f"Enabled for '{user}'")})
        return {"enabled": _bool(data.get("enabled", True), "Greetings"), "users": users}

    if section == "blocklist":
        if not isinstance(data, dict):
            raise ValidationError("Blocklist is invalid.")
        out = {}
        for key in ("users", "words"):
            items = data.get(key, [])
            if not isinstance(items, list):
                raise ValidationError(f"Blocked {key} must be a list.")
            clean = []
            for x in items:
                x = _text(x, f"Blocked {key[:-1]}", 100, required=False)
                if x and x.lower() not in (c.lower() for c in clean):
                    clean.append(x)
            out[key] = clean
        return out

    if section == "settings":
        if not isinstance(data, dict):
            raise ValidationError("Settings are invalid.")
        url = _text(data.get("commands_url", ""), "Commands page link", 300, required=False)
        if url and not url.lower().startswith(("http://", "https://")):
            raise ValidationError("The commands page link must start with http:// or https://")
        hidden = data.get("public_hidden", [])
        if not isinstance(hidden, list) or len(hidden) > 1000:
            raise ValidationError("The commands left off the public list must be a list.")
        hidden_clean = []
        for x in hidden:
            x = _text(x, "Command name", 60, required=False)
            if x and x not in hidden_clean:
                hidden_clean.append(x)
        off = data.get("disabled_builtins", [])
        if not isinstance(off, list) or any(x not in manage.BUILTIN_KEYS for x in off):
            raise ValidationError("Choose built-in commands from the list.")
        return {
            "only_when_live": _bool(data.get("only_when_live"), "Only when live"),
            "paused": _bool(data.get("paused", False), "Paused"),
            "start_active": _bool(data.get("start_active", True), "Start the bot when the app opens"),
            "live_check_seconds": int(_number(data.get("live_check_seconds"), "Live check interval", 15, 3600)),
            "commands_url": url,
            "disabled_builtins": sorted(set(off)),
            "separate_bot": _bool(data.get("separate_bot", False), "Use a separate bot account"),
            "public_list": _bool(data.get("public_list", False), "Public command list"),
            "public_hidden": hidden_clean,
        }

    if section == "stream":
        if not isinstance(data, dict):
            raise ValidationError("The stream messages are invalid.")
        out = {"enabled": _bool(data.get("enabled", True), "The stream messages switch")}   # older files have no master switch: on
        for kind in ("start", "followers", "resume", "end"):
            c = data.get(kind)
            if not isinstance(c, dict):
                raise ValidationError(f"The '{kind}' stream message is invalid.")
            out[kind] = {"enabled": _bool(c.get("enabled", False), f"The '{kind}' stream message switch"),
                         "text": _text(c.get("text", ""), f"The text of the '{kind}' stream message", 500, required=False)}
        out["end_after_minutes"] = int(_number(data.get("end_after_minutes", 2), "Minutes offline before the stream counts as ended", 1, 30))
        out["resume_within_minutes"] = int(_number(data.get("resume_within_minutes", 15), "Minutes to come back and continue the stream", 1, 120))
        return out

    if section == "games":
        if not isinstance(data, dict) or not all(isinstance(data.get(k, {}), dict) for k in minigames.GAME_KEYS):
            raise ValidationError("The mini games settings are invalid.")
        if "shared" in data and not isinstance(data["shared"], dict):
            raise ValidationError("The mini games settings are invalid.")
        data = copy.deepcopy(data)
        minigames.upgrade_games(data)            # a save in the pre-1.9.0 shape (one name per command) still works
        c, sc, sh = data.get("letters", {}), data.get("scramble", {}), data.get("shared", {})
        if not isinstance(sh, dict):
            raise ValidationError("The mini games settings are invalid.")
        dflt = minigames.defaults()
        found = {"letters": {}, "scramble": {}, "shared": {}}
        seen = {}
        for part, fields in minigames.GAME_CMDS.items():
            src = {"letters": c, "scramble": sc, "shared": sh}[part]
            for k in fields:
                raw = src.get(k, dflt[part][k])
                if isinstance(raw, str):
                    raw = [raw]
                if not isinstance(raw, list):
                    raise ValidationError("A game command's names couldn't be read.")
                names = []
                for v in raw:
                    v = _text(v, "Command name", 30).strip()
                    if " " in v:
                        raise ValidationError("A game command name is one word, like !حروف.")
                    v = minigames.cmd_key(v)
                    if manage.is_reserved(v):
                        raise ValidationError(f"{v} is a built-in command and can't be a game command.")
                    if v in seen or v in names:          # every game command name must be different, across the games too
                        raise ValidationError(f"Two game commands are both called {v}.")
                    names.append(v)
                if not names:
                    raise ValidationError("Every game command needs at least one name.")
                if len(names) > minigames.MAX_ALIASES:
                    raise ValidationError(f"A game command can have at most {minigames.MAX_ALIASES} names.")
                for v in names:
                    seen[v] = True
                found[part][k] = names
        cmds, scmds = found["letters"], found["scramble"]
        if c.get("who_starts", "moderator") not in minigames.WHO:
            raise ValidationError("Choose who can start a round.")
        cats = [x for x in (c.get("categories") or []) if x in minigames.CATEGORIES]
        if not cats:
            raise ValidationError("Choose at least one category.")
        letters = "".join(dict.fromkeys(ch for ch in str(c.get("letters", "")) if "\u0621" <= ch <= "\u064a"))
        if not letters:
            raise ValidationError("Choose at least one Arabic letter.")
        words = {}
        for cat in minigames.CATEGORIES:
            raw = (c.get("words") or {}).get(cat, [])
            if not isinstance(raw, list) or len(raw) > 2000:
                raise ValidationError("A word list is invalid.")
            words[cat] = list(dict.fromkeys(w for w in (_text(x, "Word", 40, required=False).strip() for x in raw) if w))
        if sc.get("who_starts", "moderator") not in minigames.WHO:
            raise ValidationError("Choose who can start a round.")
        raw = sc.get("words", [])
        if not isinstance(raw, list) or len(raw) > 2000:
            raise ValidationError("A word list is invalid.")
        swords = list(dict.fromkeys(w for w in (_text(x, "Word", 40, required=False).strip() for x in raw) if w))
        bad = next((w for w in swords if not minigames.scramble_ok(w)), None)
        if bad is not None:
            raise ValidationError(f"«{bad}»: a word for «رتب» is one Arabic word of 3 to 7 letters.")
        # 1.10.0: categories. Your own words may have one; categories can be turned off (not played).
        raw_cats = sc.get("word_cats", {}) or {}
        if not isinstance(raw_cats, dict):
            raise ValidationError("The word categories couldn't be read.")
        word_cats = {}
        for w, cat in raw_cats.items():
            w = str(w).strip()
            cat = " ".join(_text(cat, "Category", 60, required=False).split())
            if w in swords and cat:                   # (a removed word takes its category with it)
                if len(cat) > minigames.MAX_CATEGORY:
                    raise ValidationError(f"«{cat}»: a category name can be at most {minigames.MAX_CATEGORY} characters.")
                word_cats[w] = cat
        off = sc.get("categories_off", []) or []
        if not isinstance(off, list) or len(off) > 200:
            raise ValidationError("The categories in play couldn't be read.")
        known_cats = minigames.scramble_categories({"word_cats": word_cats})
        off = [c for c in dict.fromkeys(str(x).strip() for x in off) if c in known_cats]
        if not minigames.scramble_entries({"words": swords, "word_cats": word_cats, "categories_off": off}):
            raise ValidationError("Keep at least one category in play, or the game has no words.")
        return {"letters": dict(cmds, enabled=_bool(c.get("enabled", False), "Game switch"), who_starts=c.get("who_starts", "moderator"),
                                round_seconds=int(_number(c.get("round_seconds", 60), "Round time", 15, 600)),
                                auto_minutes=int(_number(c.get("auto_minutes", 0), "Automatic rounds", 0, 240)),
                                categories=cats, letters=letters, words=words,
                                announce=_bool(c.get("announce", True), "Announcements")),
                "scramble": dict(scmds, enabled=_bool(sc.get("enabled", False), "Game switch"), who_starts=sc.get("who_starts", "moderator"),
                                 round_seconds=int(_number(sc.get("round_seconds", 45), "Round time", 15, 600)),
                                 hint=_bool(sc.get("hint", True), "Hint"),
                                 auto_minutes=int(_number(sc.get("auto_minutes", 0), "Automatic rounds", 0, 240)),
                                 announce=_bool(sc.get("announce", True), "Announcements"), words=swords,
                                 show_category=_bool(sc.get("show_category", True), "Show the category"),
                                 word_cats=word_cats, categories_off=off),
                "shared": dict(found["shared"],
                               rounds_per_stream=int(_number(sh.get("rounds_per_stream", 0), "Rounds per stream", 0, minigames.MAX_ROUNDS)),
                               cooldown_seconds=int(_number(sh.get("cooldown_seconds", 0), "Cooldown between rounds", 0, minigames.MAX_COOLDOWN)))}

    if section == "game_wins":
        if not isinstance(data, dict) or len(data) > 100000:
            raise ValidationError("The wins list is invalid.")
        out = {}
        for uid, e in data.items():
            if not isinstance(e, dict):
                raise ValidationError("The wins list is invalid.")
            g = e.get("games", {})
            if not isinstance(g, dict):
                raise ValidationError("The wins list is invalid.")
            out[str(uid)[:30]] = {"name": _text(e.get("name", "?"), "Name", 40, required=False) or "?", "wins": int(_number(e.get("wins", 0), "Wins", 0, 10 ** 9)),
                                  "games": {k: int(_number(g[k], "Wins", 0, 10 ** 9)) for k in minigames.GAME_KEYS if k in g}}
        return out

    if section == "moderation":
        if not isinstance(data, dict):
            raise ValidationError("The moderation settings are invalid.")
        base = moderation.defaults()
        out = {"shared_chat": _bool(data.get("shared_chat", False), "Shared chat")}

        def listed(raw, label, limit=500):
            if not isinstance(raw, list) or len(raw) > limit:
                raise ValidationError(f"{label} must be a list of at most {limit}.")
            return raw
        for f in moderation.FILTERS:
            c = data.get(f, base[f])
            if not isinstance(c, dict):
                raise ValidationError(f"The '{f}' filter is invalid.")
            steps = c.get("steps", [0, 60, 600])
            if not isinstance(steps, list) or not 1 <= len(steps) <= 6 or any(isinstance(x, bool) or not isinstance(x, int) or not 0 <= x <= 1209600 for x in steps):
                raise ValidationError("Each punishment step is 0 (a warning) or a timeout of up to 14 days, in seconds (1 to 6 steps).")
            action = c.get("action", "steps")
            if action not in moderation.ACTIONS:
                raise ValidationError("Choose what the filter does.")
            o = {"enabled": _bool(c.get("enabled", False), "Filter switch"), "exempt_vip": _bool(c.get("exempt_vip", True), "Skip VIPs"),
                 "exempt_sub": _bool(c.get("exempt_sub", False), "Skip subscribers"), "action": action, "steps": steps,
                 "warn_text": _text(c.get("warn_text", ""), "Warning message", 300, required=False)}
            if f == "badwords":
                ws, seen = [], set()
                for e in listed(c.get("words", []), "Bad words", 1000):
                    w = _text(e.get("w", "") if isinstance(e, dict) else e, "Bad word", 60, required=False)
                    if w and w.lower() not in seen:
                        seen.add(w.lower())
                        ws.append({"w": w, "anywhere": _bool(e.get("anywhere", False) if isinstance(e, dict) else False, "Anywhere")})
                o["words"] = ws
                o["allowed"] = list(dict.fromkeys(a for a in (_text(x, "Allowed word", 60, required=False) for x in listed(c.get("allowed", []), "Allowed words")) if a))
            elif f == "links":
                tr = []
                for x in listed(c.get("trusted", []), "Trusted sites"):
                    d = _text(x, "Trusted site", 100, required=False).lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
                    if d and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,24}", d):
                        raise ValidationError(f"'{d}' doesn't look like a website address (like example.com).")
                    if d and d not in tr:
                        tr.append(d)
                o["trusted"] = tr
            elif f in ("caps", "symbols"):
                o["percent"] = int(_number(c.get("percent", base[f]["percent"]), "Percent", 10, 100))
                o["min_length"] = int(_number(c.get("min_length", base[f]["min_length"]), "Minimum length", 1, 500))
            elif f == "emotes":
                o["max"] = int(_number(c.get("max", 7), "Most emotes", 1, 100))
            elif f == "repeats":
                o["word_repeats"] = int(_number(c.get("word_repeats", 6), "Repeated words", 2, 100))
                o["same_message"] = int(_number(c.get("same_message", 3), "Same message", 2, 20))
            out[f] = o
        return out

    if section == "prefs":
        if not isinstance(data, dict):
            raise ValidationError("Settings are invalid.")
        on_close = data.get("on_close", "quit")
        if on_close not in ("quit", "tray"):
            raise ValidationError("Choose what happens when the window closes.")
        days = data.get("log_days", 30)
        if isinstance(days, bool) or days not in (0, 7, 30, 90):
            raise ValidationError("Choose how long to keep the logs.")
        return {
            "startup": _bool(data.get("startup", False), "Run on startup"),
            "start_minimized": _bool(data.get("start_minimized", False), "Start minimized"),
            "on_close": on_close,
            "auto_reconnect": _bool(data.get("auto_reconnect", True), "Reconnect to Twitch automatically"),
            "auto_update": _bool(data.get("auto_update", True), "Check for updates automatically"),
            "notify": _bool(data.get("notify", True), "Desktop notifications"),
            "notify_sound": _bool(data.get("notify_sound", False), "Play a sound"),
            "log_days": days,
            "log_chat": _bool(data.get("log_chat", False), "Log chat messages"),
        }

    if section == "ui":
        if not isinstance(data, dict):
            raise ValidationError("Appearance settings are invalid.")
        size = data.get("fontSize", "medium")
        if size not in ("small", "medium", "large", "xlarge"):
            raise ValidationError("Choose a font size: small, medium, large or extra large.")
        language = data.get("language", "en")
        if language not in ("en", "ar"):
            raise ValidationError("The language must be English or Arabic.")
        accent = str(data.get("accent", "#9a1118")).strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", accent):
            raise ValidationError("The accent color must look like #9a1118.")
        return {
            "dark": _bool(data.get("dark", True), "Dark mode"),
            "language": language,
            "fontSize": size,
            "accent": accent,
            "compact": _bool(data.get("compact", False), "Compact layout"),
            "reduceMotion": _bool(data.get("reduceMotion", False), "Reduce motion"),
            "tourDone": _bool(data.get("tourDone", False), "Tutorial"),
            "gsDone": _bool(data.get("gsDone", False), "Getting started"),
            "wnSeen": str(data.get("wnSeen", ""))[:20] if re.fullmatch(r"[0-9a-z.\-]{0,20}", str(data.get("wnSeen", ""))) else "",
        }

    raise ValidationError("Unknown section.")


# ---------- web app ----------

def create_app(store: Store, state: dict, port: int | None = None) -> web.Application:
    state.setdefault("store", store)     # the login code needs the settings too

    @web.middleware
    async def guard(request: web.Request, handler):
        # Blocks other websites (and DNS-rebinding tricks) from driving the
        # dashboard through the user's browser.
        if request.headers.get("Host", "").rsplit(":", 1)[0] not in ("localhost", "127.0.0.1"):
            raise web.HTTPForbidden(text="Forbidden")
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("Origin")
            if origin and not origin_ok(origin, port or PORT):      # PORT is the port really in use
                raise web.HTTPForbidden(text="Forbidden")
            if request.content_type != "application/json":
                raise web.HTTPUnsupportedMediaType(text="Expected JSON")
        # 1.12.0: the page says which channel it was opened for. If the app switched channel since, refuse (the page
        # reloads): a save can never land in the wrong channel.
        want = request.headers.get("X-Channel")
        if want and request.path.startswith("/api/") and channels_info(state) is not None and want != str(accounts.ACTIVE["id"]):
            return web.json_response({"error": "switched"}, status=409, headers={"Cache-Control": "no-store"})
        try:
            resp = await handler(request)
        except EmptySaveRefused as e:        # (never an empty list over real data: the page shows why)
            return web.json_response({"error": str(e)}, status=409, headers={"Cache-Control": "no-store"})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    async def index(request):
        return web.Response(text=PAGE.read_text(encoding="utf-8"), content_type="text/html")

    async def icon(request):
        if not ICON.is_file():
            raise web.HTTPNotFound()
        return web.Response(body=ICON.read_bytes(), content_type="image/x-icon")

    async def status(request):
        info = bot_account_info(state, store.get("settings"))
        mod = state.get("bot_mod") or {}
        if (info["enabled"] and info["login"] and state.get("account_id") and not state.get("mod_busy")
                and time.time() - mod.get("at", 0) > 120):      # keep the "is it a moderator?" answer fresh
            state["mod_task"] = asyncio.create_task(refresh_bot_mod(state))
        bot = state.get("bot")
        account = state.get("account")
        uptime = None
        if bot and bot.live_since:
            uptime = int((datetime.now(timezone.utc) - bot.live_since).total_seconds())
        login = state.get("login", {"status": "idle"})
        return web.json_response({
            "account": account,
            "connected": bool(bot and bot.connected),
            "live": bool(bot and bot.is_live),
            "uptime_seconds": uptime,
            "login": {k: login.get(k) for k in ("status", "code", "uri", "message")},
            "problem": auth.last_problem,
            "event_problems": dict(getattr(bot, "event_problems", {}) or {}) if bot else {},
            "avatar": state.get("avatar") if account else None,
            "lost": bool(state.get("lost")),
            "health": health_info(state),
            "bot_account": bot_account_info(state, store.get("settings")),
            "donations": donation_status(state),
            "publist": publist_info(state),
            "mod_problem": getattr(state.get("bot"), "mod_problem", None),
            "last_reconnect": state.get("last_reconnect"),
            "two_copies": bool(state.get("two_copies")),                            # the bot reconnected by itself (why, when)
            "banned": bool(state.get("banned")),                                       # the developer turned the app off here
            "game": bot.game_view() if bot and hasattr(bot, "game_view") else None,
            "game_limits": bot.game_limits() if bot and hasattr(bot, "game_limits") else None,
            "channels": channels_info(state),          # 1.12.0: every channel, which one is shown, who sends its replies
            "bot_add": state.get("bot_add"),            # 1.12.0: "Add bot account": waiting (code) / connected / error
            # what changed since the page last looked: it reloads the settings / the logs only when these move (1.9.0)
            "rev": f"{getattr(store, 'boot', 0)}:{getattr(store, 'rev', 0)}",
            "logrev": f"{getattr(store, 'boot', 0)}:{getattr(store.activity, 'rev', 0)}",   # All games: rounds used, cooldown left      # the Mini games round in progress (the card's live box)
            "dev": str(state.get("account_id") or "") in greetings.DEVELOPERS,           # shows the Users page (the website checks again)   # Twitch refused a delete/timeout ("scopes" = reconnect)
            "caps": dict(desktop.caps, updates=bool(desktop.FROZEN and not updater.is_dev())),
            "update": {k: updater.U.get(k) for k in ("status", "current", "latest", "notes", "progress", "error")},
        })

    async def logs(request):
        tab = request.query.get("tab", "activity")
        if tab == "all":       # the Logs page: all three tabs at once, with how many entries each got today
            return web.json_response({t: store.activity.recent(300, t) for t in ("activity", "moderation", "bot")} | {"counts": store.activity.counts()})
        if tab not in ("activity", "moderation", "bot"):
            tab = "activity"
        return web.json_response(store.activity.recent(200, tab))      # newest first, saved on disk

    async def bots_get(request):
        info = bots_info(state)
        if info is None:
            return web.json_response({"error": "This app runs a single channel."}, status=400)
        if request.query.get("status"):        # ask Twitch: can each bot send in each of its channels? (slower)
            from . import botsender
            for b in info["bots"]:
                s = botsender.get(b["id"], b["login"])
                if request.query.get("fresh"):    # "Check again": ask Twitch afresh (not the 2-minute memory)
                    s._mods.clear()
                    s.problem = ""
                b["status"] = {cid: await s.status(cid) for cid in b["channels"]}
        return web.json_response(info)

    async def bots_action(request):
        """sender (who sends THIS channel's replies) | add (sign in a bot account) | remove | ack (dismiss a warning)."""
        from . import botsender
        try:
            data = await request.json()
        except (ValueError, UnicodeDecodeError):
            data = {}
        data = data if isinstance(data, dict) else {}
        reg = accounts.load()
        if reg is None:
            return web.json_response({"error": "This app runs a single channel."}, status=400)
        cid, action = str(accounts.ACTIVE["id"]), request.match_info["action"]
        runtimes = state.get("runtimes") or {}
        entry = next((c for c in reg["channels"] if c["id"] == cid), None)
        if action == "sender":
            sid = str(data.get("sender") or "own")
            if sid != "own" and sid not in [b["id"] for b in reg["bots"]]:
                return web.json_response({"error": "Unknown bot account."}, status=400)
            entry["sender"] = sid
            entry.pop("sender_note", None)
            accounts.save(reg)
            restart_bot(state)
        elif action == "add":
            old = state.get("bot_add_task")
            if old is not None and not old.done():
                old.cancel()
            start_login(state, role="bot")
            state["bot_add_task"] = asyncio.create_task(_register_bot(state))
        elif action == "remove":
            bid = str(data.get("id") or "")
            bot = next((b for b in reg["bots"] if b["id"] == bid), None)
            if bot is None:
                return web.json_response({"error": "Unknown bot account."}, status=400)
            reg["bots"] = [b for b in reg["bots"] if b["id"] != bid]
            moved = []
            for c in reg["channels"]:
                if c.get("sender") == bid:   # never silently stop: these channels reply with their own account, and are warned
                    c["sender"] = "own"
                    c["sender_note"] = {"what": "removed", "login": bot.get("login", ""), "at": int(time.time())}
                    moved.append(c["id"])
            accounts.save(reg)
            botsender.forget(bid)
            accounts.bot_token_file(bid).unlink(missing_ok=True)
            for m in moved:
                if m in runtimes:
                    restart_bot(runtimes[m].state)
            return web.json_response({"ok": True, "moved": moved, "bots": bots_info(state)})
        elif action == "ack":
            if entry is not None:
                entry.pop("sender_note", None)
                accounts.save(reg)
        else:
            raise web.HTTPNotFound()
        return web.json_response({"ok": True, "bots": bots_info(state)})

    async def channel_action(request):
        """1.12.0: switch / add / remove a channel (main.py does the work; the page reloads afterwards)."""
        app_fns = state.get("app") or {}
        try:
            data = await request.json()
        except (ValueError, UnicodeDecodeError):
            data = {}
        action = request.match_info["action"]
        try:
            if action == "active":
                app_fns["switch_channel"](str((data or {}).get("id", "")))
            elif action == "add":
                app_fns["add_channel"]()
            elif action == "remove":
                await app_fns["remove_channel"](str((data or {}).get("id", "")))
            else:
                raise web.HTTPNotFound()
        except (KeyError, TypeError):
            return web.json_response({"error": "This app runs a single channel."}, status=400)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True, "channels": channels_info(state)})

    async def support_send(request):
        """The Support page's Send (1.11.0): checked here, then sent through the website to the developers' Discord."""
        try:
            data = await request.json()
        except (ValueError, UnicodeDecodeError):
            data = None
        try:
            prep = support.prepare(data)
            token = (auth.load_token() or {}).get("access_token")
            if not token or not state.get("account"):
                raise support.SupportError("login", "Connect Twitch first.")
            return web.json_response(await support.send(prep, token))
        except support.SupportError as e:
            return web.json_response({"error": e.code, "detail": e.detail}, status=400 if e.code not in ("offline", "failed") else 502)

    async def connect(request):
        if state.get("account"):
            return web.json_response({"ok": True})
        start_login(state)
        return web.json_response({"ok": True})

    async def disconnect(request):
        state["user_logout"] = True          # (so the app doesn't say "your login expired" afterwards)
        task = state.get("login_task")
        if task and not task.done():
            task.cancel()
        auth.disconnect()
        bot = state.get("bot")
        state["account"] = None
        state["avatar"] = None
        state["bot"] = None
        if bot:
            state["close_task"] = asyncio.create_task(bot.close())   # main.py then waits for a new login
        return web.json_response({"ok": True})

    async def read(request):
        section = request.match_info["section"]
        if section not in SECTIONS:
            raise web.HTTPNotFound()
        return web.json_response(store.get(section))

    async def write(request):
        section = request.match_info["section"]
        if section not in SECTIONS:
            raise web.HTTPNotFound()
        try:
            data = validate(section, keep_tour_flag(section, await request.json(), store))
        except ValidationError as e:
            return web.json_response({"error": str(e)}, status=400)
        except (ValueError, AttributeError):
            return web.json_response({"error": "That data couldn't be read."}, status=400)
        clash = game_command_clash(data if section == "games" else store.get("games"),
                                   data if section == "commands" else store.get("commands")) if section in ("games", "commands") else None
        if clash:
            return web.json_response({"error": clash}, status=400)
        if section == "prefs":
            try:
                desktop.apply_prefs(data)      # the Windows start-up entry
            except Exception as e:
                log.exception("Could not change the start-up setting")
                return web.json_response({"error": "Couldn't change the Windows start-up setting: " + str(e)[:150]}, status=500)
        previous = store.get("settings") if section == "settings" else None
        store.save(section, data)
        if section in ("commands", "settings") and state.get("publist_wake") is not None:
            state["publist_wake"].set()         # the public command list follows the change in a few seconds
        if section == "settings" and previous is not None and bool(previous.get("separate_bot")) != bool(data.get("separate_bot")):
            restart_bot(state)          # the bot talks from another account now (or from yours again)
        if section == "prefs":
            store.activity.prune()              # apply a new "Keep logs for"
            wake = state.get("update_wake")
            if wake is not None and data.get("auto_update"):
                wake.set()                      # look for updates now that automatic updates are on
        return web.json_response(data)

    async def publist_sync(request):
        syncer = state.get("publist_syncer")
        if syncer is not None:
            syncer.sync_now()
        return web.json_response({"ok": True})

    async def dev_users(request):
        """Developers only: the list of channels that use the app, from the website (which checks the user ID itself)."""
        if str(state.get("account_id") or "") not in greetings.DEVELOPERS:
            return web.json_response({"error": "Not available."}, status=403)
        token = (auth.load_token() or {}).get("access_token") or ""
        code, body, _ = await publiclist.http_send("GET", token, None, path="/api/dev/users")
        if code == 0:
            return web.json_response({"error": "The website can't be reached right now."}, status=503)
        return web.json_response(body, status=code if code in (200, 401, 403) else 502)

    async def dev_ban(request):
        if str(state.get("account_id") or "") not in greetings.DEVELOPERS:
            return web.json_response({"error": "Not available."}, status=403)
        try:
            data = await request.json()
            uid, ban = str(data["user_id"]), bool(data["banned"])
        except Exception:
            return web.json_response({"error": "The request couldn't be read."}, status=400)
        token = (auth.load_token() or {}).get("access_token") or ""
        code, body, _ = await publiclist.http_send("PUT", token, {"user_id": uid, "banned": ban}, path="/api/dev/ban")
        if code == 0:
            return web.json_response({"error": "The website can't be reached right now."}, status=503)
        return web.json_response(body, status=code if code in (200, 400, 401, 403) else 502)

    async def update_check(request):
        await updater.check(updater.U)
        if updater.U["status"] == "available" and store.get("prefs").get("auto_update", True):
            state["update_task"] = asyncio.create_task(updater.download(updater.U))
        return web.json_response({"ok": True})

    async def update_nudge(request):
        """The page tells us the window was opened or brought back to the front."""
        wake = state.get("update_wake")
        started = updater.nudge(updater.U, store, wake) if wake is not None else False
        return web.json_response({"ok": True, "checking": started})

    async def update_download(request):
        if updater.U["status"] in ("available", "error") and updater.U.get("asset"):
            state["update_task"] = asyncio.create_task(updater.download(updater.U))
        return web.json_response({"ok": True})

    async def update_install(request):
        if not updater.install(updater.U, relaunch=True):
            return web.json_response({"error": "There is no downloaded update to install."}, status=400)
        def close_app():
            if desktop.quit_app:
                desktop.quit_app()
            else:
                os._exit(0)
        asyncio.get_running_loop().call_later(1.0, close_app)     # let this answer reach the page first
        return web.json_response({"ok": True})

    async def show_window(request):
        """A second copy of the app was started: it asks this one to bring its window to the front instead of running twice."""
        fn = desktop.show_window
        if fn is None:
            return web.json_response({"ok": True, "shown": False})      # no app window yet: this copy is still starting
        try:
            fn()
        except Exception:
            log.exception("Could not show the app window")
        return web.json_response({"ok": True, "shown": True})

    async def donation_connect(request):
        manager = state.get("donations")
        if manager is None:
            return web.json_response({"error": "Donations aren't available yet. Try again in a moment."}, status=503)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "That request wasn't understood."}, status=400)
        try:
            manager.connect(request.match_info["service"], body.get("token") if isinstance(body, dict) else None)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except OSError as e:
            log.error("Could not save a donation token: %s", e)          # the token itself is never logged
            return web.json_response({"error": "Couldn't save the token on this PC: " + str(e)[:120]}, status=500)
        return web.json_response({"ok": True})

    async def donation_disconnect(request):
        manager = state.get("donations")
        if manager is None:
            return web.json_response({"error": "Donations aren't available yet."}, status=503)
        try:
            manager.disconnect(request.match_info["service"])
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def bot_connect(request):
        start_login(state, "bot")
        return web.json_response({"ok": True})

    async def bot_cancel(request):
        task = state.get("bot_login_task")
        if task and not task.done():
            task.cancel()
        state["bot_login"] = {"status": "idle"}
        return web.json_response({"ok": True})

    async def bot_disconnect(request):
        task = state.get("bot_login_task")
        if task and not task.done():
            task.cancel()
        botauth.disconnect()
        state["bot_account"] = None
        state["bot_mod"] = None
        state["bot_login"] = {"status": "idle"}
        if store.get("settings").get("separate_bot"):
            restart_bot(state)          # the bot then waits until a bot account is connected again
        return web.json_response({"ok": True})

    async def bot_check(request):
        await refresh_bot_mod(state)
        return web.json_response({"ok": True, "is_mod": (state.get("bot_mod") or {}).get("is_mod")})

    async def bot_test(request):
        bot = state.get("bot")
        if not (bot and getattr(bot, "separate", False) and bot.connected):
            return web.json_response({"error": "The bot isn't running with the bot account yet."}, status=400)
        try:
            name = await bot.send_test()
        except Exception as e:
            log.exception("The test message could not be sent")
            return web.json_response({"error": "Twitch refused the message: " + str(e)[:150]}, status=502)
        return web.json_response({"ok": True, "name": name})

    async def restart(request):
        restart_bot(state)               # the "Restart bot" button: a fresh connection to Twitch, right now
        return web.json_response({"ok": True})

    async def reconnect(request):
        state["lost"] = False
        wake = state.get("wake")
        if wake is not None:
            wake.set()
        return web.json_response({"ok": True})

    async def notify_test(request):
        shown = notify.send(dict(store.get("prefs"), notify=True), "FQPN's Chat Bot", "This is a test notification.")
        return web.json_response({"ok": bool(shown)})

    app = web.Application(middlewares=[guard], client_max_size=16 * 1024 * 1024)    # (Support: up to 4 pictures)
    app.router.add_get("/", index)
    app.router.add_get("/icon.ico", icon)
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/logs", logs)
    app.router.add_post("/api/connect", connect)
    app.router.add_post("/api/support", support_send)
    app.router.add_post("/api/channels/{action}", channel_action)
    app.router.add_get("/api/bots", bots_get)
    app.router.add_post("/api/bots/{action}", bots_action)
    app.router.add_post("/api/disconnect", disconnect)
    app.router.add_post("/api/reconnect", reconnect)
    app.router.add_post("/api/restart", restart)
    app.router.add_post("/api/botaccount/connect", bot_connect)
    app.router.add_post("/api/donations/{service}/connect", donation_connect)
    app.router.add_post("/api/donations/{service}/disconnect", donation_disconnect)
    app.router.add_post("/api/botaccount/cancel", bot_cancel)
    app.router.add_post("/api/botaccount/disconnect", bot_disconnect)
    app.router.add_post("/api/botaccount/check", bot_check)
    app.router.add_post("/api/botaccount/test", bot_test)
    app.router.add_post("/api/show", show_window)
    app.router.add_post("/api/update/check", update_check)
    app.router.add_post("/api/update/download", update_download)
    app.router.add_post("/api/update/nudge", update_nudge)
    app.router.add_get("/api/dev/users", dev_users)
    app.router.add_post("/api/dev/ban", dev_ban)
    app.router.add_post("/api/update/install", update_install)
    app.router.add_post("/api/notify/test", notify_test)
    app.router.add_post("/api/publist/sync", publist_sync)
    app.router.add_get("/api/{section}", read)
    app.router.add_put("/api/{section}", write)
    return app


async def start(store: Store, state: dict, port: int | None = None) -> web.AppRunner:
    global PORT, start_error
    runner = web.AppRunner(create_app(store, state), access_log=None)
    await runner.setup()

    async def bind(p: int) -> None:
        await web.TCPSite(runner, HOST, p).start()

    try:
        chosen = await bind_first_free(port or PORT, PORT_TRIES, bind)
    except OSError as e:
        start_error = str(e)
        ready.set()
        raise
    PORT = chosen
    if PORT_FILE is not None:
        try:
            Path(PORT_FILE).write_text(str(chosen), encoding="utf-8")
        except OSError:
            log.warning("Could not write the dashboard port file", exc_info=True)
    ready.set()
    log.info("Dashboard running at http://%s:%d", HOST, chosen)
    return runner
