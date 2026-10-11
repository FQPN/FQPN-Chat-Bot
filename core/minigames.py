"""Mini games. The first: «اسم، جماد، نبات، حيوان، بلاد» (the letters game).

A round: the bot picks a category and a letter; the first viewer to write a correct word wins. A word counts when it starts
with the letter (ال, أ/إ/آ, ى/ي, ة/ه and tashkeel don't matter) and is in the category's list (built-in + the streamer's
own + words mods approved). A word that starts with the letter but isn't known can be approved by a mod with !صح; it is
then added to the list. Wins are saved."""
import random
import re
import time

from .moderation import _TASHKEEL

GAME_KEYS = ("letters",)
CATEGORIES = ("اسم", "جماد", "نبات", "حيوان", "بلاد")
DEFAULT_LETTERS = "ابتجحخدرزسشصطعفقكلمنهوي"        # the hard ones (ث ذ ض ظ غ ء) are off by default; the streamer can add them
WHO = ("everyone", "subscriber", "vip", "moderator", "broadcaster")


def defaults() -> dict:
    return {"letters": {"enabled": False, "start_cmd": "!حروف", "approve_cmd": "!صح", "wins_cmd": "!فوز", "top_cmd": "!الأوائل",
                        "who_starts": "moderator", "round_seconds": 60, "auto_minutes": 0, "categories": list(CATEGORIES), "announce": True,
                        "letters": DEFAULT_LETTERS, "words": {c: [] for c in CATEGORIES}}}


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
    def __init__(self, cat: str, letter: str, seconds: int, clock=time.time):
        self.cat, self.letter, self.clock = cat, letter, clock
        self.ends = clock() + seconds
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


def add_win(wins: dict, uid: str, name: str) -> int:
    e = wins.setdefault(str(uid), {"name": name, "wins": 0})
    e["name"], e["wins"] = name, int(e.get("wins", 0)) + 1
    return e["wins"]


def top(wins: dict, n: int = 5) -> list:
    return sorted(((e.get("name", "?"), int(e.get("wins", 0))) for e in wins.values()), key=lambda x: (-x[1], x[0].lower()))[:n]
