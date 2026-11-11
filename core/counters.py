"""1.15.0 (owner): the Counters view (Commands > Custom > Counters) and the Dashboard's Counters card.

A counter is a named number that commands change with $(count name) (+1, shows it) and read with $(getcount name).
The numbers stay where they always were (counters.json, as "name:deaths", so backups keep them); counter_meta.json only
remembers the last change of each one ("+1 by chat 3 minutes ago", "set by you"), for the page.

A counter shows on the page when it has a number saved, or when one of your commands uses it (then it is 0 until the
first $(count))."""
import re
import time

from . import manage

MAX_COUNTERS = 100
MAX_VALUE = 10_000_000
_USE = re.compile(r"\$\((count|getcount)\s+([^)]*)\)", re.I)


class CounterError(Exception):
    pass


def norm(name) -> str:
    """The counter's real name: letters, digits and _ only, small letters, at most 30 (the same rule as $(count name))."""
    return re.sub(r"[^\w]", "", str(name or "").strip().casefold())[:30]


def _key(name: str) -> str:
    return "name:" + name


def note(store, name: str, how: str, by: str) -> None:
    """Remembers a counter's last change: how = "+1" / "-1" / "set" / "reset" / "new", by = "chat" / "you", or who reset
    it from chat (1.16.0: "sami (mod)")."""
    meta = dict(store.get("counter_meta") or {})
    meta[name] = {"at": int(time.time()), "how": how, "by": by}
    store.save("counter_meta", meta)


_PLAIN = re.compile(r"\$\(count\s*\)", re.I)


def reset_from_chat(store, owner: str, cmd: dict, by: str) -> list:
    """1.16.0 (owner): "!deaths reset" from a mod: every counter in this command's reply goes back to 0.
    Returns the counters reset (a plain $(count), the command's own counter, is "#"); [] = the reply has no counter."""
    resp = str((cmd or {}).get("response") or "")
    names = []
    for _, arg in _USE.findall(resp):
        n = norm(arg)
        if n and n not in names:
            names.append(n)
    plain = bool(_PLAIN.search(resp))
    if not names and not plain:
        return []
    counters = dict(store.get("counters") or {})
    for n in names:
        counters[_key(n)] = 0
    if plain:
        counters[f"cmd:{owner}"] = 0
    store.save("counters", counters)
    for n in names:
        note(store, n, "reset", by)
    return names + (["#"] if plain else [])


def uses(commands: dict) -> dict:
    """counter -> [(command, "adds" | "shows")], from every command's reply."""
    out: dict = {}
    for cname, c in (commands or {}).items():
        for kind, arg in _USE.findall(str((c or {}).get("response") or "")):
            n = norm(arg)
            if not n:
                continue
            what = "adds" if kind.lower() == "count" else "shows"
            if (cname, what) not in out.setdefault(n, []):
                out[n].append((cname, what))
    return out


def view(store) -> list:
    """Every counter for the page: [{name, value, used: [[command, adds|shows]], last: {at, how, by} | None}], A to Z."""
    counters = store.get("counters") or {}
    meta = store.get("counter_meta") or {}
    used = uses(store.get("commands") or {})
    names = {k[5:] for k in counters if k.startswith("name:")} | set(used)
    shown = set(_shown(store))
    return [{"name": n, "value": max(0, int(counters.get(_key(n), 0))), "used": [list(u) for u in used.get(n, [])],
             "last": meta.get(n), "stream": n in shown} for n in sorted(names)]


# ---------- 1.17.0: counters on stream (an OBS Browser Source: core/overlays.py) ----------
MAX_ON_STREAM = 8


def _shown(store) -> list:
    show = (store.get("counter_overlay") or {}).get("show") or []
    return [norm(x) for x in show if isinstance(x, str) and norm(x)][:MAX_ON_STREAM]


def _set_shown(store, names: list) -> None:
    store.save("counter_overlay", dict(store.get("counter_overlay") or {}, show=list(dict.fromkeys(names))[:MAX_ON_STREAM]))


def positions(store) -> dict:
    """1.17.0 (Overlays page): where each overlay sits on the screen and how big it is: {"c:deaths": [x, y, size]} with x and
    y in % of the width / height (its top-left corner) and size 0.5 to 3 (1 = normal). An overlay with no place sits in the
    top-left corner with the others."""
    out = {}
    for k, v in ((store.get("counter_overlay") or {}).get("pos") or {}).items():
        try:
            x, y = float(v[0]), float(v[1])
            size = float(v[2]) if len(v) > 2 and v[2] is not None else 1.0
        except (TypeError, ValueError, IndexError):
            continue
        out[str(k)[:70]] = [round(min(100.0, max(0.0, x)), 2), round(min(100.0, max(0.0, y)), 2), round(min(3.0, max(0.5, size)), 2)]
    return out


def set_position(store, key: str, x, y, size=1.0) -> None:
    pos = positions(store)
    key = str(key or "")[:70]
    if not key:
        return
    if x is None:
        pos.pop(key, None)
    else:
        pos[key] = [x, y, size]
    store.save("counter_overlay", dict(store.get("counter_overlay") or {}, pos=pos))
    store.save("counter_overlay", dict(store.get("counter_overlay") or {}, pos=positions(store)))     # (rounded, kept on screen)


def order(store) -> list:
    """1.17.0: the overlays in the order they were switched on ("first" = First in chat, "c:<name>" = a counter): the ones
    without a place stack in this order, so a new one goes at the bottom. (Before this was kept: First in chat first.)"""
    saved = [k for k in ((store.get("counter_overlay") or {}).get("order") or []) if isinstance(k, str)]
    want = (["first"] if first_on(store) else []) + ["c:" + n for n in _shown(store)]
    out = [k for k in saved if k in want]
    return out + [k for k in want if k not in out]


def _set_order(store, keys: list) -> None:
    store.save("counter_overlay", dict(store.get("counter_overlay") or {}, order=list(dict.fromkeys(keys))[:MAX_ON_STREAM + 1]))


def first_on(store) -> bool:
    return (store.get("counter_overlay") or {}).get("first", True) is not False


def set_first(store, on: bool) -> None:
    keys = [k for k in order(store) if k != "first"]
    store.save("counter_overlay", dict(store.get("counter_overlay") or {}, first=bool(on)))
    _set_order(store, keys + (["first"] if on else []))          # switched on now: at the bottom


def overlay(store, only: str = "") -> list:
    """What the overlay shows: [{name, value}] for the counters switched on (in the order they were switched on), or the
    ones named in ?only=deaths,wins (a separate Browser Source per counter)."""
    counters = store.get("counters") or {}
    want = [norm(x) for x in str(only or "").split(",") if norm(x)] or _shown(store)
    have = {v["name"] for v in view(store)}
    return [{"name": n, "value": max(0, int(counters.get(_key(n), 0)))} for n in want if n in have][:MAX_ON_STREAM]


def _value(v) -> int:
    if isinstance(v, bool):
        raise CounterError("Type a whole number.")
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise CounterError("Type a whole number.")
    if f != int(f):
        raise CounterError("Type a whole number.")
    if f < 0:
        raise CounterError("A counter can't go below 0.")          # 1.15.0 (owner): 0 is the lowest
    if abs(f) > MAX_VALUE:
        raise CounterError("That number is too big.")
    return int(f)


def _exists(store, name: str) -> bool:
    return _key(name) in (store.get("counters") or {}) or name in uses(store.get("commands") or {})


def _set(store, name: str, value: int, how: str) -> int:
    counters = dict(store.get("counters") or {})
    counters[_key(name)] = value
    store.save("counters", counters)
    note(store, name, how, "you")
    return value


def act(store, action: str, body: dict, validate_commands=None, clash=None) -> None:
    """The page's buttons. validate_commands / clash: the dashboard's own checks, for the commands made or renamed."""
    name = norm(body.get("name"))
    if action == "resetall":
        counters = dict(store.get("counters") or {})
        names = [v["name"] for v in view(store)]
        for n in names:
            counters[_key(n)] = 0
        store.save("counters", counters)
        meta = dict(store.get("counter_meta") or {})
        for n in names:
            meta[n] = {"at": int(time.time()), "how": "reset", "by": "you"}
        store.save("counter_meta", meta)
        return
    if action == "first":                  # 1.17.0: First in chat on the overlay, or not
        set_first(store, body.get("show"))
        return
    if action == "pos" and body.get("key") == "chat":     # 1.18.0: the Chat box: its place and its width and height
        from . import chatbox
        try:
            chatbox.set_box(store, float(body.get("x")), float(body.get("y")), float(body.get("w")), float(body.get("h")))
        except (TypeError, ValueError):
            raise CounterError("That place isn't on the screen.")
        return
    if action == "pos":                    # 1.17.0: an overlay dragged on the Overlays page's preview
        try:
            x, y = float(body.get("x")), float(body.get("y"))
            size = float(body.get("k") or 1)
        except (TypeError, ValueError):
            raise CounterError("That place isn't on the screen.")
        set_position(store, body.get("key"), x, y, size)
        return
    if action == "pos_reset":              # 1.17.0: all of them back to the top-left corner
        ov = dict(store.get("counter_overlay") or {}, pos={})
        ov.pop("chat_box", None)           # 1.18.0: the Chat box goes back to the bottom-left
        store.save("counter_overlay", ov)
        return
    if not name:
        raise CounterError("Give the counter a name: letters, numbers or _ (like deaths).")
    if action == "create":
        if _exists(store, name):
            raise CounterError(f"There is already a counter called {name}.")
        if len([v for v in view(store)]) >= MAX_COUNTERS:
            raise CounterError(f"You can have up to {MAX_COUNTERS} counters.")
        start = _value(body.get("start", 0))
        made = []
        if body.get("make_commands"):
            made = _make_commands(store, name, body, validate_commands, clash)
        _set(store, name, start, "new")
        return made
    if not _exists(store, name):
        raise CounterError(f"The counter {name} isn't there anymore.")
    if action == "stream":                 # 1.17.0: show it on stream (OBS) or not
        shown = [n for n in _shown(store) if n != name]
        keys = [k for k in order(store) if k != "c:" + name]
        if body.get("show"):
            if len(shown) >= MAX_ON_STREAM:
                raise CounterError(f"Up to {MAX_ON_STREAM} counters can be on stream at once.")
            shown.append(name)
            keys.append("c:" + name)                                # switched on now: at the bottom
        _set_shown(store, shown)
        _set_order(store, keys)
        return
    if action == "set":
        _set(store, name, _value(body.get("value")), "set")
    elif action == "add":
        try:
            step = int(float(body.get("by", 1)))
        except (TypeError, ValueError):
            step = 1
        cur = max(0, int((store.get("counters") or {}).get(_key(name), 0)))     # (below 0 from before 1.15.0 = 0)
        step = 1 if step > 0 else -1
        if cur + step < 0:
            raise CounterError(f"{name} is already 0: a counter can't go below 0.")
        _set(store, name, min(MAX_VALUE, cur + step), "+1" if step > 0 else "-1")
    elif action == "reset":
        _set(store, name, 0, "reset")
    elif action == "delete":
        users = [c for c, _ in uses(store.get("commands") or {}).get(name, [])]
        if users:                       # it would only come back at 0: the commands still count it
            raise CounterError(f"{' and '.join(users[:3])} still use this counter. Change or delete "
                               f"{'that command' if len(users) == 1 else 'those commands'} first.")
        counters = dict(store.get("counters") or {})
        counters.pop(_key(name), None)
        store.save("counters", counters)
        meta = dict(store.get("counter_meta") or {})
        meta.pop(name, None)
        store.save("counter_meta", meta)
        if name in _shown(store):
            _set_shown(store, [n for n in _shown(store) if n != name])
        if "c:" + name in positions(store):
            set_position(store, "c:" + name, None, None)
    elif action == "rename":
        new = norm(body.get("new"))
        if not new:
            raise CounterError("Give the counter a name: letters, numbers or _ (like deaths).")
        if new == name:
            return
        if _exists(store, new):
            raise CounterError(f"There is already a counter called {new}.")
        commands = dict(store.get("commands") or {})
        changed = False
        for cname, c in commands.items():
            resp = str((c or {}).get("response") or "")
            fixed = _USE.sub(lambda m: f"$({m.group(1)} {new})" if norm(m.group(2)) == name else m.group(0), resp)
            if fixed != resp:
                commands[cname] = dict(c, response=fixed)
                changed = True
        if changed:
            if validate_commands:
                commands = validate_commands(commands)
            store.save("commands", commands)
        counters = dict(store.get("counters") or {})
        if _key(name) in counters:
            counters[_key(new)] = counters.pop(_key(name))
        store.save("counters", counters)
        meta = dict(store.get("counter_meta") or {})
        if name in meta:
            meta[new] = meta.pop(name)
        store.save("counter_meta", meta)
        if name in _shown(store):           # it stays on stream under its new name (and in its place)
            _set_shown(store, [new if n == name else n for n in _shown(store)])
        _set_order(store, ["c:" + new if k == "c:" + name else k for k in order(store)])
        pos = positions(store)
        if "c:" + name in pos:
            x, y, size = pos["c:" + name]
            set_position(store, "c:" + name, None, None)
            set_position(store, "c:" + new, x, y, size)
    else:
        raise CounterError("Unknown action.")


def _make_commands(store, name: str, body: dict, validate_commands, clash) -> list:
    """"Also make the commands for me": one that adds 1 (moderators) and one that shows the number (everyone)."""
    ar = body.get("lang") == "ar"
    add_name = manage.clean_name(str(body.get("add_cmd") or "")) if str(body.get("add_cmd") or "").strip() else ""
    show_name = manage.clean_name(str(body.get("show_cmd") or "")) if str(body.get("show_cmd") or "").strip() else ""
    if not add_name and not show_name:
        return []
    if add_name and add_name == show_name:
        raise CounterError("The two commands need different names.")
    commands = dict(store.get("commands") or {})
    used = manage.names_in_use(commands)
    for n in (add_name, show_name):
        if n and n in used:
            raise CounterError(f"{n} is already one of your commands. Choose another name.")
    made = []
    if add_name:
        commands[add_name] = {"response": (f"+1 {name}! صار العدد: $(count {name})" if ar else f"+1 {name}! Now at $(count {name})"),
                              "permission": "moderator", "cooldown": 5, "enabled": True, "aliases": []}
        made.append(add_name)
    if show_name:
        commands[show_name] = {"response": (f"{name}: $(getcount {name})"),
                               "permission": "everyone", "cooldown": 10, "enabled": True, "aliases": []}
        made.append(show_name)
    if validate_commands:
        commands = validate_commands(commands)
    if clash:
        reason = clash(commands)
        if reason:
            raise CounterError(reason)
    store.save("commands", commands)
    return made
