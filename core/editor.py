"""Editor link (1.13.0): someone the streamer trusts edits this channel's commands from a website page.

The app makes the link: a 256-bit secret for the URL and a NEW password every time (shown to the streamer once). Only their
SHA-256 hashes go to the website, with a private copy of the commands for the editor page. One link at a time: a new one,
Cancel, 24 hours, or 5 wrong passwords end it.
While a link is active, the Syncer (one per channel) takes the waiting edits from the website every few seconds, checks each
with the app's OWN rules (the same as a save from the dashboard), saves it, writes it in the Logs (who / what), tells the
website applied or refused (with the reason), and sends the new copy. Shortcuts (game / title) and commands with special
replies are shown but can only be changed in the app."""

import asyncio
import copy
import hashlib
import logging
import secrets
import time

from . import auth, publiclist

log = logging.getLogger("twitchbot.editor")
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"        # no 0/O, 1/I/L: easy to read out and type
LINK_HOURS = 24
# 1.13.0: the editor uses the app's OWN pages. These tools can be changed through the link; the rest of the app is not there
# (login, bot accounts, donations, app settings, support, users). Logs are shown, read-only. From "settings" only the
# built-in commands' on/off can change.
EDITABLE = ("commands", "timers", "greetings", "events", "blocklist", "moderation", "games")
SHOWN = EDITABLE + ("settings", "stream", "game_wins")
SETTINGS_KEYS = ("disabled_builtins",)
WINS_MAX = 500                       # (the leaderboard copy: the best 500)
PAGE = None                          # the app's page file (set below)
EVERY = 4.0                                            # seconds between two looks for waiting edits (while a link is active)


class EditorError(Exception):
    pass


def new_password() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(4)) + "-" + "".join(secrets.choice(ALPHABET) for _ in range(4))


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def locked(c: dict) -> bool:
    """Shortcuts (they change the game or title) and replies with tiers are changed in the app only."""
    return (c.get("action") or "text") != "text" or bool(c.get("tiers"))


def snapshot(commands: dict) -> list:
    out = []
    for name in sorted(commands or {}, key=lambda n: (n.lower(), n)):
        c = commands[name]
        if not isinstance(c, dict):
            continue
        out.append({"name": name, "response": str(c.get("response") or ""), "perm": c.get("permission") or "everyone",
                    "cooldown": int(c.get("cooldown") or 0), "enabled": c.get("enabled", True) is not False,
                    "aliases": list(c.get("aliases") or []), "locked": locked(c)})
    return out


def digest(data) -> str:
    import json
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False))


def section_copy(store, name):
    data = store.get(name)
    if name == "settings":
        data = {k: (data or {}).get(k) for k in SETTINGS_KEYS + ("public_list", "only_when_live")}
    if name == "game_wins" and isinstance(data, dict) and len(data) > WINS_MAX:
        top = sorted(data.items(), key=lambda kv: -int((kv[1] or {}).get("wins", 0) if isinstance(kv[1], dict) else 0))[:WINS_MAX]
        data = dict(top)
    return data


def full_copy(store) -> dict:
    """What the editor's copy of the app shows: the tools, their fingerprints (to catch edits made meanwhile), the Logs."""
    sections = {n: section_copy(store, n) for n in SHOWN}
    logs = {t: store.activity.recent(300, t) for t in ("activity", "moderation", "bot")}
    try:
        logs["counts"] = store.activity.counts()
    except Exception:
        logs["counts"] = {}
    return {"sections": sections, "digests": {n: digest(sections[n]) for n in EDITABLE + ("settings",)}, "logs": logs}


def clean_status(st: dict) -> dict:
    """The page's status without anything private: no Twitch codes, no editor link, no other channels."""
    st = dict(st or {})
    for k in ("login", "bot_add", "editor", "channels", "dev", "two_copies"):
        st.pop(k, None)
    if isinstance(st.get("bot_account"), dict):
        st["bot_account"] = {k: v for k, v in st["bot_account"].items() if k not in ("code", "uri", "error")}
    st["remote"] = True
    return st


def page_html() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parent / "dashboard.html").read_text(encoding="utf-8")


def state_of(store) -> dict:
    st = dict(store.get("editor_state") or {})
    if st.get("active") and float(st.get("expires") or 0) <= time.time():
        st["active"] = False
    return st


async def create(store, login: str, send=None) -> dict:
    """A new link + password (the old link ends at once). Returns {url, password, expires}; raises EditorError."""
    token = auth.load_token() or {}
    if not token.get("access_token") or not login:
        raise EditorError("Connect Twitch first.")
    if not publiclist.SITE:
        raise EditorError("This version of the app has no website.")
    secret = secrets.token_urlsafe(32)
    password = new_password()
    salt = secrets.token_hex(16)
    body = {"token_hash": sha256(secret), "pw_salt": salt, "pw_hash": sha256(salt + password),
            "commands": snapshot(store.get("commands"))}
    code, resp, _ = await (send or publiclist.http_send)("PUT", token["access_token"], body, path="/api/editor/link")
    if code != 200:
        raise EditorError(resp.get("error") or ("The website can't be reached." if code == 0 else f"The website answered {code}."))
    code2, resp2, _ = await (send or publiclist.http_send)("PUT", token["access_token"], {"html": page_html()}, path="/api/editor/page")
    if code2 != 200:
        raise EditorError(resp2.get("error") or "The website couldn't take the app's page.")
    url = f"{publiclist.SITE}/{login}/edit/{secret}"
    expires = int(resp.get("expires") or time.time() + LINK_HOURS * 3600)
    store.save("editor_state", {"active": True, "url": url, "expires": expires, "made": int(time.time()), "applied": 0})
    log.info("Made an editor link (ends in %d h)", LINK_HOURS)
    return {"url": url, "password": password, "expires": expires}


async def cancel(store, send=None) -> None:
    token = (auth.load_token() or {}).get("access_token")
    if token:
        await (send or publiclist.http_send)("DELETE", token, None, path="/api/editor/link")
    store.save("editor_state", dict(store.get("editor_state") or {}, active=False))
    log.info("Cancelled the editor link")


def apply(store, change: dict):
    """One edit from the editor page, checked with the app's own rules. (ok, error)."""
    from . import dashboard
    commands = copy.deepcopy(store.get("commands") or {})
    op, name, old = change.get("op"), str(change.get("name") or ""), str(change.get("old_name") or "")
    if op == "delete":
        if name not in commands:
            return True, ""
        if locked(commands[name]):
            return False, "This command is changed in the app only."
        del commands[name]
    elif op == "put":
        return apply_put(store, change)
    elif op == "set":
        src_name = old if old and old in commands else name
        src = commands.get(src_name)
        if src is not None and locked(src):
            return False, "This command is changed in the app only."
        if old and old != name and name in commands:
            return False, f"{name} already exists."
        c = dict(src or {"response": "", "permission": "everyone", "cooldown": 5, "enabled": True, "aliases": []})
        cmd = change.get("cmd") or {}
        c.update(response=cmd.get("response", c.get("response")), permission=cmd.get("permission", c.get("permission")),
                 cooldown=cmd.get("cooldown", c.get("cooldown")), enabled=cmd.get("enabled", True), aliases=cmd.get("aliases") or [])
        if old and old != name:
            commands.pop(old, None)
        commands[name] = c
    else:
        return False, "Unknown change."
    try:
        clean = dashboard.validate("commands", commands)
        clash = dashboard.game_command_clash(store.get("games"), clean)
        if clash:
            return False, clash
        store.save("commands", clean)
    except Exception as e:                    # ValidationError (the reason), or the empty-list guard
        return False, str(e)
    try:
        store.activity.add("editor", name, change.get("editor") or "", op=op)
    except Exception:
        pass
    return True, ""


def apply_put(store, change: dict):
    """A whole tool saved on the editor's copy of the app (the way the app's own pages save). Accepted only if that tool
    did not change in the app since the editor got it, and only through the app's own checks."""
    from . import dashboard
    section = str(change.get("section") or "")
    if section not in EDITABLE + ("settings",):
        return False, "This can't be changed through the editor link."
    if change.get("base") and change.get("base") != digest(section_copy(store, section)):
        return False, "It was changed in the app meanwhile: the page reloaded with the latest. Make your change again."
    data = change.get("data")
    if section == "settings":
        cur = dict(store.get("settings") or {})
        for k in SETTINGS_KEYS:
            if isinstance(data, dict) and k in data:
                cur[k] = data[k]
        data = cur
    try:
        clean = dashboard.validate(section, data)
        if section in ("commands", "games"):
            clash = dashboard.game_command_clash(clean if section == "games" else store.get("games"), clean if section == "commands" else store.get("commands"))
            if clash:
                return False, clash
        store.save(section, clean)
    except Exception as e:
        return False, str(e)
    try:
        store.activity.add("editor", section, change.get("editor") or "", op="put")
    except Exception:
        pass
    return True, ""


class Syncer:
    """One per channel. Sleeps while there is no active link."""

    def __init__(self, store, state, send=None, clock=time.time):
        self.store, self.state = store, state
        self.send = send or publiclist.http_send
        self.clock = clock
        self.sent_digest = None

    async def step(self) -> None:
        st = state_of(self.store)
        if not st.get("active"):
            if (self.store.get("editor_state") or {}).get("active"):
                self.store.save("editor_state", dict(self.store.get("editor_state"), active=False))      # it expired
            return
        token = (auth.load_token() or {}).get("access_token")
        if not token:
            return
        code, body, _ = await self.send("GET", token, None, path="/api/editor/changes")
        if code == 200 and body.get("active") is False:
            self.store.save("editor_state", dict(self.store.get("editor_state") or {}, active=False))   # ended on the website
            return
        results, changed = [], False
        for ch in (body.get("changes") or []) if code == 200 else []:
            ok, why = apply(self.store, ch)
            results.append({"id": ch.get("id"), "ok": ok, "error": why})
            changed = changed or ok
            log.info("Editor link: %s %s by %s -> %s", ch.get("op"), ch.get("name"), ch.get("editor"), "applied" if ok else why)
        if results:
            await self.send("POST", token, {"results": results}, path="/api/editor/ack")
            if changed:
                st2 = dict(self.store.get("editor_state") or {})
                st2["applied"] = int(st2.get("applied") or 0) + sum(1 for r in results if r["ok"])
                st2["last"] = int(self.clock())
                self.store.save("editor_state", st2)
                if self.state.get("publist_wake") is not None:
                    self.state["publist_wake"].set()      # the public list follows the change
        copy_ = full_copy(self.store)
        from . import dashboard
        try:
            status = clean_status(await dashboard.STATUS_FN()) if dashboard.STATUS_FN else {}
        except Exception:
            status = {}
        d = digest([copy_["digests"], len(copy_["logs"].get("activity") or []), (copy_["logs"].get("activity") or [{}])[0] if copy_["logs"].get("activity") else None,
                    status.get("live"), status.get("connected")])
        if d != self.sent_digest or self.clock() - getattr(self, "sent_at", 0) > 60:     # the editor's copy follows the app
            copy_["status"] = status
            copy_["commands"] = snapshot(self.store.get("commands"))      # (the older, commands-only form)
            c2, _, _ = await self.send("PUT", token, copy_, path="/api/editor/data")
            if c2 == 200:
                self.sent_digest, self.sent_at = d, self.clock()

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Editor link sync failed")
            await asyncio.sleep(EVERY if state_of(self.store).get("active") else 15)
