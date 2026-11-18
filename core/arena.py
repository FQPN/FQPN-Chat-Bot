"""1.19.0: the Arena (Overlays > Arena). First thing in it: Chat soldiers.

Viewers type !spawn and fall onto the stream as a tiny soldier, !attack stabs whoever their soldier is standing on,
!protect puts on heavy armor that blocks one attack. The bot never answers in chat for any of it.

Who does what: this file checks the command (is the Arena on, may this viewer play, is their 3-second wait over) and
keeps a short list of what happened (and sends a soldier off when their viewer has gone quiet). The overlay (core/overlays.py) reads that list about once a second and plays it:
it alone knows where every soldier is standing, so it decides hit or miss, who grows and who wears the crown.
Nothing here is saved between runs except the settings."""

import re
import threading
import time

DEFAULTS = {
    "on": False,
    "cmd_spawn": "!spawn", "cmd_attack": "!attack", "cmd_protect": "!protect",
    "cooldown": 3,              # seconds between two !attack (and between two !protect) of the same viewer
    "who": "everyone",          # everyone | sub | vip | mod
    "max": 20,                  # soldiers on screen at once
    "grow": "little",           # off | little | lot: how big the top soldier can get
    "crown": True,              # the soldier with the most knockouts wears a crown
    "idle": 20,                 # minutes without a chat message before that viewer's soldier walks off (0 = he stays)
    "size": 100,                # percent
    "names": True,
    "blood": True,
    "ground": 100,              # 1.19.1: where the soldiers stand, % from the top of the overlay (100 = the bottom edge)
    "left": 0,                  # 1.19.1: the stretch they walk, % of the width (left edge ... right edge)
    "right": 100,
}
CHOICES = {"who": ("everyone", "sub", "vip", "mod"), "grow": ("off", "little", "lot")}
RANGES = {"cooldown": (0, 10), "max": (5, 40), "size": (50, 200), "idle": (0, 180), "ground": (10, 100), "left": (0, 80), "right": (20, 100)}
BOOLS = ("on", "crown", "names", "blood")
CMDS = ("cmd_spawn", "cmd_attack", "cmd_protect")
CMD_MAX = 25
NEED = {"everyone": 0, "sub": 1, "vip": 2, "mod": 3}      # the bot's levels: 1 subscriber, 2 VIP, 3 moderator, 4 streamer
KEEP = 300                      # events remembered (the overlay only wants the ones newer than the last it played)
TEST_NAMES = ("سلطان", "Shuaiil", "نواف_77", "xDarkWolf", "ريم", "Mido", "خالد", "Noor", "جود", "Zezo")
TEST_COLORS = ("#ff6b85", "#ffb02e", "#ffe14d", "#7be37b", "#2fd6c3", "#4db8ff", "#8f9cff", "#c08cff", "#ff7ce0", "#ff8a4d")


class ArenaError(ValueError):
    pass


def _cmd(v, default: str) -> str:
    """A command as typed in chat: one word, no spaces, kept as written (lower-cased when compared)."""
    v = re.sub(r"\s+", "", str(v if v is not None else "")).strip()[:CMD_MAX]
    return v or default


def validate(data) -> dict:
    """Every setting checked. Anything missing or unknown falls back to the default (never an error for old data)."""
    data = data if isinstance(data, dict) else {}
    out = dict(DEFAULTS)
    for k in BOOLS:
        if k in data:
            out[k] = bool(data[k])
    for k, opts in CHOICES.items():
        if data.get(k) in opts:
            out[k] = data[k]
    for k, (lo, hi) in RANGES.items():
        try:
            if k in data and not isinstance(data[k], bool):
                out[k] = max(lo, min(hi, int(float(data[k]))))
        except (TypeError, ValueError):
            pass
    if out["right"] < out["left"] + 20:      # at least a fifth of the width to walk in
        out["right"] = min(100, out["left"] + 20)
        out["left"] = out["right"] - 20
    for k in CMDS:
        out[k] = _cmd(data.get(k), DEFAULTS[k])
    low = [out[k].lower() for k in CMDS]
    if len(set(low)) < 3:
        raise ArenaError("The three Arena commands must be different from each other.")
    return out


def cfg_of(store) -> dict:
    try:
        return validate(store.get("arena") or {})
    except ArenaError:
        return dict(DEFAULTS)


class Arena:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = []            # {"id", "t": spawn|attack|protect|clear, "u": login, "n": shown name, "c": color}
        self.next_id = 1
        self.wait = {}              # (login, kind) -> when that viewer may do it again
        self.seen_at = {}           # login -> the last time that viewer wrote anything in chat
        self.inplay = {}            # login -> the shown name, while that viewer has a soldier on the field
        self.boot = int(time.time() * 1000)     # a new run of the app: the overlay starts its list again

    def _add(self, kind: str, login: str = "", name: str = "", color: str = "") -> None:
        self.events.append({"id": self.next_id, "t": kind, "u": login, "n": name, "c": color})
        self.next_id += 1
        if len(self.events) > KEEP:
            del self.events[:len(self.events) - KEEP]

    def seen(self, login: str, now=None) -> None:
        """Any chat message from this viewer. Writing anything keeps their soldier on the field."""
        login = (login or "").lower()
        if not login:
            return
        now = time.time() if now is None else now
        with self.lock:
            self.seen_at[login] = now
            self._trim(now)

    def _trim(self, now: float) -> None:
        """A busy channel never fills memory: only the most recent chatters are remembered, plus everyone on the field."""
        if len(self.seen_at) > 4000:
            self.seen_at = dict(sorted(self.seen_at.items(), key=lambda kv: kv[1], reverse=True)[:2000])
            for u in self.inplay:
                self.seen_at.setdefault(u, now)
        if len(self.inplay) > 500:
            keep = sorted(self.inplay, key=lambda u: self.seen_at.get(u, 0), reverse=True)[:250]
            self.inplay = {u: self.inplay[u] for u in keep}

    def sweep(self, cfg: dict, now=None) -> None:
        """Soldiers whose viewer has gone quiet walk off the field. Called while the overlay asks for news."""
        mins = int(cfg.get("idle") or 0)
        if mins <= 0 or not self.inplay:
            return
        now = time.time() if now is None else now
        with self.lock:
            for login in [u for u, _ in self.inplay.items() if now - self.seen_at.get(u, 0) > mins * 60]:
                self._add("leave", login)
                self.inplay.pop(login, None)

    def command(self, cfg: dict, text: str, login: str, name: str, color: str, level: int, now=None) -> bool:
        """A chat message. True when it was one of the Arena's commands (so nothing else answers it)."""
        if not cfg.get("on"):
            return False
        word = (text or "").strip().split(" ", 1)[0].lower()
        kind = next((k[4:] for k in CMDS if word and word == str(cfg[k]).lower()), None)
        if not kind:
            return False
        login = (login or "").lower()
        if not login or level < NEED.get(cfg.get("who"), 0):
            return True                       # theirs to type, not theirs to play: silently nothing
        now = time.time() if now is None else now
        with self.lock:
            if kind != "spawn":
                if now < self.wait.get((login, kind), 0):
                    return True               # still waiting: nothing happens (and the wait doesn't start again)
                self.wait[(login, kind)] = now + int(cfg.get("cooldown") or 0)
                if len(self.wait) > 4000:
                    self.wait = {k: v for k, v in self.wait.items() if v > now}
            self.seen_at[login] = now
            if kind == "spawn":
                self.inplay[login] = name or login
                self._trim(now)
            self._add(kind, login, name or login, color or "")
        return True

    def test(self, n: int = 5) -> None:
        """«Drop 5 test soldiers»: made-up viewers (never anything in your Twitch chat)."""
        with self.lock:
            start = self.next_id
            for i in range(n):
                j = (start + i) % len(TEST_NAMES)
                self._add("spawn", "test:" + TEST_NAMES[j].lower(), TEST_NAMES[j], TEST_COLORS[j])
                self.seen_at["test:" + TEST_NAMES[j].lower()] = time.time()

    def clear(self) -> None:
        with self.lock:
            self.inplay.clear()
            self._add("clear")

    def view(self, after: int) -> dict:
        with self.lock:
            return {"boot": self.boot, "last": self.next_id - 1, "events": [e for e in self.events if e["id"] > after][-60:]}


ARENA = Arena()
