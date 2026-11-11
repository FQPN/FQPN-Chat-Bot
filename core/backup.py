"""1.14.0: Backup & restore (Settings > App).

One file (.fqpn, JSON inside) with the channel's whole setup. NEVER in it: Twitch / bot account logins, donation keys,
the editor link, logs (those live in other files, which this module never reads). Restoring checks every part the
same way a normal save does; a part that doesn't pass is skipped and named, the rest is restored."""
import json
import logging
import time
from datetime import datetime

log = logging.getLogger(__name__)

APP = "FQPN's Chat Bot"
FORMAT = 1                      # the file layout; a newer one is refused ("update the app first")
# What a backup holds (store names). The giveaway part is its settings only (never a running giveaway or its entries).
PARTS = ["commands", "timers", "events", "greetings", "blocklist", "moderation", "games", "game_wins", "counters",
         "stream", "giveaway", "settings", "prefs", "ui", "follow_dates", "voice_fixes", "chatbox", "public_banner",
         "viewer_stats", "chat_colors"]     # 1.18.0 (Twitch panel): each viewer's messages and watch time     # 1.18.0: + first follow dates, Voice spelling fixes
MAX_BYTES = 5_000_000


def file_name(prefix: str = "FQPN-Chat-Bot-backup", when: float = None, minutes: bool = False) -> str:
    d = datetime.fromtimestamp(when or time.time())
    return f"{prefix}-{d:%Y-%m-%d}" + (f"-{d:%H%M}" if minutes else "") + ".fqpn"


def make(store, version: str, channel: str) -> dict:
    parts = {}
    for name in PARTS:
        data = store.get(name)
        if name == "giveaway":
            data = {"settings": dict((data or {}).get("settings") or {})}
        parts[name] = data
    return {"app": APP, "format": FORMAT, "version": str(version or ""), "channel": str(channel or ""),
            "made": int(time.time()), "parts": parts}


def dumps(backup: dict) -> str:
    return json.dumps(backup, ensure_ascii=False, indent=1)


def summary(backup: dict) -> dict:
    """What the page shows before restoring: counts of the main things, and which parts are in the file."""
    p = backup.get("parts") or {}
    def n(x):
        return len(x) if isinstance(x, (dict, list)) else 0
    games = p.get("games") if isinstance(p.get("games"), dict) else {}
    return {"version": backup.get("version", ""), "channel": backup.get("channel", ""), "made": backup.get("made", 0),
            "commands": n(p.get("commands")), "timers": n(p.get("timers")),
            "events": sum(1 for e in (p.get("events") or {}).values() if isinstance(e, dict) and e.get("enabled")) if isinstance(p.get("events"), dict) else 0,
            "greetings": n((p.get("greetings") or {}).get("users")) if isinstance(p.get("greetings"), dict) else 0,
            "blocked": n((p.get("blocklist") or {}).get("users")) + n((p.get("blocklist") or {}).get("timed")) if isinstance(p.get("blocklist"), dict) else 0,
            "games": sum(1 for k, g in games.items() if k != "shared" and isinstance(g, dict) and g.get("enabled")),
            "parts": [k for k in PARTS if k in p]}


class BackupError(Exception):
    """A file that can't be restored at all (the page shows the message; nothing changes)."""


def read(text) -> dict:
    """Parse and check the outside of a backup file. Raises BackupError with a plain message."""
    if isinstance(text, (bytes, bytearray)):
        if len(text) > MAX_BYTES:
            raise BackupError("too_big")
        text = text.decode("utf-8-sig", errors="replace")
    if not isinstance(text, str) or len(text) > MAX_BYTES:
        raise BackupError("too_big")
    try:
        data = json.loads(text)
    except ValueError:
        raise BackupError("not_backup")
    if not isinstance(data, dict) or data.get("app") != APP or not isinstance(data.get("parts"), dict):
        raise BackupError("not_backup")
    if not isinstance(data.get("format"), int) or data["format"] > FORMAT:
        raise BackupError("newer")
    return data


def restore(store, backup: dict, validate, apply_side_effects=None) -> dict:
    """Restore every part that passes `validate(name, data)` (the dashboard's own checks). Returns
    {"restored": [...], "skipped": [...]}. `apply_side_effects(name, old, new)` runs after each saved part."""
    from . import giveaway
    done, skipped = [], []
    parts = backup.get("parts") or {}
    for name in PARTS:
        if name not in parts:
            continue
        raw = parts[name]
        try:
            if name == "giveaway":
                if not isinstance(raw, dict) or not isinstance(raw.get("settings"), dict):
                    raise ValueError("giveaway")
                old = store.get("giveaway")
                giveaway.update_settings(store, raw["settings"])
                done.append(name)
                continue
            if name == "follow_dates":          # 1.18.0: merged, the earliest date of each person wins (nothing is lost)
                if not isinstance(raw, dict):
                    raise ValueError("follow_dates")
                data = dict(store.get("follow_dates") or {})
                for uid, v in list(raw.items())[:500000]:
                    if not isinstance(v, (list, tuple)) or not v or isinstance(v[0], bool) or not isinstance(v[0], (int, float)):
                        continue
                    old = data.get(str(uid)[:30])
                    if not (isinstance(old, (list, tuple)) and old and isinstance(old[0], (int, float)) and old[0] <= v[0]):
                        data[str(uid)[:30]] = [float(v[0]), str(v[1])[:40] if len(v) > 1 else ""]
                store.save(name, data, allow_empty=True)
                done.append(name)
                continue
            if name == "viewer_stats":          # 1.18.0: merged, each number the bigger one (nothing is lost)
                if not isinstance(raw, dict) or not isinstance(raw.get("users"), dict):
                    raise ValueError("viewer_stats")
                data = merge_viewer_stats(store.get("viewer_stats") or {}, raw)
                old = store.get(name)
                store.save(name, data, allow_empty=True)
                if apply_side_effects:
                    apply_side_effects(name, old, data)
                done.append(name)
                continue
            if name == "chat_colors":           # 1.18.0: the !color name colors, checked
                from . import chatbox
                data = chatbox.clean_colors(raw)
                store.save(name, data, allow_empty=True)
                done.append(name)
                continue
            if name == "counters":
                if not isinstance(raw, dict):
                    raise ValueError("counters")
                data = {str(k)[:60]: int(v) for k, v in raw.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
            else:
                data = validate(name, raw)
            old = store.get(name)
            store.save(name, data, allow_empty=True, **({"by": "backup restore"} if name == "commands" else {}))
            if apply_side_effects:
                apply_side_effects(name, old, data)
            done.append(name)
        except Exception as e:                  # a damaged or unknown part: skipped and named, the rest goes on
            log.warning("Backup: the part %r was skipped (%s)", name, str(e)[:200])
            skipped.append(name)
    return {"restored": done, "skipped": skipped}


def _num(x) -> int:
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else 0


def merge_viewer_stats(cur: dict, raw: dict) -> dict:
    """1.18.0: a backup's messages and watch time put together with this PC's: for each viewer the bigger number."""
    users = dict((cur or {}).get("users") or {})
    for k, e in list((raw.get("users") or {}).items())[:50000]:
        if not isinstance(e, dict):
            continue
        k = str(k)[:40]
        mine = dict(users.get(k) or {})
        out = {"n": str(e.get("n") or mine.get("n") or "")[:40], "l": str(e.get("l") or mine.get("l") or "")[:25].lower(),
               "m": max(_num(e.get("m")), _num(mine.get("m"))), "t": max(_num(e.get("t")), _num(mine.get("t"))),
               "last": max(_num(e.get("last")), _num(mine.get("last")))}
        for p in ("week", "month"):
            a, b = e.get(p), mine.get(p)
            a = a if isinstance(a, dict) and isinstance(a.get("id"), str) else None
            b = b if isinstance(b, dict) and isinstance(b.get("id"), str) else None
            if a and b and a["id"] == b["id"]:
                out[p] = {"id": a["id"], "m": max(_num(a.get("m")), _num(b.get("m"))), "t": max(_num(a.get("t")), _num(b.get("t")))}
            elif a or b:
                x = max([y for y in (a, b) if y], key=lambda y: y["id"])
                out[p] = {"id": x["id"][:10], "m": _num(x.get("m")), "t": _num(x.get("t"))}
        users[k] = out
    return {"users": users, "wizebot": dict((cur or {}).get("wizebot") or (raw.get("wizebot") if isinstance(raw.get("wizebot"), dict) else {}) or {})}
