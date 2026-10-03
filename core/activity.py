"""Recent activity (commands, timers, greetings, events and, if switched on, chat) saved on this computer,
so the Logs page survives a restart. "Keep logs for" in Settings decides how long entries are kept."""

import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("activity")

MAX_SHOWN = 300          # entries held in memory and shown on the Logs page
MAX_FILE_LINES = 20000   # the file never grows past this, even with "Forever"
PRUNE_EVERY = 500        # re-check the file after this many new entries


def _parse(line: str):
    try:
        item = json.loads(line)
    except ValueError:
        return None
    if isinstance(item, dict) and isinstance(item.get("time"), str) and isinstance(item.get("kind"), str):
        return {"time": item["time"], "kind": item["kind"], "name": str(item.get("name", "")), "user": str(item.get("user", ""))}
    return None


def _when(item: dict):
    try:
        t = datetime.fromisoformat(item["time"])
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


class ActivityLog:
    def __init__(self, path, days_fn=lambda: 30):
        self.path = Path(path)
        self._days = days_fn            # how many days to keep (0 = forever), read each time so Settings changes apply
        self._items: deque = deque(maxlen=MAX_SHOWN)
        self._since_prune = 0
        self.prune()
        self._load()

    @property
    def items(self) -> deque:
        return self._items

    def _read_all(self) -> list:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            return []
        return [x for x in (_parse(line) for line in lines) if x]

    def _load(self) -> None:
        for item in self._read_all()[-MAX_SHOWN:]:
            self._items.append(item)

    def add(self, kind: str, name: str, user: str = "", when: datetime | None = None) -> dict:
        item = {"time": (when or datetime.now(timezone.utc)).isoformat(), "kind": kind,
                "name": str(name)[:300], "user": str(user)[:100]}
        self._items.append(item)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError:
            log.warning("Could not save the activity log", exc_info=True)
        self._since_prune += 1
        if self._since_prune >= PRUNE_EVERY:
            self.prune()
        return item

    def recent(self, n: int = 200) -> list:
        """Newest first."""
        return list(self._items)[::-1][:n]

    def prune(self) -> None:
        """Drops entries older than the chosen number of days, and keeps the file from growing without limit."""
        self._since_prune = 0
        try:
            days = int(self._days())
        except (TypeError, ValueError):
            days = 30
        items = self._read_all()
        if not items and not self.path.exists():
            return
        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            items = [x for x in items if (_when(x) or cutoff) >= cutoff]
        items = items[-MAX_FILE_LINES:]
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("Could not tidy the activity log", exc_info=True)
        keep = {x["time"] + x["kind"] + x["name"] for x in items}
        kept = [x for x in self._items if x["time"] + x["kind"] + x["name"] in keep]
        self._items.clear()
        self._items.extend(kept)
