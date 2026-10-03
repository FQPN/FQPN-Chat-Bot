"""Local web dashboard (http://localhost:5000).

It only edits the JSON files through Store. The bot re-reads those files
automatically, so changes apply without restarting anything."""

import asyncio
import os
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiohttp import web

from . import auth, desktop, events, manage, notify, updater
from .store import Store

log = logging.getLogger("twitchbot.dashboard")

HOST = "127.0.0.1"   # this PC only - never exposed to the network
PORT = 5000
PAGE = Path(__file__).resolve().parent / "dashboard.html"
ICON = Path(__file__).resolve().parent.parent / "icon.ico"   # next to main.py (and inside the installed program folder)
PERMISSIONS = ("everyone", "subscriber", "vip", "moderator", "broadcaster")
SECTIONS = ("commands", "timers", "greetings", "events", "blocklist", "settings", "ui", "prefs")
_LOGIN = re.compile(r"[a-z0-9_]{1,25}")


class ValidationError(Exception):
    pass


# ---------- Twitch connect / disconnect (used by the dashboard buttons) ----------

async def _login(state: dict) -> None:
    login = state["login"]
    login.update(status="waiting", code=None, uri=None, message="")

    def on_code(code, uri):
        login.update(code=code, uri=uri)
        print(f"\nGo to {uri} and enter code: {code}\n")

    try:
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


def start_login(state: dict) -> None:
    login = state.setdefault("login", {"status": "idle"})
    if login.get("status") == "waiting":
        return
    state["login_task"] = asyncio.create_task(_login(state))


# ---------- validation ----------

def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v, what: str, max_len: int = 450, required: bool = True) -> str:
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
            out[name] = {
                "response": _text(c.get("response"), f"Response for '{name}'"),
                "permission": c["permission"],
                "cooldown": _number(c.get("cooldown"), f"Cooldown for '{name}'", 0, 86400),
                "enabled": _bool(c.get("enabled"), f"Enabled for '{name}'"),
                "aliases": aliases,
            }
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
                low = int(_number(t.get("min", 0), "The 'from' number", 0, 1000000))
                if key in events.SINGLE:
                    low = 0
                if low in seen:
                    raise ValidationError(f"Two replies start from {low}. Each one needs a different number.")
                seen.add(low)
                tiers.append({"min": low, "response": _text(t.get("response"), "Reply", 450)})
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
                m = _text(m, f"Message for '{user}'", 450, required=False)
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
        return {
            "only_when_live": _bool(data.get("only_when_live"), "Only when live"),
            "paused": _bool(data.get("paused", False), "Paused"),
            "start_active": _bool(data.get("start_active", True), "Start the bot when the app opens"),
            "live_check_seconds": int(_number(data.get("live_check_seconds"), "Live check interval", 15, 3600)),
            "commands_url": url,
        }

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
        }

    raise ValidationError("Unknown section.")


# ---------- web app ----------

def create_app(store: Store, state: dict, port: int = PORT) -> web.Application:
    allowed_origins = {f"http://localhost:{port}", f"http://127.0.0.1:{port}"}

    @web.middleware
    async def guard(request: web.Request, handler):
        # Blocks other websites (and DNS-rebinding tricks) from driving the
        # dashboard through the user's browser.
        if request.headers.get("Host", "").rsplit(":", 1)[0] not in ("localhost", "127.0.0.1"):
            raise web.HTTPForbidden(text="Forbidden")
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("Origin")
            if origin and origin not in allowed_origins:
                raise web.HTTPForbidden(text="Forbidden")
            if request.content_type != "application/json":
                raise web.HTTPUnsupportedMediaType(text="Expected JSON")
        resp = await handler(request)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    async def index(request):
        return web.Response(text=PAGE.read_text(encoding="utf-8"), content_type="text/html")

    async def icon(request):
        if not ICON.is_file():
            raise web.HTTPNotFound()
        return web.Response(body=ICON.read_bytes(), content_type="image/x-icon")

    async def status(request):
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
            "caps": dict(desktop.caps, updates=bool(desktop.FROZEN and not updater.is_dev())),
            "update": {k: updater.U.get(k) for k in ("status", "current", "latest", "notes", "progress", "error")},
        })

    async def logs(request):
        return web.json_response(store.activity.recent(200))      # newest first, saved on disk

    async def connect(request):
        if state.get("account"):
            return web.json_response({"ok": True})
        start_login(state)
        return web.json_response({"ok": True})

    async def disconnect(request):
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
            data = validate(section, await request.json())
        except ValidationError as e:
            return web.json_response({"error": str(e)}, status=400)
        except (ValueError, AttributeError):
            return web.json_response({"error": "That data couldn't be read."}, status=400)
        if section == "prefs":
            try:
                desktop.apply_prefs(data)      # the Windows start-up entry
            except Exception as e:
                log.exception("Could not change the start-up setting")
                return web.json_response({"error": "Couldn't change the Windows start-up setting: " + str(e)[:150]}, status=500)
        store.save(section, data)
        if section == "prefs":
            store.activity.prune()              # apply a new "Keep logs for"
            wake = state.get("update_wake")
            if wake is not None and data.get("auto_update"):
                wake.set()                      # look for updates now that automatic updates are on
        return web.json_response(data)

    async def update_check(request):
        await updater.check(updater.U)
        if updater.U["status"] == "available" and store.get("prefs").get("auto_update", True):
            state["update_task"] = asyncio.create_task(updater.download(updater.U))
        return web.json_response({"ok": True})

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

    async def reconnect(request):
        state["lost"] = False
        wake = state.get("wake")
        if wake is not None:
            wake.set()
        return web.json_response({"ok": True})

    async def notify_test(request):
        shown = notify.send(dict(store.get("prefs"), notify=True), "FQPN's Chat Bot", "This is a test notification.")
        return web.json_response({"ok": bool(shown)})

    app = web.Application(middlewares=[guard])
    app.router.add_get("/", index)
    app.router.add_get("/icon.ico", icon)
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/logs", logs)
    app.router.add_post("/api/connect", connect)
    app.router.add_post("/api/disconnect", disconnect)
    app.router.add_post("/api/reconnect", reconnect)
    app.router.add_post("/api/update/check", update_check)
    app.router.add_post("/api/update/download", update_download)
    app.router.add_post("/api/update/install", update_install)
    app.router.add_post("/api/notify/test", notify_test)
    app.router.add_get("/api/{section}", read)
    app.router.add_put("/api/{section}", write)
    return app


async def start(store: Store, state: dict, port: int = PORT) -> web.AppRunner:
    runner = web.AppRunner(create_app(store, state, port), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, HOST, port).start()
    log.info("Dashboard running at http://localhost:%d", port)
    return runner
