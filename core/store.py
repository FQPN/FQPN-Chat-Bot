"""Local JSON data store. Files are re-read automatically when they change,
so the future web dashboard can edit them while the bot is running."""

import copy
import json
import logging
import time
from pathlib import Path

from . import manage, minigames, moderation, safefile
from .activity import ActivityLog

log = logging.getLogger("twitchbot.store")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# 1.12.0 (several channels): these stay in data/ and are shared by every channel; everything else is per channel, in
# data/channels/<twitch user id>/. A Store without a channel uses data/ for everything (the layout before 1.12.0).
SHARED = ("ui", "prefs")
# Never replace a real list with an empty one in one save (a bug or a half-loaded page must not wipe your commands).
# A list of at least this many entries can only become empty with allow_empty=True (a deliberate "remove everything").
EMPTY_GUARD_MIN = 3
GUARDED = {
    "commands": lambda d: len(d) if isinstance(d, dict) else 0,
    "timers": lambda d: len(d) if isinstance(d, list) else 0,
    "greetings": lambda d: len((d or {}).get("users") or []) if isinstance(d, dict) else 0,
    "blocklist": lambda d: len((d or {}).get("users") or []) if isinstance(d, dict) else 0,
}


class EmptySaveRefused(ValueError):
    """A save would have replaced a real list (commands, timers, ...) with an empty one."""

DEFAULTS = {
    "moderation": moderation.defaults(),    # the Moderation page: bad words, links, caps, emotes, symbols, repeats (all off at first)
    "games": minigames.defaults(),          # Mini games: letters (اسم، جماد، نبات، حيوان، بلاد) and scramble (رتب); off at first
    "game_rounds": {"stream": None, "rounds": 0},   # rounds played this stream (the "rounds per stream" limit; refills each stream)
    "game_wins": {},                        # wins per viewer: {user_id: {"name": ..., "wins": total, "games": {"letters": n, "scramble": m}}}
    "stream": {                       # the messages the bot says when your stream starts, comes back and ends (off until switched on)
        "enabled": True,              # the master switch for all four (each one also has its own switch)
        "start": {"enabled": False, "text": ""},       # an empty text means "the default in the app's language"
        "followers": {"enabled": False, "text": ""},
        "resume": {"enabled": False, "text": ""},
        "end": {"enabled": False, "text": ""},
        "end_after_minutes": 2,        # offline this long = the stream really ended (a shorter drop is ignored)
        "resume_within_minutes": 15,   # back within this long after a drop = the same stream continues
    },
    "usage_state": {"banned": False},       # kept by the app, not a setting: did the developer turn the app off for this channel
    "publist_state": {                # kept by the app, not a setting: what was last sent to the public list website
        "uploaded": False, "digest": "", "login": "", "at": None,
    },
    "stream_state": {                 # kept by the app, not a setting: where the current stream session stands
        "state": "idle", "seg_start": None, "live_seconds": 0.0, "offline_since": None, "ended_at": None,
        "last_seen": 0.0, "end_total": None, "title": "", "category": "",
    },
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
        "start_active": True,   # when off, the bot starts paused every time the app opens
        "live_check_seconds": 60,
        "commands_url": "",
        "disabled_builtins": [],   # built-in commands switched off in Commands > Built-in
        "separate_bot": False,     # the bot talks from its own Twitch account (Settings > Bot > Chat account)
        "public_list": True,       # keep a public copy of the command list on the website (Commands > Public list). On for NEW
                                   # installs since 1.10.0; existing settings files keep their value (missing = off)
        "public_hidden": [],       # command names left off the public list (kept here so the commands themselves don't change)
    },
    "prefs": {   # how the installed app behaves (Settings > App, Notifications, Logs and data)
        "startup": False,          # start with Windows
        "start_minimized": False,  # when started with Windows, go to the tray instead of showing the window
        "on_close": "quit",        # "quit" or "tray"
        "auto_reconnect": True,    # start the bot again by itself if the Twitch connection drops
        "auto_update": True,       # look for new versions and download them quietly
        "notify": True,            # desktop pop-ups
        "notify_sound": False,
        "log_days": 30,            # keep logs for this many days (0 = forever)
        "log_chat": False,         # also save viewers' chat messages
    },
    "ui": {   # how the dashboard looks (saved here so it also sticks inside the installed app)
        "dark": True,
        "language": "en",
        "fontSize": "medium",
        "accent": "#9a1118",
        "compact": False,
        "reduceMotion": False,
        "tourDone": False,         # the guided tour has been seen (finished or skipped), so it does not start by itself again
        "gsDone": False,           # the "Getting started" checklist reached 5 of 5: it stays hidden from then on
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
        "donation": {"enabled": False, "tiers": [      # replies by amount (in the donation's own currency)
            {"min": 0, "response": "Thank you {user} for the {amount} {currency} donation! \u2764\ufe0f"},
            {"min": 50, "response": "WOW! {user} donated {amount} {currency}! You are amazing! \U0001f525"}]},
    },
    "greetings": {"enabled": True, "users": []},   # people to greet, each with one or more messages
    "greeted": {"session": "", "users": [], "last": {}},   # who was already greeted during the current stream
    "counters": {},
}


class Store:
    def __init__(self, channel=None):
        self.channel = str(channel) if channel else None     # None = everything in data/ (before 1.12.0)
        self.problems: dict = {}                             # section -> what happened to a damaged file (shown in the app)
        self.dir.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)
        self._cache: dict[str, tuple[float, object]] = {}
        # 1.9.0: counts every save, so the dashboard reloads the settings only when something changed (it used to download
        # every section every 6 seconds). "boot" makes the value new after a restart.
        self.boot = int(time.time() * 1000)
        self.rev = 0
        for name in DEFAULTS:
            # A missing file gets its defaults. A damaged one is NEVER replaced by the defaults: it is copied aside and its
            # last good backup is used; with no good backup the defaults are only used in memory, and the app warns.
            status, _ = safefile.read(self._path(name))
            if status == "missing":
                self.save(name, copy.deepcopy(DEFAULTS[name]))
            elif status == "corrupt":
                self._recover(name)
        self._migrate()
        self._migrate_events()
        self._migrate_blocked_words()
        self._migrate_games()
        # the activity shown on the Logs page, saved so it survives a restart
        self.activity = ActivityLog(self.dir / "activity.jsonl", days_fn=lambda: self.get("prefs").get("log_days", 30))

    @property
    def dir(self) -> Path:
        """Where this channel's files are: data/channels/<id>/ (or data/ for the layout before 1.12.0)."""
        return DATA_DIR / "channels" / self.channel if self.channel else DATA_DIR

    def _recover(self, name: str):
        """A damaged file: copy it aside, then use its last good backup if there is one. Returns the data or None."""
        path = self._path(name)
        kept = safefile.quarantine(path)
        data = safefile.restore_backup(path)
        if data is not None:
            self.problems[name] = {"what": "restored", "kept": kept.name if kept else ""}
            log.warning("%s was damaged: restored its last good backup (the damaged copy is kept as %s)", path.name, kept)
        else:
            self.problems[name] = {"what": "damaged", "kept": kept.name if kept else ""}
            log.error("%s is damaged and has no good backup: it is kept as it is (copy: %s); the defaults are used in "
                      "memory until something is saved", path.name, kept)
        self._cache.pop(name, None)
        return data

    def use_channel(self, channel) -> None:
        """Switches this store to a channel's folder (after the one-time move to one folder per channel)."""
        self.__init__(channel)

    def apply_launch_defaults(self) -> None:
        """Run once when the app opens: 'Start the bot when the app opens' decides whether the bot starts active or paused."""
        settings = dict(self.get("settings"))
        want_paused = settings.get("start_active", True) is False
        if bool(settings.get("paused")) != want_paused:
            settings["paused"] = want_paused
            self.save("settings", settings)

    def _migrate_blocked_words(self) -> None:
        """1.5.0 removed "Blocked words" from the Blocklist. Words saved there move into Moderation > Bad words, which stays
        switched off, so nothing changes in chat until the streamer turns it on (blocked words only made the bot ignore a message)."""
        block = self._read("blocklist")
        if not isinstance(block, dict) or not block.get("words"):
            return
        mod = self._read("moderation")
        mod = mod if isinstance(mod, dict) else copy.deepcopy(DEFAULTS["moderation"])
        bw = mod.setdefault("badwords", copy.deepcopy(DEFAULTS["moderation"]["badwords"]))
        have = {str(e.get("w", "")).lower() for e in bw.get("words", []) if isinstance(e, dict)}
        for w in block["words"]:
            w = " ".join(str(w).split())
            if w and w.lower() not in have:
                bw.setdefault("words", []).append({"w": w, "anywhere": True})   # blocked words matched anywhere, so they keep doing that
                have.add(w.lower())
        self.save("moderation", mod)
        block["words"] = []
        self.save("blocklist", block)

    def _migrate_games(self) -> None:
        """1.9.0 added «رتب»: a game missing from games.json gets its default settings (switched off), and saved wins
        get the per-game count (every win before 1.9.0 was a letters-game win), so the leaderboards keep everyone's wins."""
        games = self._read("games")
        if isinstance(games, dict):
            missing = [k for k in minigames.GAME_KEYS if not isinstance(games.get(k), dict)]
            for k in missing:
                games[k] = copy.deepcopy(DEFAULTS["games"][k])
            commands = self._read("commands")
            custom = manage.names_in_use(commands) if isinstance(commands, dict) else {}
            if minigames.upgrade_games(games, custom) or missing:      # the shared commands move to "All games"
                self.save("games", games)
        wins = self._read("game_wins")
        if isinstance(wins, dict) and minigames.upgrade_wins(wins):
            self.save("game_wins", wins)

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
        return (DATA_DIR if name in SHARED else self.dir) / f"{name}.json"

    def _read(self, name: str):
        status, data = safefile.read(self._path(name))
        if status == "ok":
            return data
        if status == "corrupt" and name in DEFAULTS and self.problems.get(name, {}).get("what") != "damaged":
            return self._recover(name)        # damaged while the app runs (edited by hand?): same care as at start
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

    def save(self, name: str, data, allow_empty: bool = False) -> None:
        count = GUARDED.get(name)
        if count is not None and not allow_empty and count(data) == 0:
            status, old = safefile.read(self._path(name))
            if status == "ok" and count(old) >= EMPTY_GUARD_MIN:
                log.error("Refused to save an empty %s over %d entries", name, count(old))
                raise EmptySaveRefused(f"Refused to replace {count(old)} saved {name} with an empty list.")
        safefile.write(self._path(name), data)
        self.problems.pop(name, None) if self.problems.get(name, {}).get("what") == "damaged" else None
        self._cache.pop(name, None)
        self.rev = getattr(self, "rev", 0) + 1