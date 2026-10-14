"""Mini games. «اسم، جماد، نبات، حيوان، بلاد» (the letters game, "letters") and «رتب» (unscramble, "scramble", 1.9.0).
Only one round of any game runs at a time. Wins are kept per viewer: a total and how many came from each game.

The letters game:

A round: the bot picks a category and a letter; the first viewer to write a correct word wins. A word counts when it starts
with the letter (ال, أ/إ/آ, ى/ي, ة/ه and tashkeel don't matter) and is in the category's list (built-in + the streamer's
own + words mods approved). A word that starts with the letter but isn't known can be approved by a mod with !صح; it is
then added to the list. Wins are saved."""
import random
import re
import time

from .moderation import _TASHKEEL

GAME_KEYS = ("letters", "scramble")
GAME_NAMES = {"letters": "حروف", "scramble": "رتب"}      # short Arabic names: chat (!الأوائل حروف) and the leaderboard tabs
CATEGORIES = ("اسم", "جماد", "نبات", "حيوان", "بلاد")
DEFAULT_LETTERS = "ابتجحخدرزسشصطعفقكلمنهوي"        # the hard ones (ث ذ ض ظ غ ء) are off by default; the streamer can add them
WHO = ("everyone", "subscriber", "vip", "moderator", "broadcaster")


MAX_ALIASES = 5             # names per game command (Arabic and English, for example)
MAX_ROUNDS = 500            # "rounds per stream" can go up to this (0 = no limit)
MAX_COOLDOWN = 3600         # seconds between rounds, at most an hour
GAME_CMDS = {"letters": ("start_cmd", "approve_cmd"), "scramble": ("start_cmd",), "shared": ("wins_cmd", "top_cmd")}


def defaults() -> dict:
    # "shared" = the settings for all games (1.9.0): the wins / top 5 commands, and the round limit and cooldown.
    # Every command is a list of names (aliases): any of them works in chat.
    return {"shared": {"wins_cmd": ["!فوز", "!wins"], "top_cmd": ["!الأوائل", "!top"], "rounds_per_stream": 0, "cooldown_seconds": 0},
            "letters": {"enabled": False, "start_cmd": ["!حروف"], "approve_cmd": ["!صح"],
                        "who_starts": "moderator", "round_seconds": 60, "auto_minutes": 0, "categories": list(CATEGORIES), "announce": True,
                        "letters": DEFAULT_LETTERS, "words": {c: [] for c in CATEGORIES}},
            "scramble": {"enabled": False, "start_cmd": ["!رتب"], "who_starts": "moderator", "round_seconds": 45, "hint": True,
                         "auto_minutes": 0, "announce": True, "words": []}}


def cmd_key(word: str) -> str:
    """How a command word is compared: English lowercase, Arabic as written."""
    word = str(word or "").strip()
    return word.lower() if word.isascii() else word


def aliases(value) -> list:
    """A game command's names as a list. Settings from before 1.9.0 hold one name (a string); both work."""
    items = [value] if isinstance(value, str) else value if isinstance(value, (list, tuple)) else []
    out = []
    for v in items:
        k = cmd_key(v)
        if k and k not in out:
            out.append(k)
    return out


def command_names(games: dict) -> dict:
    """Every game command name -> what it is ("letters:start_cmd", "shared:wins_cmd", ...), for clash checks."""
    out = {}
    for part, fields in GAME_CMDS.items():
        for f in fields:
            for a in aliases(((games or {}).get(part) or {}).get(f)):
                out.setdefault(a, f"{part}:{f}")
    return out


def upgrade_games(games: dict, custom_names=()) -> bool:
    """1.9.0: the wins / top 5 commands move from the letters game to "All games", and every command becomes a list of
    names. The English names (!wins, !top) are added only where the old default was kept, and never when one of your own
    commands already uses that name. True when anything changed."""
    if not isinstance(games, dict):
        return False
    changed = False
    letters = games.get("letters") if isinstance(games.get("letters"), dict) else None
    if not isinstance(games.get("shared"), dict):
        shared = dict(defaults()["shared"])
        if letters is not None:
            for f, old_default in (("wins_cmd", "!فوز"), ("top_cmd", "!الأوائل")):
                if f in letters:
                    mine = aliases(letters[f])
                    if mine and mine != [old_default]:
                        shared[f] = mine                  # a name you chose stays exactly as it was
            shared = {k: ([a for a in v if a not in set(custom_names)] or v[:1]) if k.endswith("_cmd") else v for k, v in shared.items()}
        games["shared"] = shared
        changed = True
    if letters is not None:
        for f in ("wins_cmd", "top_cmd"):
            if f in letters:
                del letters[f]
                changed = True
    for part, fields in GAME_CMDS.items():
        cfg = games.get(part)
        if isinstance(cfg, dict):
            for f in fields:
                if f in cfg and not isinstance(cfg[f], list):
                    cfg[f] = aliases(cfg[f])
                    changed = True
    return changed


_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def norm(text: str) -> str:
    """For comparing answers: no tashkeel/tatweel, one form of each letter, single spaces, no leading ال."""
    t = _TASHKEEL.sub("", str(text)).translate(_AR)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = " ".join(t.split())
    words = [w[2:] if w.startswith("ال") and len(w) > 3 else w for w in t.split(" ")]
    return " ".join(words)


def first_letter(text: str) -> str:
    n = norm(text)
    return n[:1]


_LIST_CACHE: dict = {}


def builtin(cat: str) -> set:
    if cat not in _LIST_CACHE:
        from .gamewords import WORDS
        raw = WORDS.get(cat, "")
        # each line holds words separated by spaces; a few countries/names have two words: they are listed joined below
        _LIST_CACHE[cat] = {norm(w) for w in raw.split()} | {norm(w) for w in _MULTI.get(cat, ())}
    return _LIST_CACHE[cat]


_MULTI = {"بلاد": ("جزر القمر", "الجبل الأسود", "سان مارينو", "جنوب أفريقيا", "ساحل العاج", "بوركينا فاسو", "الرأس الأخضر", "كوريا الجنوبية",
                   "كوريا الشمالية", "المملكة المتحدة", "الولايات المتحدة"),
          "حيوان": ("وحيد القرن",), "نبات": ("دوار الشمس", "ورق عنب", "جوز هند", "ذرة سكرية", "عباد الشمس"), "جماد": ("لاب توب",)}


def known(cat: str, word: str, extra=()) -> bool:
    n = norm(word)
    return bool(n) and (n in builtin(cat) or n in {norm(w) for w in extra})


def examples(cat: str, letter: str, extra=(), k: int = 2) -> list:
    want = norm(letter)[:1]
    pool = sorted({w for w in builtin(cat) | {norm(w) for w in extra} if w[:1] == want})
    random.shuffle(pool)
    return pool[:k]


class Round:
    key = "letters"

    def __init__(self, cat: str, letter: str, seconds: int, clock=time.time):
        self.cat, self.letter, self.clock = cat, letter, clock
        self.started = clock()
        self.seconds = seconds
        self.ends = self.started + seconds
        self.pending: list = []          # (user_id, display, word) of unknown words that start with the letter (for !صح)
        self.done = False

    @property
    def over(self) -> bool:
        return self.done or self.clock() >= self.ends

    def check(self, text: str, extra=()):
        """'win' | 'unknown' | None. An answer is the whole message (a word or two), not a sentence."""
        t = str(text).strip()
        if not t or len(t) > 30 or t.startswith("!") or len(t.split()) > 3:
            return None
        if first_letter(t) != norm(self.letter)[:1]:
            return None
        return "win" if known(self.cat, t, extra) else "unknown"


def new_round(cfg: dict, clock=time.time, rng=random) -> Round:
    cats = [c for c in cfg.get("categories") or CATEGORIES if c in CATEGORIES] or list(CATEGORIES)
    letters = [ch for ch in dict.fromkeys(cfg.get("letters") or DEFAULT_LETTERS) if ch.strip()] or list(DEFAULT_LETTERS)
    for _ in range(20):                              # pick a letter the category has words for (so a round is winnable)
        cat, letter = rng.choice(cats), rng.choice(letters)
        if examples(cat, letter, (cfg.get("words") or {}).get(cat, []), 1):
            break
    return Round(cat, letter, int(cfg.get("round_seconds") or 60), clock)


# ---------- «رتب»: unscramble a word ----------

SCRAMBLE_MIN, SCRAMBLE_MAX = 3, 7
_ARABIC_WORD = re.compile(r"^[\u0621-\u064a]+$")


def scramble_ok(word: str) -> bool:
    """A word the game can use: one word of Arabic letters, 3 to 7 letters (tashkeel is dropped first)."""
    w = _TASHKEEL.sub("", str(word)).strip()
    return bool(_ARABIC_WORD.match(w)) and SCRAMBLE_MIN <= len(w) <= SCRAMBLE_MAX


_POOL: list = []


def scramble_pool(extra=()) -> list:
    """The built-in words that make good puzzles (one word, 3-7 letters, not starting with ال) + the streamer's own."""
    if not _POOL:
        from .gamewords import WORDS
        seen = set()
        for cat in CATEGORIES:
            for w in WORDS.get(cat, "").split():
                if scramble_ok(w) and not w.startswith("ال") and norm(w) not in seen:
                    seen.add(norm(w))
                    _POOL.append(w)
    own = [_TASHKEEL.sub("", str(w)).strip() for w in extra]
    return list(dict.fromkeys(_POOL + [w for w in own if scramble_ok(w)]))


def shuffle_letters(word: str, rng=random) -> list:
    """The word's letters in a new order, never the right one (and never the same word read another way)."""
    letters = list(word)
    for _ in range(60):
        rng.shuffle(letters)
        if norm("".join(letters)) != norm(word):
            return letters
    return letters[::-1] if norm(word[::-1]) != norm(word) else letters


def tiles_text(tiles) -> str:
    return " ، ".join(tiles)


class ScrambleRound:
    key = "scramble"

    def __init__(self, word: str, seconds: int, clock=time.time, rng=random):
        self.word, self.clock = word, clock
        self.tiles = shuffle_letters(word, rng)
        self.started = clock()
        self.seconds = seconds
        self.ends = self.started + seconds
        self.hint_at = self.started + seconds / 2
        self.hinted = False
        self.done = False

    @property
    def over(self) -> bool:
        return self.done or self.clock() >= self.ends

    def check(self, text: str):
        """'win' or None: the whole message is the word (ة/ه, أ/إ/ا, tashkeel and a leading ال don't matter)."""
        t = str(text).strip()
        if not t or len(t) > 20 or t.startswith("!") or len(t.split()) > 1:
            return None
        return "win" if norm(t) == norm(self.word) else None


def new_scramble(cfg: dict, avoid=(), clock=time.time, rng=random) -> ScrambleRound:
    pool = scramble_pool(cfg.get("words") or [])
    fresh = [w for w in pool if norm(w) not in {norm(a) for a in avoid}] or pool
    return ScrambleRound(rng.choice(fresh), int(cfg.get("round_seconds") or 45), clock, rng)


# ---------- wins: a total per viewer plus how many came from each game ----------

def add_win(wins: dict, uid: str, name: str, game: str = "letters") -> int:
    e = wins.setdefault(str(uid), {"name": name, "wins": 0, "games": {}})
    e["name"], e["wins"] = name, int(e.get("wins", 0)) + 1
    g = e.setdefault("games", {})
    g[game] = int(g.get(game, 0)) + 1
    return e["wins"]


def upgrade_wins(wins: dict) -> bool:
    """1.9.0: wins saved before there was more than one game were all letters-game wins. Returns True if anything changed."""
    changed = False
    for e in wins.values():
        if isinstance(e, dict) and not isinstance(e.get("games"), dict):
            n = int(e.get("wins", 0) or 0)
            e["games"] = {"letters": n} if n else {}
            changed = True
    return changed


def wins_of(e: dict, game: str | None = None) -> int:
    if not isinstance(e, dict):
        return 0
    if game is None:
        return int(e.get("wins", 0) or 0)
    return int((e.get("games") or {}).get(game, 0) or 0)


def top(wins: dict, n: int = 5, game: str | None = None) -> list:
    """[(name, wins)] best first: all games together, or one game. Nobody with 0 wins."""
    rows = [(e.get("name", "?"), wins_of(e, game)) for e in wins.values() if isinstance(e, dict)]
    return sorted((r for r in rows if r[1] > 0), key=lambda x: (-x[1], str(x[0]).lower()))[:n]


def game_named(text: str):
    """'letters' / 'scramble' for «حروف» / «رتب» (also with ! or ال), else None."""
    want = norm(str(text).strip().lstrip("!"))
    return next((k for k, v in GAME_NAMES.items() if norm(v) == want), None) if want else None


def breakdown(e: dict) -> str:
    """«حروف 5، رتب 4»: the games this viewer has won, in the games' order."""
    return "، ".join(f"{GAME_NAMES[k]} {wins_of(e, k)}" for k in GAME_KEYS if wins_of(e, k))


def reset_game(wins: dict, game: str) -> dict:
    """The leaderboard without one game's wins (totals go down; people left with nothing are removed)."""
    out = {}
    for uid, e in wins.items():
        if not isinstance(e, dict):
            continue
        g = dict(e.get("games") or {})
        n = int(g.pop(game, 0) or 0)
        total = max(0, int(e.get("wins", 0) or 0) - n)
        if total > 0:
            out[uid] = dict(e, wins=total, games=g)
    return out
