"""Local JSON data store. Files are re-read automatically when they change,
so the future web dashboard can edit them while the bot is running."""

import copy
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DEFAULTS = {
    "commands": {
        "discord": {
            "response": "Join the Discord!",
            "permission": "everyone",
            "cooldown": 10,
            "enabled": True,
            "aliases": [],
        },
        "uptime": {
            "response": "$(channel) has been live for $(uptime).",
            "permission": "everyone",
            "cooldown": 15,
            "enabled": True,
            "aliases": [],
        },
    },
    "timers": [
        {
            "name": "follow",
            "message": "Don't forget to follow!",
            "interval_minutes": 20,
            "enabled": False,
        }
    ],
    "blocklist": {"users": [], "words": []},
    "settings": {
        "only_when_live": True,
        "paused": False,
        "live_check_seconds": 60,
        "commands_url": "",
    },
    "events": {   # automatic replies to Twitch events; each has tiers picked by the event's number
        "watch_streak": {"enabled": True, "tiers": [
            {"min": 1, "response": "HUGEEEEEE STREAKKKKKKK! {streak}-STREAM!"}]},
        "follow": {"enabled": False, "tiers": [
            {"min": 0, "response": "Welcome {user}! \u2764\ufe0f"}]},
        "subscription": {"enabled": False, "tiers": [
            {"min": 1, "response": "THANK YOU FOR THE SUB, {user}! \U0001f525"}]},
        "gift_sub": {"enabled": False, "tiers": [
            {"min": 1, "response": "{user} gifted a sub! THANK YOU! \u2764\ufe0f"},
            {"min": 5, "response": "{gifts} SUBS?! THANK YOU {user}! \U0001f525"},
            {"min": 10, "response": "{gifts} GIFTED SUBS FROM {user}!!! \U0001f525\U0001f525"},
            {"min": 25, "response": "{user} JUST GIFTED {gifts} SUBS!!! ABSOLUTE LEGEND! \U0001f6a8\U0001f525"}]},
        "raid": {"enabled": False, "tiers": [
            {"min": 1, "response": "HUGE RAID! Welcome {raider} and {viewers} raiders! \U0001f525"}]},
        "hype_train": {"enabled": False, "tiers": [
            {"min": 1, "response": "HYPE TRAIN LEVEL {level}! \U0001f682"},
            {"min": 5, "response": "LEVEL {level}?! CHAT IS INSANE \U0001f525"}]},
        "bits": {"enabled": False, "tiers": [
            {"min": 1, "response": "Thanks for the Bits, {user}! \u2764\ufe0f"},
            {"min": 100, "response": "{user} JUST DROPPED {bits} BITS! \U0001f525"},
            {"min": 500, "response": "{user} WITH {bits} BITS!!! \U0001f6a8"},
            {"min": 1000, "response": "{user} JUST DROPPED {bits} BITS!!! ABSOLUTE MADNESS! \U0001f525\U0001f525\U0001f525"}]},
    },
    "greetings": {"enabled": True, "users": []},   # people to greet, each with one or more messages
    "greeted": {"session": "", "users": [], "last": {}},   # who was already greeted during the current stream
    "counters": {},
}


class Store:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        self._cache: dict[str, tuple[float, object]] = {}
        for name in DEFAULTS:
            if self._read(name) is None:  # missing, empty, or broken file
                self.save(name, copy.deepcopy(DEFAULTS[name]))
        self._migrate()
        self._migrate_events()

    def _migrate_events(self) -> None:
        """Older versions stored the Watch Streak reply as {response, min_streak}. It becomes one tier, and any
        event that is missing gets its default, so nothing changes for people who already set things up."""
        ev = self._read("events")
        if not isinstance(ev, dict):
            return
        changed = False
        ws = ev.get("watch_streak")
        if isinstance(ws, dict) and "tiers" not in ws:
            try:
                low = max(1, int(ws.get("min_streak", 1)))
            except (TypeError, ValueError):
                low = 1
            text = str(ws.get("response") or "").strip() or DEFAULTS["events"]["watch_streak"]["tiers"][0]["response"]
            ev["watch_streak"] = {"enabled": bool(ws.get("enabled", True)), "tiers": [{"min": low, "response": text}]}
            changed = True
        for key, default in DEFAULTS["events"].items():
            if key not in ev:
                ev[key] = copy.deepcopy(default)
                changed = True
        if changed:
            self.save("events", ev)

    def _migrate(self) -> None:
        """Older versions kept a command prefix in settings and stored names without it.
        Now the creator picks each name exactly, so the old prefix is added to the names once."""
        settings = self._read("settings")
        if not isinstance(settings, dict) or "prefix" not in settings:
            return
        prefix = str(settings.pop("prefix") or "")
        commands = self._read("commands")
        if prefix and isinstance(commands, dict):
            counters = self._read("counters")
            counters = counters if isinstance(counters, dict) else {}
            new = {}
            for name, c in commands.items():
                full = (prefix + name).lower()
                if isinstance(c, dict):
                    c["aliases"] = [(prefix + a).lower() for a in c.get("aliases", [])]
                new[full] = c
                if f"cmd:{name}" in counters:
                    counters[f"cmd:{full}"] = counters.pop(f"cmd:{name}")
            self.save("commands", new)
            self.save("counters", counters)
        self.save("settings", settings)

    def _path(self, name: str) -> Path:
        return DATA_DIR / f"{name}.json"

    def _read(self, name: str):
        try:
            return json.loads(self._path(name).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def get(self, name: str):
        path = self._path(name)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return copy.deepcopy(DEFAULTS[name])
        cached = self._cache.get(name)
        if cached and cached[0] == mtime:
            return cached[1]
        data = self._read(name)
        if data is None:
            data = copy.deepcopy(DEFAULTS[name])
        self._cache[name] = (mtime, data)
        return data

    def save(self, name: str, data) -> None:
        self._path(name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._cache.pop(name, None)