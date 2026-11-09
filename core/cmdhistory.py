"""1.16.0 (owner): Command history and undo.

Every change to a command is remembered here (command_history.json): who changed it (you, a mod in chat with !cmadd /
!cmedit / !cmdel, the editor link, a backup restore), when, and the command before and after. The Commands page shows
this list (History), and any change can be undone: a deleted command comes back, an edit goes back to how it was.

The list is written by Store.save("commands", ...) itself, so every way of changing commands is covered. Only the last
MAX_ENTRIES changes are kept (the oldest go first)."""
import copy
import time

MAX_ENTRIES = 300
FIELDS = ("response", "permission", "cooldown", "enabled", "aliases", "action", "reply")   # what the page names


def _same(a: dict, b: dict) -> bool:
    return (a or {}) == (b or {})


def changed_fields(before: dict | None, after: dict | None) -> list:
    """What changed between two versions of a command: field names (FIELDS first, then "other")."""
    if before is None or after is None:
        return []
    out = [f for f in FIELDS if (before or {}).get(f) != (after or {}).get(f)]
    rest = (set(before) | set(after)) - set(FIELDS)
    if any(before.get(k) != after.get(k) for k in rest):
        out.append("other")
    return out


def diff(old: dict, new: dict) -> list:
    """The changes between two whole command lists: [{kind, name, old?, before, after}].
    kind: added / edited / deleted / renamed (one command gone and one new one with the same reply = renamed)."""
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}
    gone = [n for n in old if n not in new]
    came = [n for n in new if n not in old]
    out = []
    for n in list(gone):              # a rename: the same reply under a new name (the dashboard's edit window does this)
        twin = next((m for m in came if str((new[m] or {}).get("response")) == str((old[n] or {}).get("response"))), None)
        if twin is not None:
            out.append({"kind": "renamed", "name": twin, "old": n, "before": old[n], "after": new[twin]})
            gone.remove(n)
            came.remove(twin)
    for n in gone:
        out.append({"kind": "deleted", "name": n, "before": old[n], "after": None})
    for n in came:
        out.append({"kind": "added", "name": n, "before": None, "after": new[n]})
    for n in new:
        if n in old and not _same(old[n], new[n]):
            out.append({"kind": "edited", "name": n, "before": old[n], "after": new[n]})
    return out


def record(store, old: dict, new: dict, by: str) -> None:
    """Adds the changes between old and new to the history (newest last)."""
    changes = diff(old, new)
    if not changes:
        return
    hist = list(store.get("command_history") or [])
    now = time.time()
    base = int(now * 1000)
    last = max([int(h.get("id", 0)) for h in hist[-5:]] + [0])
    for i, c in enumerate(changes):
        nid = max(base + i, last + 1 + i)
        e = {"id": nid, "at": int(now), "by": str(by or "you")[:60], "kind": c["kind"], "name": c["name"],
             "before": copy.deepcopy(c["before"]), "after": copy.deepcopy(c["after"])}
        if c.get("old"):
            e["old"] = c["old"]
        hist.append(e)
    store.save_raw("command_history", hist[-MAX_ENTRIES:])


def view(store, name: str = "") -> list:
    """The page's list, newest first: each entry with what changed, and whether it can still be undone as it is."""
    hist = store.get("command_history") or []
    cur = store.get("commands") or {}
    name = str(name or "").strip().lower()
    out = []
    for e in reversed(hist):
        if name and name not in (e.get("name"), e.get("old")):
            continue
        out.append(dict(e, fields=changed_fields(e.get("before"), e.get("after")), state=_state(e, cur)))
    return out


def _state(e: dict, cur: dict) -> str:
    """'now' = the command is still exactly like this change left it; 'later' = it changed again since; 'gone' = a
    deleted command that is still deleted (it can come back); 'back' = a deleted command that exists again; 'missing' =
    the command isn't there anymore (deleted or renamed by a newer change)."""
    kind, name = e.get("kind"), e.get("name")
    if kind == "deleted":
        return "back" if name in cur else "gone"
    if name not in cur:
        return "missing"        # deleted (or renamed) since: the newer change undoes that first
    if _same(cur[name], e.get("after")):
        return "now"
    return "later"


class UndoError(Exception):
    pass


def undo(store, entry_id, validate=None, clash=None, by: str = "you") -> str:
    """Puts things back as they were before this change. Returns the command's name (as it is now)."""
    hist = store.get("command_history") or []
    e = next((h for h in hist if str(h.get("id")) == str(entry_id)), None)
    if e is None:
        raise UndoError("That change isn't in the history anymore.")
    commands = copy.deepcopy(store.get("commands") or {})
    kind, name = e.get("kind"), e.get("name")
    if kind == "added":
        if name not in commands:
            raise UndoError(f"{name} is already deleted.")
        del commands[name]
        result = name
    elif kind == "deleted":
        if name in commands:
            raise UndoError(f"There is a command called {name} again. Delete or rename it first.")
        commands[name] = copy.deepcopy(e.get("before"))
        result = name
    elif kind == "renamed":
        old = e.get("old")
        if name not in commands:
            raise UndoError(f"{name} isn't there anymore.")
        if old in commands:
            raise UndoError(f"There is a command called {old} again. Delete or rename it first.")
        del commands[name]
        commands[old] = copy.deepcopy(e.get("before"))
        result = old
    else:
        if name not in commands:
            raise UndoError(f"{name} was deleted since. Bring it back first.")
        commands[name] = copy.deepcopy(e.get("before"))
        result = name
    if validate:
        commands = validate(commands)
    if clash:
        reason = clash(commands)
        if reason:
            raise UndoError(reason)
    store.save("commands", commands, allow_empty=True, by=by)
    return result


def last_for(store, name: str):
    """The newest change of this command (for the page's Undo button right after a save or delete)."""
    for e in reversed(store.get("command_history") or []):
        if name in (e.get("name"), e.get("old")):
            return e
    return None


def undo_batch(store, entry_id, validate=None, clash=None) -> int:
    """Undoes every change saved together with this one (an import): newest first. Returns how many."""
    hist = store.get("command_history") or []
    e = next((h for h in hist if str(h.get("id")) == str(entry_id)), None)
    if e is None:
        raise UndoError("That change isn't in the history anymore.")
    same = [h for h in hist if h.get("at") == e.get("at") and h.get("by") == e.get("by")]
    n = 0
    for h in reversed(same):
        try:
            undo(store, h["id"], validate, clash, by="you (undo import)")
            n += 1
        except UndoError:
            pass
    return n
