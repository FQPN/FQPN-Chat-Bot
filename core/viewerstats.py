"""1.18.0 (Twitch panel): each viewer's chat messages and watch time, for the leaderboard panel under the stream.

Kept in the store section "viewer_stats":
    {"users": {key: {"n": display name, "l": login, "m": messages, "t": seconds watched,
                     "week": {"id": "2026-11-08", "m": .., "t": ..}, "month": {"id": "2026-11", "m": .., "t": ..},
                     "last": when they were last seen}},
     "wizebot": {"at": when, "count": how many viewers came from WizeBot}}
key = the Twitch user ID. Someone who came from WizeBot without a usable ID is kept as "wz:<login>" until they write in
chat; then their numbers move to their real ID.

Messages are counted as they come in. Watch time: while the channel is live, the bot asks Twitch every few minutes who is
in the chat (people who never write too) and adds the minutes since the last look. "This week" starts on Sunday and
"this month" on the 1st, on this PC's clock (like the mini games' leaderboards).
Saved at most once a minute (and when the app closes), so a busy chat never means a save per message."""
import re
import time

from . import minigames

SAVE_EVERY = 60          # seconds between saves
MAX_USERS = 20000        # a very big channel: the smallest and longest-unseen go first
KEEP_AFTER_TRIM = 15000
WATCH_GAP_MAX = 600      # never more than 10 minutes for one look (the PC slept, the app was closed...)
NUM_RE = re.compile(r"^\d{1,20}$")
LOGIN_RE = re.compile(r"^[a-z0-9_]{1,25}$")
PERIODS = minigames.PERIODS


def period_ids(now=None) -> dict:
    return minigames.period_ids(now)


def _sub(e: dict, p: str, pid: str) -> dict:
    s = e.get(p)
    if not isinstance(s, dict) or s.get("id") != pid:
        s = {"id": pid, "m": 0, "t": 0}
        e[p] = s
    return s


def value(e: dict, kind: str, period=None, now=None) -> int:
    """kind "m" (messages) or "t" (seconds watched); period None (all time), "week" or "month" (0 once it's over)."""
    if not isinstance(e, dict):
        return 0
    if period:
        s = e.get(period)
        if not isinstance(s, dict) or s.get("id") != period_ids(now)[period]:
            return 0
        return int(s.get(kind) or 0)
    return int(e.get(kind) or 0)


class ViewerStats:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        d = store.get("viewer_stats") or {}
        self.data = {"users": dict(d.get("users") or {}), "wizebot": dict(d.get("wizebot") or {})}
        self.dirty, self.saved_at = False, clock()
        self.last_watch = 0.0
        if self._fix_totals(self.data["users"].values()):
            self.dirty = True

    @staticmethod
    def _fix_totals(people) -> bool:
        """All time is never less than this week / this month (someone imported only in WizeBot's weekly top 100 had 0)."""
        changed = False
        for e in people:
            if not isinstance(e, dict):
                continue
            for k in ("m", "t"):
                best = max([int(e.get(k) or 0)] + [int((e.get(p) or {}).get(k) or 0) for p in PERIODS if isinstance(e.get(p), dict)])
                if best > int(e.get(k) or 0):
                    e[k] = best
                    changed = True
        return changed

    # ---------- counting

    def _user(self, uid, login, name) -> dict | None:
        uid, login = str(uid or "").strip(), str(login or "").strip().lower()
        if not NUM_RE.match(uid):
            return None
        users = self.data["users"]
        e = users.get(uid)
        if e is None:
            e = users[uid] = {"n": name or login, "l": login, "m": 0, "t": 0}
            old = users.pop("wz:" + login, None) if login else None
            if isinstance(old, dict):                     # came from WizeBot by name only: their numbers move here
                for k in ("m", "t"):
                    e[k] = int(old.get(k) or 0)
                for p in PERIODS:
                    if isinstance(old.get(p), dict):
                        e[p] = dict(old[p])
        if name:
            e["n"] = str(name)[:40]
        if login:
            e["l"] = login
        e["last"] = int(self.clock())
        return e

    def message(self, uid, login, name) -> None:
        e = self._user(uid, login, name)
        if e is None:
            return
        e["m"] = int(e.get("m") or 0) + 1
        for p, pid in period_ids(self.clock()).items():
            s = _sub(e, p, pid)
            s["m"] = int(s.get("m") or 0) + 1
        self.dirty = True

    def watch(self, people) -> int:
        """One look at who is in the chat: people = [(uid, login, name)]. Adds the time since the last look (the first
        look of a session counts as a normal gap). Returns the seconds added to each."""
        now = self.clock()
        gap = int(min(WATCH_GAP_MAX, max(0, now - self.last_watch))) if self.last_watch else 0
        self.last_watch = now
        if gap <= 0:
            return 0
        pids = period_ids(now)
        for uid, login, name in people:
            e = self._user(uid, login, name)
            if e is None:
                continue
            e["t"] = int(e.get("t") or 0) + gap
            for p, pid in pids.items():
                s = _sub(e, p, pid)
                s["t"] = int(s.get("t") or 0) + gap
        self.dirty = True
        return gap

    def offline(self) -> None:
        """The stream ended: the next look starts a new count (the time offline isn't watch time)."""
        self.last_watch = 0.0

    def _trim(self) -> None:
        users = self.data["users"]
        if len(users) <= MAX_USERS:
            return
        ranked = sorted(users.items(), key=lambda kv: (int(kv[1].get("t") or 0) + 60 * int(kv[1].get("m") or 0), int(kv[1].get("last") or 0)), reverse=True)
        self.data["users"] = dict(ranked[:KEEP_AFTER_TRIM])

    def flush(self, force=False) -> None:
        if not self.dirty or (not force and self.clock() - self.saved_at < SAVE_EVERY):
            return
        self._trim()
        self.store.save("viewer_stats", {"users": self.data["users"], "wizebot": self.data["wizebot"]})
        self.dirty, self.saved_at = False, self.clock()

    # ---------- reading

    def top(self, kind: str, period=None, n: int = 100) -> list:
        """[(key, login, name, value)] best first, nobody with 0."""
        now = self.clock()
        rows = [(k, e.get("l") or "", e.get("n") or e.get("l") or "?", value(e, kind, period, now)) for k, e in self.data["users"].items() if isinstance(e, dict)]
        rows = [r for r in rows if r[3] > 0]
        rows.sort(key=lambda r: (-r[3], str(r[2]).lower()))
        return rows[:n]

    # ---------- WizeBot (once)

    def import_wizebot(self, lists: dict, unit: int = 1) -> int:
        """lists = {("t" | "m", None | "week" | "month"): [{"user_name", "user_uid", "value"}]} from WizeBot's top 100.
        unit = seconds per WizeBot unit for watch time (1 = WizeBot counts seconds, 60 = minutes). Never adds up twice:
        each number becomes the bigger of WizeBot's and this app's (the app may have counted the same time already).
        Returns how many viewers it touched."""
        now = self.clock()
        pids = period_ids(now)
        users = self.data["users"]
        by_login = {e.get("l"): k for k, e in users.items() if isinstance(e, dict) and e.get("l")}
        touched = set()
        for (kind, period), rows in (lists or {}).items():
            if kind not in ("m", "t") or period not in (None, "week", "month"):
                continue
            for r in rows or []:
                if not isinstance(r, dict):
                    continue
                login = str(r.get("user_name") or "").strip().lower().lstrip("@")
                if not LOGIN_RE.match(login):
                    continue
                try:
                    v = int(float(str(r.get("value") or 0)))
                except ValueError:
                    continue
                if v <= 0:
                    continue
                if kind == "t":
                    v *= max(1, int(unit))
                uid = str(r.get("user_uid") or "").strip()
                key = by_login.get(login) or (uid if NUM_RE.match(uid) and uid in users else None) or (uid if NUM_RE.match(uid) else "wz:" + login)
                e = users.setdefault(key, {"n": login, "l": login, "m": 0, "t": 0})
                e.setdefault("l", login)
                by_login[login] = key
                if period is None:
                    e[kind] = max(int(e.get(kind) or 0), v)
                else:
                    s = _sub(e, period, pids[period])
                    s[kind] = max(int(s.get(kind) or 0), v)
                touched.add(key)
        self._fix_totals(users[k] for k in touched)
        if touched:
            self.data["wizebot"] = {"at": int(now), "count": len(touched)}
            self.dirty = True
            self.flush(force=True)
        return len(touched)
