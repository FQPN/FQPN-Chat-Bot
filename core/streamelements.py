"""1.17.0 (owner): Import from StreamElements (Commands > Import, next to Nightbot).

Reads a channel's StreamElements chat bot commands from StreamElements' public commands page (the same list anyone sees
at streamelements.com/<channel>/commands: no sign-in) and turns them into the rows of the same Import window as
Nightbot (core/nightbot.py: preview → choose → apply). StreamElements writes variables as ${user}; they become this
app's $(user), and anything this app doesn't have comes in switched off, with a note."""
import re

import aiohttp

from .nightbot import NightbotError, SUPPORTED, TIMER_LINES, login_of

API = "https://api.streamelements.com/kappa/v2/"
_SE = re.compile(r"\$\{([^}]*)\}")
SIMPLE = {"user": "$(user)", "user.name": "$(user)", "sender": "$(user)", "sender.name": "$(user)", "touser": "$(touser)",
          "touser.name": "$(touser)", "channel": "$(channel)", "channel.name": "$(channel)", "uptime": "$(uptime)",
          "channel.uptime": "$(uptime)", "game": "$(game)", "title": "$(title)", "channel.game": "$(game)",
          "channel.title": "$(title)", "channel.viewers": "$(viewers)", "random.chatter": "$(random.chatter)",
          "user.followage": "$(followage)", "followage": "$(followage)", "1:": "$(query)", "count": "$(count)",
          "queryescape ${1:}": "$(querystring)"}


def level_of(n) -> str:
    """StreamElements' access level number → this app's user level."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "everyone"
    if n >= 1500:
        return "broadcaster"
    if n >= 500:
        return "moderator"
    if n >= 300:
        return "vip"                  # 300 = regular, 400 = VIP
    if n >= 250:
        return "subscriber"
    return "everyone"


def convert_reply(reply: str) -> tuple:
    """(the reply with this app's variables, [notes], works)."""
    notes, works, unknown = [], True, []

    def one(m):
        body = m.group(1).strip()
        low = body.lower()
        if low in SIMPLE:
            if low == "1:":
                notes.append("${1:} (what the viewer typed after the command) is $(query) here.")
            return SIMPLE[low]
        name, _, arg = body.partition(" ")
        lname = name.lower()
        if lname in ("count", "getcount") and arg.strip():
            return f"$({lname} {arg.strip()})"
        if lname.startswith("customapi.") or lname in ("customapi", "urlfetch"):
            url = body.split(".", 1)[1] if lname.startswith("customapi.") else arg
            notes.append("${customapi} is $(urlfetch) here: it works the same.")
            return f"$(urlfetch {url.strip()})"
        if re.fullmatch(r"\d+", lname):
            unknown.append("${" + body + "}")
            return m.group(0)
        if lname in SUPPORTED:
            return f"$({body})"
        unknown.append("${" + body + "}")
        return m.group(0)

    out = _SE.sub(one, str(reply or ""))
    if unknown:
        works = False
        notes.append("This app doesn't have " + ", ".join(sorted(set(unknown))) + ": imported switched off. Change it or delete it.")
    return out[:500], notes, works


async def fetch(channel: str) -> dict:
    """{"channel", "login", "commands": [StreamElements' command objects]}; NightbotError (with the reason) otherwise."""
    login = login_of(re.sub(r"streamelements\.com/", "twitch.tv/", str(channel or ""), flags=re.I))
    if not login:
        raise NightbotError("Type a Twitch channel name, like fqpn_.")
    headers = {"User-Agent": "FQPNsChatBot", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=headers) as s:
            async with s.get(API + "channels/" + login) as r:
                if r.status == 404:
                    raise NightbotError(f"StreamElements isn't set up on {login}, or that channel doesn't exist.")
                if r.status != 200:
                    raise NightbotError(f"StreamElements answered {r.status}. Try again in a minute.")
                ch = await r.json(content_type=None) or {}
            cid = ch.get("_id")
            if not cid:
                raise NightbotError(f"StreamElements isn't set up on {login}.")
            cmds = None
            for tail in ("/public", "/channel", ""):          # the public list (the page anyone can open)
                async with s.get(API + "bot/commands/" + str(cid) + tail) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        cmds = data if isinstance(data, list) else (data or {}).get("commands") or (data or {}).get("docs")
                        if isinstance(cmds, list):
                            break
            if cmds is None:
                raise NightbotError("StreamElements didn't give the commands. Check that the commands page is public, then try again.")
    except NightbotError:
        raise
    except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
        raise NightbotError("Couldn't reach StreamElements. Check the internet connection and try again.")
    return {"channel": ch.get("displayName") or ch.get("username") or login, "login": login,
            "commands": [c for c in cmds if isinstance(c, dict)]}


def preview(fetched: dict, existing: dict) -> list:
    """The same rows as Nightbot's preview, so the Import window and core/nightbot.apply work unchanged."""
    taken, bare = {}, {}
    for n, c in (existing or {}).items():
        for a in [n] + list((c or {}).get("aliases", [])):
            taken[a] = n
            bare.setdefault(a.lstrip("!"), n)
    rows = []
    for c in fetched.get("commands", []):
        word = " ".join(str(c.get("command") or "").split()).lower()
        if not word:
            continue
        name = word if word.startswith("!") else "!" + word
        reply, notes, works = convert_reply(c.get("reply") or "")
        if not reply:
            continue
        if c.get("enabled") is False:
            works = False
            notes.append("It's switched off in StreamElements: imported switched off.")
        if str(c.get("type") or "say") == "whisper":
            notes.append("StreamElements whispers this one: here it's said in chat.")
        if c.get("keywords") or c.get("regex"):
            notes.append("Its trigger words in StreamElements aren't imported: only the command itself.")
        if c.get("cost"):
            notes.append("It costs points in StreamElements: here it's free.")
        cd = c.get("cooldown") or {}
        cool = cd.get("global") if isinstance(cd, dict) else cd
        aliases = [("!" + a.lower().lstrip("!")) for a in (c.get("aliases") or []) if isinstance(a, str) and a.strip()]
        rows.append({"count": 0, "name": name[:60], "reply": reply, "level": level_of(c.get("accessLevel")),
                     "cooldown": max(0, min(86400, int(cool or 0))), "works": works, "notes": notes,
                     "clash": taken.get(name) or bare.get(name.lstrip("!")), "alias_of": None,
                     "aliases": [a for a in aliases if a not in taken][:10], "as_reply": str(c.get("type") or "") == "reply"})
    rows.sort(key=lambda r: r["name"])
    return rows


# ---------- the second way: the streamer's own StreamElements key (JWT) ----------
# StreamElements' sign-in for other apps isn't open to everyone, so the streamer pastes their own key (StreamElements
# dashboard → profile → Channels → Show secrets → JWT Token). It's used once, to read the commands and timers, and is
# never saved or sent anywhere but StreamElements.

async def fetch_with_key(key: str) -> dict:
    key = str(key or "").strip().removeprefix("Bearer ").strip()
    if len(key) < 40 or " " in key:
        raise NightbotError("That doesn't look like a StreamElements key. Copy the whole “JWT Token”.")
    headers = {"User-Agent": "FQPNsChatBot", "Accept": "application/json", "Authorization": "Bearer " + key}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=headers) as s:
            async with s.get(API + "channels/me") as r:
                if r.status in (401, 403):
                    raise NightbotError("StreamElements didn't accept that key. Copy the JWT Token again (it changes now and then).")
                if r.status != 200:
                    raise NightbotError(f"StreamElements answered {r.status}. Try again in a minute.")
                ch = await r.json(content_type=None) or {}
            cid = ch.get("_id")
            async with s.get(API + "bot/commands/" + str(cid)) as r:
                if r.status != 200:
                    raise NightbotError(f"StreamElements didn't give the commands ({r.status}). Try again.")
                cmds = await r.json(content_type=None)
            timers = []
            async with s.get(API + "bot/timers/" + str(cid)) as r:
                if r.status == 200:
                    timers = await r.json(content_type=None) or []
    except NightbotError:
        raise
    except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
        raise NightbotError("Couldn't reach StreamElements. Check the internet connection and try again.")
    cmds = cmds if isinstance(cmds, list) else (cmds or {}).get("commands") or []
    timers = timers if isinstance(timers, list) else (timers or {}).get("timers") or []
    return {"channel": ch.get("displayName") or ch.get("username") or "StreamElements", "login": str(ch.get("username") or ""),
            "commands": [c for c in cmds if isinstance(c, dict)], "timers": [t for t in timers if isinstance(t, dict)]}


def preview_timers(fetched: dict, existing: list) -> list:
    names = {str(t.get("name") or "").strip().lower(): t.get("name") for t in (existing or []) if isinstance(t, dict)}
    rows = []
    for t in fetched.get("timers", []):
        name = " ".join(str(t.get("name") or "").split())[:40]
        msgs = [m for m in (t.get("messages") or []) if isinstance(m, str) and m.strip()]
        if not name or not msgs:
            continue
        msg, notes, works = convert_reply(msgs[0])
        if len(msgs) > 1:
            notes.append(f"It has {len(msgs)} messages in StreamElements: only the first one comes along.")
        on = t.get("online") or {}
        mins = on.get("interval") if isinstance(on, dict) else None
        mins = int(mins or t.get("interval") or 15)
        lines = int(t.get("chatLines") or 0)
        lines = min(TIMER_LINES, key=lambda x: abs(x - lines))
        rows.append({"name": name, "reply": msg, "minutes": max(1, min(1440, mins)), "lines": lines, "works": works,
                     "notes": notes, "clash": names.get(name.lower()), "was_on": bool(t.get("enabled"))})
    return rows
