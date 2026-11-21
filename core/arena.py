"""1.19.0: the Arena (Overlays > Arena). First thing in it: Chat soldiers. 1.20.0: or Chat bears (setting "kind").

Viewers type !spawn and fall onto the stream as a tiny soldier, !attack stabs whoever their soldier is standing on,
!protect puts on heavy armor that blocks one attack. The bot never answers in chat for any of it.

Who does what: this file checks the command (is the Arena on, may this viewer play, is their 3-second wait over) and
keeps a short list of what happened (and sends a soldier off when their viewer has gone quiet). The overlay (core/overlays.py) reads that list about once a second and plays it:
it alone knows where every soldier is standing, so it decides hit or miss, who grows and who wears the crown.
Nothing here is saved between runs except the settings.

1.20.0: three more for every character: !dance (a little dance, music notes), !eat (one bite of pizza, one random power-up,
with its own long wait) and !walkaway (your character walks off the stream). The power-up is picked here, so the wait
for !attack knows about Rage."""

import random

import re
import threading
import time

DEFAULTS = {
    "on": False,
    "kind": "soldiers",         # 1.20.0: who drops onto the stream: soldiers | bears | bags (same commands, same rules; bags never bleed)
    "cmd_spawn": "!spawn", "cmd_attack": "!attack", "cmd_protect": "!protect",
    "cmd_dance": "!dance", "cmd_eat": "!eat", "cmd_walkaway": "!walkaway",     # 1.20.0
    "cmd_help": "!arena",       # 1.20.0: the bot answers in chat with every Arena command
    "eat_wait": 120,            # 1.20.0: seconds before the same viewer can !eat again (power-ups are strong)
    "cooldown": 3,              # seconds between two !attack (and between two !protect) of the same viewer
    "who": "everyone",          # everyone | sub | vip | mod
    "max": 20,                  # soldiers on screen at once
    "grow": "little",           # off | little | lot: how big the top soldier can get
    "crown": True,              # the soldier with the most knockouts wears a crown
    "idle": 20,                 # minutes without a chat message before that viewer's soldier walks off (0 = he stays)
    "size": 100,                # percent
    "speed": 100,               # 1.20.0: how fast they walk, percent (50 slow ... 200 fast)
    "names": True,
    "blood": True,
    "ground": 100,              # 1.19.1: where the soldiers stand, % from the top of the overlay (100 = the bottom edge)
    "left": 0,                  # 1.19.1: the stretch they walk, % of the width (left edge ... right edge)
    "right": 100,
}
CHOICES = {"who": ("everyone", "sub", "vip", "mod"), "grow": ("off", "little", "lot"), "kind": ("soldiers", "bears", "bags")}
RANGES = {"eat_wait": (30, 900), "speed": (50, 200), "cooldown": (0, 10), "max": (5, 40), "size": (50, 200), "idle": (0, 180), "ground": (10, 100), "left": (0, 80), "right": (20, 100)}
BOOLS = ("on", "crown", "names", "blood")
CMDS = ("cmd_spawn", "cmd_attack", "cmd_protect", "cmd_dance", "cmd_eat", "cmd_walkaway", "cmd_help")
HELP_WAIT = 30                  # seconds between two command lists in chat (for the whole channel)
# 1.20.0: what one bite of pizza gives (weights). ULTRA KILL is its own 1 in ULTRA_ODDS roll on top: it knocks out everyone else.
BUFFS = (("speed", 30), ("jump", 25), ("rage", 25), ("armor", 20))   # jump: a hit has JUMP_ODDS to be jumped over
ULTRA_ODDS = 1000
RAGE_SECS = 12                  # Rage: no wait between attacks for this long
CMD_MAX = 25
NEED = {"everyone": 0, "sub": 1, "vip": 2, "mod": 3}      # the bot's levels: 1 subscriber, 2 VIP, 3 moderator, 4 streamer
KEEP = 300                      # events remembered (the overlay only wants the ones newer than the last it played)
TEST_NAMES = ("سلطان", "Shuaiil", "نواف_77", "xDarkWolf", "ريم", "Mido", "خالد", "Noor", "جود", "Zezo")
TEST_COLORS = ("#ff6b85", "#ffb02e", "#ffe14d", "#7be37b", "#2fd6c3", "#4db8ff", "#8f9cff", "#c08cff", "#ff7ce0", "#ff8a4d")


class ArenaError(ValueError):
    pass


CMD_EACH = 5                    # 1.20.0: an action can have several commands (up to this many), kept as one string "!spawn !join"


def _cmd(v, default: str) -> str:
    """The commands for one action as typed in chat, separated by spaces or commas (1.20.0; before: one word).
    Each kept as written (lower-cased when compared), cut to CMD_MAX, no repeats, at most CMD_EACH."""
    out, seen = [], set()
    for w in re.split(r"[\s,،]+", str(v if v is not None else "")):
        w = w.strip()[:CMD_MAX]
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return " ".join(out[:CMD_EACH]) or default


def words(v) -> list:
    """1.20.0: the commands of one action, lower-cased."""
    return [w for w in str(v or "").lower().split() if w]


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
    low = [w for k in CMDS for w in words(out[k])]
    if len(set(low)) < len(low):
        raise ArenaError("A command can only do one thing: the same command is set for two Arena actions.")
    return out


def cfg_of(store) -> dict:
    try:
        return validate(store.get("arena") or {})
    except ArenaError:
        return dict(DEFAULTS)


class Arena:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = []            # {"id", "t": spawn|attack|protect|dance|eat|leave|clear, "u": login, "n": shown name, "c": color, "b": power-up (eat)}
        self.next_id = 1
        self.wait = {}              # (login, kind) -> when that viewer may do it again
        self.seen_at = {}           # login -> the last time that viewer wrote anything in chat
        self.inplay = {}            # login -> the shown name, while that viewer has a soldier on the field
        self.boot = int(time.time() * 1000)     # a new run of the app: the overlay starts its list again
        self.rage = {}              # 1.20.0: login -> until when !attack has no wait (the Rage power-up)
        self.help_at = 0.0          # 1.20.0: when the command list was last said in chat
        self.rand = random.random

    def _add(self, kind: str, login: str = "", name: str = "", color: str = "", buff: str = "") -> None:
        ev = {"id": self.next_id, "t": kind, "u": login, "n": name, "c": color}
        if buff:
            ev["b"] = buff
        self.events.append(ev)
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
        kind = next((k[4:] for k in CMDS if word and word in words(cfg[k])), None)
        if not kind:
            return False
        login = (login or "").lower()
        if kind == "help":                    # 1.20.0: anyone may ask; once every HELP_WAIT seconds for the channel
            now = time.time() if now is None else now
            with self.lock:
                if now < self.help_at + HELP_WAIT:
                    return True
                self.help_at = now
            return "help"
        if not login or level < NEED.get(cfg.get("who"), 0):
            return True                       # theirs to type, not theirs to play: silently nothing
        now = time.time() if now is None else now
        with self.lock:
            if kind == "walkaway":            # 1.20.0: no wait; only someone on the field can walk off
                self.seen_at[login] = now
                if login in self.inplay:
                    self.inplay.pop(login, None)
                    self._add("leave", login)
                return True
            if kind == "eat" and login not in self.inplay:
                return True                   # nothing to feed: the long wait doesn't start
            if kind != "spawn":
                raging = kind == "attack" and now < self.rage.get(login, 0)
                if now < self.wait.get((login, kind), 0) and not raging:
                    return True               # still waiting: nothing happens (and the wait doesn't start again)
                self.wait[(login, kind)] = now + int(cfg.get("eat_wait" if kind == "eat" else "cooldown") or 0)
                if len(self.wait) > 4000:
                    self.wait = {k: v for k, v in self.wait.items() if v > now}
            self.seen_at[login] = now
            if kind == "spawn":
                self.inplay[login] = name or login
                self._trim(now)
            buff = self._buff(login, now) if kind == "eat" else ""
            self._add(kind, login, name or login, color or "", buff)
        return True

    @staticmethod
    def help_text(cfg: dict, lang: str = "en") -> str:
        """1.20.0: the line the bot says for !arena: every Arena command (the first word of each), for this kind of character."""
        first = lambda k: (words(cfg.get(k)) or [DEFAULTS[k]])[0]
        kind = cfg.get("kind") if cfg.get("kind") in ("bears", "bags") else "soldiers"
        if lang == "ar":
            head = {"soldiers": "⚔️ جنود الشات", "bears": "🐻 دببة الشات", "bags": "🛍️ أكياس الشات"}[kind]
            arm = {"soldiers": "للدرع", "bears": "لسترة الخشب", "bags": "لتغليف الفقاعات"}[kind]
            parts = [(first("cmd_spawn"), "للدخول"), (first("cmd_attack"), "للهجوم"), (first("cmd_protect"), arm),
                     (first("cmd_dance"), "للرقص"), (first("cmd_eat"), "لقوة عشوائية"), (first("cmd_walkaway"), "للمغادرة")]
        else:
            head = {"soldiers": "⚔️ Chat soldiers", "bears": "🐻 Chat bears", "bags": "🛍️ Chat bags"}[kind]
            arm = {"soldiers": "for armor", "bears": "for a wooden vest", "bags": "for bubble wrap"}[kind]
            hit = {"soldiers": "to fight", "bears": "to scratch", "bags": "to swing your bat"}[kind]
            parts = [(first("cmd_spawn"), "to join"), (first("cmd_attack"), hit), (first("cmd_protect"), arm),
                     (first("cmd_dance"), "to dance"), (first("cmd_eat"), "for a random power-up"), (first("cmd_walkaway"), "to leave")]
        return head + ": " + " · ".join(f"{c} {w}" for c, w in parts)

    def _buff(self, login: str, now: float) -> str:
        """1.20.0: the power-up of one bite of pizza."""
        if self.rand() < 1 / ULTRA_ODDS:
            return "ultra"
        r = self.rand() * sum(w for _, w in BUFFS)
        k = BUFFS[-1][0]
        for name, w in BUFFS:
            r -= w
            if r < 0:
                k = name
                break
        if k == "rage":
            self.rage[login] = now + RAGE_SECS
            if len(self.rage) > 2000:
                self.rage = {u: v for u, v in self.rage.items() if v > now}
        return k

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
