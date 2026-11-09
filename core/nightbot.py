"""1.17.0 (owner): Import from Nightbot (Commands > Import from Nightbot).

Reads a channel's Nightbot commands from Nightbot's public commands page (the same list anyone sees at
nightbot.tv/t/<channel>/commands: no sign-in) and turns them into this app's commands:
  - the name, reply, user level and cooldown carry over; Nightbot variables that work the same stay as they are,
    the ones that only look different are changed ($(customapi URL) → $(urlfetch URL), $(twitch $(channel)
    "{{uptimeLength}}") → $(uptime), …), and a command with something this app doesn't have is imported switched off,
    with a note saying what to check;
  - a command with the name of one you already have: skip it, replace yours, or import it under another name;
  - everything imported shows in Command history ("Nightbot import"), with "Undo the whole import".
Timers aren't on Nightbot's public page, so they can't be read this way.

The second way, "Sign in with Nightbot" (also gets mod-only commands and the timers): Nightbot's sign-in needs a secret
key that must never be inside the app, so fqpnbot.com does that one step (web/worker.js, /nightbot/…). The app makes a
long random code, opens fqpnbot.com/nightbot/start in the browser and asks the website every 2 seconds whether the
streamer said yes. The key it gets is used once, to read the commands and timers, and then given back to Nightbot."""
import re
import secrets
import time

import aiohttp

from .publiclist import SITE

API = "https://api.nightbot.tv/1/"
LEVELS = {"everyone": "everyone", "subscriber": "subscriber", "regular": "vip", "twitch_vip": "vip", "vip": "vip",
          "moderator": "moderator", "owner": "broadcaster", "admin": "broadcaster"}
SUPPORTED = {"user", "touser", "query", "querystring", "count", "getcount", "channel", "game", "title", "uptime", "viewers",
             "urlfetch", "eval", "accountage", "random.chatter", "followers", "firststreak", "firststreakpeak", "weather",
             "time", "follow", "followdate", "followage", "clip", "streak"}
_VAR = re.compile(r"\$\(([\w.]+)")
TWITCH_FIELDS = {"uptimeLength": "$(uptime)", "uptime": "$(uptime)", "game": "$(game)", "title": "$(title)",
                 "viewers": "$(viewers)", "name": "$(channel)", "displayName": "$(channel)"}


class NightbotError(Exception):
    pass


def login_of(text: str) -> str:
    """A channel name from what was typed: "FQPN_", "@fqpn_", "twitch.tv/fqpn_", "nightbot.tv/t/fqpn_/commands"."""
    t = str(text or "").strip().lower()
    m = re.search(r"(?:nightbot\.tv/t/|twitch\.tv/)([a-z0-9_]{2,25})", t)
    if m:
        return m.group(1)
    t = t.lstrip("@").strip("/ ")
    return t if re.fullmatch(r"[a-z0-9_]{2,25}", t) else ""


async def fetch(channel: str) -> dict:
    """{"channel": display name, "commands": [Nightbot's command objects]}. NightbotError with a reason in words."""
    login = login_of(channel)
    if not login:
        raise NightbotError("Type a Twitch channel name, like fqpn_.")
    headers = {"User-Agent": "FQPNsChatBot", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=headers) as s:
            async with s.get(API + "channels/t/" + login) as r:
                if r.status == 404:
                    raise NightbotError(f"Nightbot isn't set up on {login}, or that channel doesn't exist.")
                if r.status != 200:
                    raise NightbotError(f"Nightbot answered {r.status}. Try again in a minute.")
                ch = (await r.json(content_type=None) or {}).get("channel") or {}
            cid = ch.get("_id")
            if not cid:
                raise NightbotError(f"Nightbot isn't set up on {login}.")
            async with s.get(API + "commands", headers={"Nightbot-Channel": str(cid)}) as r:
                if r.status != 200:
                    raise NightbotError(f"Nightbot didn't give the commands ({r.status}). Try again in a minute.")
                data = await r.json(content_type=None) or {}
    except NightbotError:
        raise
    except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
        raise NightbotError("Couldn't reach Nightbot. Check the internet connection and try again.")
    return {"channel": ch.get("displayName") or ch.get("name") or login, "login": login,
            "commands": [c for c in (data.get("commands") or []) if isinstance(c, dict)]}


# ---------- "Sign in with Nightbot" ----------

PENDING: dict = {}          # the sign-in waiting for the browser: {"state", "started"}
TIMER_LINES = (0, 2, 5, 10, 20, 50)


def start_signin() -> str:
    """A new sign-in: returns the web address to open in the browser."""
    PENDING.clear()
    PENDING.update(state=secrets.token_urlsafe(32), started=time.time())
    return SITE.rstrip("/") + "/nightbot/start?state=" + PENDING["state"]


async def check_signin():
    """None = still waiting; otherwise the same as fetch(): {"channel", "login", "commands", "timers"}."""
    state = PENDING.get("state")
    if not state:
        raise NightbotError("Start again: press Sign in with Nightbot.")
    if time.time() - PENDING.get("started", 0) > 600:
        PENDING.clear()
        raise NightbotError("The sign-in took too long. Press Sign in with Nightbot again.")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(SITE.rstrip("/") + "/api/nightbot/token", params={"state": state}) as r:
                data = await r.json(content_type=None) if r.status == 200 else {"status": "error", "error": f"website {r.status}"}
    except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
        return None                                            # (try again in 2 seconds)
    if data.get("status") == "waiting":
        return None
    PENDING.clear()
    if data.get("status") != "ok" or not data.get("token"):
        if data.get("error") == "not_setup":
            raise NightbotError("Sign in with Nightbot isn't set up on the website yet (Cloudflare needs NIGHTBOT_CLIENT_ID "
                                "and NIGHTBOT_CLIENT_SECRET). Use “Just type the channel” for now.")
        if data.get("error") == "denied":
            raise NightbotError("Nightbot wasn't connected (the sign-in was cancelled).")
        raise NightbotError("Nightbot didn't accept the sign-in. Try again.")
    return await fetch_signed_in(data["token"])


async def fetch_signed_in(token: str) -> dict:
    headers = {"Authorization": "Bearer " + token, "User-Agent": "FQPNsChatBot", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=headers) as s:
            me, cmds, timers = {}, {}, {}
            async with s.get(API + "me") as r:
                if r.status == 200:
                    me = await r.json(content_type=None) or {}
            async with s.get(API + "commands") as r:
                if r.status != 200:
                    raise NightbotError(f"Nightbot didn't give the commands ({r.status}). Try again.")
                cmds = await r.json(content_type=None) or {}
            async with s.get(API + "timers") as r:
                if r.status == 200:
                    timers = await r.json(content_type=None) or {}
            try:                                                # the key is never needed again: give it back
                await s.post("https://api.nightbot.tv/oauth2/token/revoke", data={"token": token})
            except Exception:
                pass
    except NightbotError:
        raise
    except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
        raise NightbotError("Couldn't reach Nightbot. Check the internet connection and try again.")
    user = (me.get("user") or {}) if isinstance(me, dict) else {}
    return {"channel": user.get("displayName") or user.get("name") or "Nightbot", "login": str(user.get("name") or ""),
            "commands": [c for c in (cmds.get("commands") or []) if isinstance(c, dict)],
            "timers": [t for t in (timers.get("timers") or []) if isinstance(t, dict)]}


def minutes_of(cron: str):
    """Nightbot's timer interval (a cron line, like "*/15 * * * *") in minutes. None when it isn't a simple interval."""
    p = str(cron or "").split()
    if len(p) != 5:
        return None
    m, h = p[0], p[1]
    if m.startswith("*/") and h == "*" and m[2:].isdigit():
        return int(m[2:])
    if m.isdigit() and h == "*":
        return 60
    if m.isdigit() and h.startswith("*/") and h[2:].isdigit():
        return int(h[2:]) * 60
    return None


def preview_timers(fetched: dict, existing: list) -> list:
    names = {str(t.get("name") or "").strip().lower(): t.get("name") for t in (existing or []) if isinstance(t, dict)}
    rows = []
    for t in fetched.get("timers", []):
        name = " ".join(str(t.get("name") or "").split())[:40]
        if not name:
            continue
        msg, notes, works = convert_message(t.get("message") or "")
        mins = minutes_of(t.get("interval"))
        if mins is None:
            mins = 15
            notes.append(f"Nightbot's time ({t.get('interval')}) is a special one: set to every 15 minutes, check it.")
        lines = int(t.get("lines") or 0)
        lines = min(TIMER_LINES, key=lambda x: abs(x - lines))
        rows.append({"name": name, "reply": msg, "minutes": max(1, min(1440, mins)), "lines": lines, "works": works,
                     "notes": notes, "clash": names.get(name.lower()), "was_on": bool(t.get("enabled"))})
    return rows


def apply_timers(existing: list, rows: list) -> tuple:
    timers = [dict(t) for t in (existing or []) if isinstance(t, dict)]
    added = []
    for r in rows:
        choice, name = r.get("choice") or "new", " ".join(str(r.get("name") or "").split())[:40]
        if choice == "skip" or not name:
            continue
        if choice == "rename":
            name = " ".join(str(r.get("as") or "").split())[:40]
        clash = next((i for i, t in enumerate(timers) if str(t.get("name", "")).lower() == name.lower()), None)
        if clash is not None and choice != "replace":
            continue
        new = {"name": name, "message": r.get("reply") or "", "interval_minutes": int(r.get("minutes") or 15),
               "enabled": False, "min_lines": int(r.get("lines") or 0) if int(r.get("lines") or 0) in TIMER_LINES else 2}
        if clash is not None:
            timers[clash] = new
        else:
            timers.append(new)
        added.append(name)
    return timers, added


def convert_message(msg: str) -> tuple:
    """(the reply for this app, [notes], works) — works is False when the reply uses something this app doesn't have."""
    notes, works = [], True
    out = str(msg or "")
    if "$(customapi" in out:
        out = out.replace("$(customapi", "$(urlfetch")
        notes.append("$(customapi) is $(urlfetch) here: it works the same.")

    def twitch(m):
        who, field = m.group(1).strip(), m.group(2)
        if who in ("$(channel)",) and field in TWITCH_FIELDS:
            return TWITCH_FIELDS[field]
        return m.group(0)
    new = re.sub(r'\$\(twitch\s+([^\s"]+)\s+"\{\{(\w+)\}\}"\)', twitch, out)
    if new != out:
        notes.append("$(twitch …) was changed to this app's own variable.")
        out = new
    if "$(urlfetch json" in out:
        out = out.replace("$(urlfetch json ", "$(urlfetch ")
        notes.append("$(urlfetch json …) is plain $(urlfetch …) here: check the reply.")
    unknown = sorted({v for v in _VAR.findall(out) if v.lower() not in SUPPORTED and not v.isdigit()})
    if re.search(r"\$\(\d\)", out):
        unknown.append("$(1), $(2)…")
    if unknown:
        works = False
        notes.append("This app doesn't have " + ", ".join(u if u.startswith("$(") else f"$({u})" for u in unknown)
                     + ": imported switched off. Change it or delete it.")
    if "$(eval" in out and works:
        notes.append("$(eval) here is a calculator (numbers and Math), not full JavaScript: check it works.")
    return out[:500], notes, works


def preview(fetched: dict, existing: dict) -> list:
    """The rows of the "Choose" step: [{name, reply, level, cooldown, works, notes, clash, alias_of}]."""
    taken, bare = {}, {}
    for n, c in (existing or {}).items():
        for a in [n] + list((c or {}).get("aliases", [])):
            taken[a] = n
            bare.setdefault(a.lstrip("!"), n)                # "!discord" from Nightbot = your "discord"
    rows = []
    for c in fetched.get("commands", []):
        name = " ".join(str(c.get("name") or "").split()).lower()[:60]
        if not name:
            continue
        reply, notes, works = convert_message(c.get("message") or "")
        alias_of = str(c.get("alias") or "").strip().lower() or None
        if alias_of and not reply:
            notes.append(f"In Nightbot this runs {alias_of}: it's added as another name of {alias_of}.")
        if not reply and not alias_of:
            continue
        rows.append({"count": int(c.get("count") or 0), "name": name, "reply": reply, "level": LEVELS.get(str(c.get("userLevel") or "everyone"), "everyone"),
                     "cooldown": max(0, min(86400, int(c.get("coolDown") or 0))), "works": works, "notes": notes,
                     "clash": taken.get(name) or bare.get(name.lstrip("!")), "alias_of": alias_of if (alias_of and not reply) else None})
    rows.sort(key=lambda r: (r["alias_of"] is not None, r["name"]))
    return rows


def apply(existing: dict, rows: list) -> tuple:
    """The commands after the import, and what happened: (commands, {"added": [...], "replaced": [...], "skipped": [...],
    "off": [...]}). rows: the ticked rows, each with "choice" = new | skip | replace | rename (and "as" for rename)."""
    cmds = {k: dict(v) for k, v in (existing or {}).items()}
    done = {"added": [], "replaced": [], "skipped": [], "off": [], "aliases": []}
    used = lambda: {a for c in cmds.values() for a in c.get("aliases", [])} | set(cmds)
    for r in rows:
        if r.get("alias_of"):
            continue
        name, choice = str(r.get("name") or "").strip().lower(), r.get("choice") or "new"
        if not name or choice == "skip":
            done["skipped"].append(name)
            continue
        if choice == "rename":
            name = " ".join(str(r.get("as") or "").split()).lower()[:60]
            if not name or name in used():
                done["skipped"].append(r.get("name"))
                continue
        elif (name in used() or (r.get("clash") and r.get("clash") in cmds)) and choice != "replace":
            done["skipped"].append(name)
            continue
        if choice == "replace":
            owner = next((n for n, c in cmds.items() if n == name or name in c.get("aliases", [])), None) or \
                (r.get("clash") if r.get("clash") in cmds else None)
            if owner and name in cmds[owner].get("aliases", []):      # the name was another name of one of yours
                cmds[owner]["aliases"] = [a for a in cmds[owner].get("aliases", []) if a != name]
            elif owner:
                cmds.pop(owner)
            done["replaced"].append(name)
        else:
            done["added"].append(name)
        cmds[name] = {"response": r.get("reply") or "", "permission": r.get("level") if r.get("level") in LEVELS.values() else "everyone",
                      "cooldown": int(r.get("cooldown") or 0), "enabled": bool(r.get("works", True)), "aliases": []}
        names_now = used()
        extra = [str(a).strip().lower()[:60] for a in (r.get("aliases") or []) if isinstance(a, str)]
        cmds[name]["aliases"] = list(dict.fromkeys(a for a in extra if a and a != name and a not in names_now))[:10]
        if r.get("as_reply"):
            cmds[name]["reply"] = True       # (StreamElements' "reply" type: answers as a reply to the viewer)
        if not r.get("works", True):
            done["off"].append(name)
    for r in rows:                                      # Nightbot aliases: another name of the command they run
        target = r.get("alias_of")
        if target and target in cmds and r["name"] not in used():
            cmds[target]["aliases"] = cmds[target].get("aliases", []) + [r["name"]]
            done["aliases"].append(r["name"])
    return cmds, done
