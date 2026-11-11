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

GAME_KEYS = ("letters", "scramble", "emoji", "reverse", "math", "ladder", "trivia", "riddle", "translate", "opposite", "oddone")      # 1.14.0: + «ايموجي», «عكس», «احسب»; 1.15.0: + «لغز», «ترجم», «ضد»
GAME_NAMES = {"letters": "حروف", "scramble": "رتب", "emoji": "ايموجي", "reverse": "عكس", "math": "احسب", "ladder": "سلم", "trivia": "سؤال", "riddle": "لغز", "translate": "ترجم", "opposite": "ضد", "oddone": "الدخيل"}      # chat (!الأوائل حروف) and the leaderboard tabs
QUICK_GAMES = ("emoji", "reverse", "math", "ladder", "trivia", "riddle", "translate", "opposite", "oddone")      # 1.14.0: the bot posts a challenge; the first right answer wins
MATH_LEVELS = ("easy", "normal", "hard")
TRIVIA_LEVELS = ("easy", "hard")
TRIVIA_TIERS = ("easy", "medium", "hard", "mixed")     # 1.15.0 (owner): how hard the questions themselves are
ODDONE_LEVELS = ("easy", "hard")     # 1.15.0 «الدخيل»: clearly different groups / close ones
TRANSLATE_LEVELS = ("easy", "hard")     # 1.15.0 «ترجم»: everyday words / less common ones
TRANSLATE_WAYS = ("en_ar", "ar_en", "mixed")
OPPOSITE_LEVELS = ("easy", "hard")     # 1.15.0 «ضد»: everyday words / harder ones   # English word -> write it in Arabic, the other way, or either        # 1.14.0 «سؤال»: easy = the 4 choices are shown; hard (default) = only the question
CATEGORIES = ("اسم", "جماد", "نبات", "حيوان", "بلاد")
DEFAULT_LETTERS = "ابتجحخدرزسشصطعفقكلمنهوي"        # the hard ones (ث ذ ض ظ غ ء) are off by default; the streamer can add them
WHO = ("everyone", "subscriber", "vip", "moderator", "broadcaster")


MAX_ALIASES = 5             # names per game command (Arabic and English, for example)
MAX_ROUNDS = 500            # "rounds per stream" can go up to this (0 = no limit)
MAX_COOLDOWN = 3600         # seconds between rounds, at most an hour
GAME_CMDS = {"letters": ("start_cmd", "approve_cmd"), "scramble": ("start_cmd",), "emoji": ("start_cmd",), "reverse": ("start_cmd",),
             "math": ("start_cmd",), "ladder": ("start_cmd",), "trivia": ("start_cmd",), "riddle": ("start_cmd",),
             "translate": ("start_cmd",), "opposite": ("start_cmd",), "oddone": ("start_cmd",), "shared": ("wins_cmd", "top_cmd", "random_cmd", "list_cmd")}


def defaults() -> dict:
    # "shared" = the settings for all games (1.9.0): the wins / top 5 commands, and the round limit and cooldown.
    # Every command is a list of names (aliases): any of them works in chat.
    # 1.14.0: random_cmd «لعبه؟» starts a round of a random game (among the ones switched on)
    return {"shared": {"wins_cmd": ["!فوز", "!wins"], "top_cmd": ["!الأوائل", "!top"], "random_cmd": ["لعبه؟", "لعبة؟"],
                       "list_cmd": ["العاب؟", "ألعاب؟", "!العاب", "games?"],      # 1.15.0 (owner): lists the games that are on
                       "rounds_per_stream": 0, "cooldown_seconds": 0, "enabled": True},      # 1.14.0: enabled = the main switch
            "letters": {"enabled": False, "start_cmd": ["حروف؟", "!حروف"], "approve_cmd": ["!صح"],
                        "who_starts": "everyone", "round_seconds": 60, "auto_minutes": 0, "categories": list(CATEGORIES), "announce": True,
                        "letters": DEFAULT_LETTERS, "words": {c: [] for c in CATEGORIES}},
            "scramble": {"enabled": False, "start_cmd": ["رتب؟", "!رتب"], "who_starts": "everyone", "round_seconds": 45, "hint": True,
                         "auto_minutes": 0, "announce": True, "words": [],
                         # 1.10.0: categories make it easier. The built-in words keep the category they come from (the five
                         # of the first game); your own words can have one (word -> category). Turned-off categories aren't played.
                         "show_category": True, "word_cats": {}, "categories_off": [],
                         "max_letters": 5},          # 1.14.0: easier: everyday words, 3 to 5 letters (up to 7 in the settings)
            "emoji": {"enabled": False, "start_cmd": ["ايموجي؟", "!ايموجي"], "who_starts": "everyone", "round_seconds": 30, "hint": True,
                      "auto_minutes": 0, "announce": True, "puzzles": []},        # your own: [{"e": "🐪🏜️", "a": ["صحراء"]}]
            "reverse": {"enabled": False, "start_cmd": ["عكس؟", "!عكس"], "who_starts": "everyone", "round_seconds": 30, "hint": True,
                        "auto_minutes": 0, "announce": True},
            "math": {"enabled": False, "start_cmd": ["احسب؟", "!احسب"], "who_starts": "everyone", "round_seconds": 20,
                     "auto_minutes": 0, "announce": True, "level": "normal"},
            "ladder": {"enabled": False, "start_cmd": ["سلم؟", "!سلم"], "who_starts": "everyone", "round_seconds": 30,     # 1.14.0
                       "auto_minutes": 0, "announce": True, "words": 3},
            "trivia": {"enabled": False, "start_cmd": ["سؤال؟", "!سؤال"], "who_starts": "everyone", "round_seconds": 30,
                       "auto_minutes": 0, "announce": True, "level": "hard", "hint": True, "questions": "easy"},
            "riddle": {"enabled": False, "start_cmd": ["لغز؟", "!لغز"], "who_starts": "everyone", "round_seconds": 45,     # 1.15.0
                       "auto_minutes": 0, "announce": True, "hint": True},
            "translate": {"enabled": False, "start_cmd": ["ترجم؟", "!ترجم"], "who_starts": "everyone", "round_seconds": 30,   # 1.15.0
                          "auto_minutes": 0, "announce": True, "hint": True, "level": "easy", "way": "mixed"},      # (owner: random by default)
            "opposite": {"enabled": False, "start_cmd": ["ضد؟", "!ضد"], "who_starts": "everyone", "round_seconds": 30,   # 1.15.0
                         "auto_minutes": 0, "announce": True, "hint": True, "level": "easy"},
            "oddone": {"enabled": False, "start_cmd": ["الدخيل؟", "!الدخيل"], "who_starts": "everyone", "round_seconds": 30,   # 1.15.0
                       "auto_minutes": 0, "announce": True, "level": "easy"}}


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
    shared = games.get("shared")
    if isinstance(shared, dict) and "list_cmd" not in shared:
        # 1.15.0 (owner), once (list_cmd missing = first start on 1.15.0): every game also starts with «name؟» where its
        # command is still the old default «!name», and «العاب؟» lists the games. A name already in use (one of your
        # commands, or another game's) is never taken.
        new = defaults()
        taken = set(custom_names) | {a for p, fs in GAME_CMDS.items() if isinstance(games.get(p), dict)
                                     for f in fs for a in aliases(games[p].get(f))}
        for g in GAME_KEYS:
            cfg = games.get(g)
            q, bang = new[g]["start_cmd"]
            if isinstance(cfg, dict) and aliases(cfg.get("start_cmd")) == [bang] and q not in taken:
                cfg["start_cmd"] = [q, bang]
                taken.add(q)
        shared["list_cmd"] = [a for a in new["shared"]["list_cmd"] if cmd_key(a) not in taken]
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
_POOL_CATS: list = []        # the same built-in words with the category each comes from


def scramble_pool(extra=()) -> list:
    """The built-in words (1.14.0: the everyday list, core/gamewords_easy.py) + the streamer's own."""
    if not _POOL:
        from .gamewords_easy import EASY
        seen = set()
        for cat, text in EASY.items():
            for w in text.split():
                if scramble_ok(w) and not w.startswith("ال") and norm(w) not in seen:
                    seen.add(norm(w))
                    _POOL.append(w)
                    _POOL_CATS.append((w, cat))
    own = [_TASHKEEL.sub("", str(w)).strip() for w in extra]
    return list(dict.fromkeys(_POOL + [w for w in own if scramble_ok(w)]))


MAX_CATEGORY = 20           # characters in a category name of your own


def clean_word(w) -> str:
    return _TASHKEEL.sub("", str(w)).strip()


def scramble_entries(cfg: dict) -> list:
    """[(word, category), ...] the game can use: the built-in words (category = the first game's category they come from) and
    your own words (category = the one you gave them, or "" for none; yours wins when a word is in both). Without the
    categories you turned off. Words without a category are always played."""
    scramble_pool()                                   # (fills the built-in pool once)
    off = set((cfg or {}).get("categories_off") or [])
    cats = (cfg or {}).get("word_cats") or {}
    out, seen = [], {}
    for w in [clean_word(x) for x in (cfg or {}).get("words") or []]:
        if scramble_ok(w) and norm(w) not in seen:
            seen[norm(w)] = len(out)
            out.append((w, str(cats.get(w) or "").strip()))
    longest = max(SCRAMBLE_MIN, min(SCRAMBLE_MAX, int((cfg or {}).get("max_letters") or 5)))      # 1.14.0 (your own words: any length)
    for w, cat in _POOL_CATS:
        if norm(w) not in seen and len(w) <= longest:
            seen[norm(w)] = len(out)
            out.append((w, cat))
    return [(w, c) for w, c in out if not c or c not in off]


def scramble_categories(cfg: dict) -> list:
    """Every category that has words: the built-in ones first, then your own (for the "categories in play" list)."""
    from .gamewords_easy import EASY
    own = [str(c).strip() for c in ((cfg or {}).get("word_cats") or {}).values() if str(c).strip()]
    return list(dict.fromkeys(list(EASY) + own))


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

    def __init__(self, word: str, seconds: int, clock=time.time, rng=random, category: str = ""):
        self.word, self.clock, self.category = word, clock, category
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
    pool = scramble_entries(cfg) or scramble_entries(dict(cfg, categories_off=[]))     # (never empty: then every category)
    recent = {norm(a) for a in avoid}
    fresh = [e for e in pool if norm(e[0]) not in recent] or pool
    word, cat = rng.choice(fresh)
    return ScrambleRound(word, int(cfg.get("round_seconds") or 45), clock, rng, category=cat)


# ---------- 1.14.0: «ايموجي», «عكس», «احسب»: the bot posts a challenge, the first right answer wins ----------

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_TO_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


class QuickRound:
    """A challenge (prompt) with its accepted answers. answer = what is shown when time is up (and in the win message)."""

    def __init__(self, key: str, prompt: str, answers, seconds: int, clock=time.time, hint: str = ""):
        self.key, self.prompt, self.clock, self.hint = key, prompt, clock, hint
        self.answers = [str(a).strip() for a in answers if str(a).strip()]
        self.answer = self.answers[0] if self.answers else ""
        self.started = clock()
        self.seconds = seconds
        self.ends = self.started + seconds
        self.hint_at = self.started + seconds / 2
        self.hinted = False
        self.done = False

    @property
    def over(self) -> bool:
        return self.done or self.clock() >= self.ends

    def check(self, text: str, who=None):
        """'win' or None. The whole message is the answer (a few words at most).
        1.14.0: «سلم»: N different words starting with the letter; «سؤال»: the choice's text (the owner: no numbers), and a
        wrong guess (another choice) locks that viewer out of this round (so nobody can just send all four)."""
        t = str(text).strip()
        if self.key == "ladder":
            return self._ladder(t)
        if self.key in ("trivia", "riddle", "translate", "opposite", "oddone"):     # 1.15.0: «لغز» and «ترجم» are answered like Hard «سؤال»
            return self._trivia(t, who)
        if not t or len(t) > 30 or t.startswith("!") or len(t.split()) > 3:
            return None
        if self.key == "math":
            digits = t.translate(_AR_DIGITS).replace(" ", "").lstrip("=")
            return "win" if re.fullmatch(r"-?\d{1,7}", digits) and int(digits) == int(self.answer) else None
        n = norm(t)
        return "win" if any(n == norm(a) for a in self.answers) else None

    def _ladder(self, t: str):
        if not t or t.startswith("!") or len(t) > 160:
            return None
        want, letter, good = int(getattr(self, "count", 3)), norm(getattr(self, "letter", "")), []
        for w in re.split(r"[\s،,.؛;:!؟?]+", t):
            n = norm(w)
            if n.startswith("ال") and letter != "ا" and len(n) > 3:
                n = n[2:]                            # «التمر» counts for ت
            if len(n) < 2 or len(set(n)) < 2 or not n.startswith(letter) or n in good:
                continue
            good.append(n)
        if len(good) >= want:
            self.win_text = "، ".join(x for x in t.split() if x)[:80]
            return "win"
        return None

    def _trivia(self, t: str, who):
        if not t or t.startswith("!") or len(t) > 40:
            return None
        n = trivia_key(t)                            # the answer's own text: «مسقط», «المحيط الهادئ», «7» (also «٧»)
        if not getattr(self, "show_choices", True):  # hard: only the question; the first right answer wins, no lockout
            return "win" if n and n in {trivia_key(a) for a in self.answers} else None
        if who is not None and who in self.out:
            return None
        pick = next((i for i, c in enumerate(self.choices) if trivia_key(c) == n), None)
        if pick is None and n in {trivia_key(a) for a in self.answers}:
            pick = self.right                        # a short form of the right one («الهادئ»)
        if pick is None:
            return None                              # just chatting: not a guess
        if pick == self.right:
            return "win"
        if who is not None:
            self.out.add(who)
        return None


def trivia_key(text: str) -> str:
    """«سؤال» answers compared: norm() (ال, أ/إ/آ, ة/ه, tashkeel), digits as Western, any capitals, spaces ignored («أبو ظبي» = «ابوظبي»)."""
    t = re.sub(r"^(the|an|a|to)\s+", "", str(text).strip().casefold())     # 1.15.0 «ترجم»: "the cat", "to eat" count too
    return norm(t.translate(_AR_DIGITS)).casefold().replace(" ", "")


def trivia_hint(answer: str) -> str:
    """«سؤال» on hard: how the answer starts (with «ال», 3 letters: «الع»; else 1) and how many letters (and words)."""
    a = _TASHKEEL.sub("", str(answer)).strip()
    if re.fullmatch(r"[\d٠-٩]+", a):
        return ""                                    # a number: any hint would give it away (no hint is sent)
    start = a[:3] if a.startswith("ال") and len(a) > 4 else a[:1]
    n, w = len(a.replace(" ", "")), len(a.split())
    return f"💡 تلميح: يبدأ بـ «{start}» ({n} حروف" + ({2: "، كلمتين"}.get(w, f"، {w} كلمات") if w > 1 else "") + ")"


def emoji_puzzles(cfg: dict) -> list:
    """[(emojis, [answers])]: your own puzzles first, then the built-in ones."""
    from .gamewords_easy import EMOJI
    own = []
    for p in (cfg or {}).get("puzzles") or []:
        if isinstance(p, dict) and str(p.get("e") or "").strip() and p.get("a"):
            own.append((str(p["e"]).strip(), [str(a).strip() for a in p["a"] if str(a).strip()]))
    return own + [(e, a.split("|")) for e, a in EMOJI]


def letters_hint(word: str) -> str:
    n = len(_TASHKEEL.sub("", word).replace(" ", ""))
    return f"💡 تلميح: تبدأ بحرف «{word[:1]}» ({n} حروف)"


def new_emoji(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    pool = emoji_puzzles(cfg)
    fresh = [p for p in pool if p[0] not in set(avoid)] or pool
    e, answers = rng.choice(fresh)
    return QuickRound("emoji", e, answers, int(cfg.get("round_seconds") or 30), clock, letters_hint(answers[0]))


def new_reverse(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    """An everyday word (3 to 6 letters) shown backwards: «ةرايس» -> سيارة. Never one that reads the same both ways."""
    scramble_pool()
    pool = [w for w, _ in _POOL_CATS if 3 <= len(w) <= 6 and norm(w[::-1]) != norm(w)]
    recent = {norm(a) for a in avoid}
    word = rng.choice([w for w in pool if norm(w) not in recent] or pool)
    return QuickRound("reverse", word[::-1], [word], int(cfg.get("round_seconds") or 30), clock, letters_hint(word))


def new_math(cfg: dict, clock=time.time, rng=random) -> QuickRound:
    """easy: + and - (up to 20); normal: also x up to 10; hard: bigger numbers and ÷ (always a whole answer).
    Shown with Arabic digits; Arabic or Western digits both count."""
    level = cfg.get("level") if cfg.get("level") in MATH_LEVELS else "normal"
    ops = {"easy": "+-", "normal": "+-x", "hard": "+-x/"}[level]
    op = rng.choice(ops)
    big = level == "hard"
    if op == "+":
        a, b = rng.randint(1, 99 if big else 20), rng.randint(1, 99 if big else 20)
        ans = a + b
    elif op == "-":
        a, b = rng.randint(1, 99 if big else 20), rng.randint(1, 99 if big else 20)
        a, b = max(a, b), min(a, b)
        ans = a - b
    elif op == "x":
        a, b = rng.randint(2, 15 if big else 10), rng.randint(2, 15 if big else 10)
        ans = a * b
    else:
        b, ans = rng.randint(2, 12), rng.randint(2, 12)
        a = b * ans
    sign = {"+": "+", "-": "−", "x": "×", "/": "÷"}[op]
    prompt = f"{a} {sign} {b} = ؟"       # 1.14.0 (owner): Western digits, also in Arabic (both are accepted as answers)
    return QuickRound("math", prompt, [str(ans)], int(cfg.get("round_seconds") or 20), clock)


LADDER_LETTERS = "ابتجحخدرزسشصعفقكلمنهوي"        # letters with many easy words (not ث ذ ض ظ غ)
LADDER_WORDS = (2, 3, 4, 5)


def new_ladder(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    """1.14.0 «سلم»: the fastest to write N different words starting with a letter."""
    n = int(cfg.get("words") or 3)
    n = n if n in LADDER_WORDS else 3
    letters = [c for c in LADDER_LETTERS if c not in set(avoid)] or list(LADDER_LETTERS)
    letter = rng.choice(letters)
    r = QuickRound("ladder", letter, [letter], int(cfg.get("round_seconds") or 30), clock)
    r.letter, r.count, r.win_text = letter, n, ""
    return r


def new_trivia(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    """1.14.0 «سؤال»: a question. level "easy": the 4 shuffled choices are shown; "hard" (default): only the question,
    with a halfway hint (first letter + letters). Viewers write the answer itself (not a number); trivia_ar.ALSO = short forms.
    1.15.0 (owner): "questions" = how hard the questions are: easy (default), medium, hard, or mixed (all three)."""
    from .trivia_ar import LEVELS, ALSO
    tier = cfg.get("questions") if cfg.get("questions") in TRIVIA_TIERS else "easy"
    qs = [q for k in ("easy", "medium", "hard") for q in LEVELS[k]] if tier == "mixed" else list(LEVELS[tier])
    pool = [q for q in qs if q[0] not in set(avoid)] or qs
    q, right, *wrong = rng.choice(pool)
    choices = [right] + list(wrong)
    rng.shuffle(choices)
    easy = cfg.get("level") == "easy"
    r = QuickRound("trivia", q, [right] + list(ALSO.get(right, ())), int(cfg.get("round_seconds") or 30), clock,
                   "" if easy else trivia_hint(right))
    r.choices, r.right, r.out, r.show_choices = choices, choices.index(right), set(), easy
    return r


def new_riddle(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    """1.15.0 «لغز»: an easy riddle; any of its fair answers wins; a halfway hint like Hard «سؤال»."""
    from .riddles_ar import RIDDLES
    pool = [x for x in RIDDLES if x[0] not in avoid] or RIDDLES
    q = rng.choice(pool)
    r = QuickRound("riddle", q[0], q[1:], int(cfg.get("round_seconds") or 45), clock, trivia_hint(q[1]))
    r.show_choices = False
    return r


def new_translate(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    """1.15.0 «ترجم»: a word to translate. level: easy (everyday) / hard; way: en_ar, ar_en or mixed. Every fair translation
    wins: all the words on the other side of any line that has the shown word («رجل» -> man or foot)."""
    from .translate_words import EASY, HARD
    words = HARD if cfg.get("level") == "hard" else EASY
    way = cfg.get("way") or "mixed"
    way = rng.choice(("en_ar", "ar_en")) if way == "mixed" else way
    side = 0 if way == "en_ar" else 1
    pool = [w for w in words if w[side][0] not in avoid] or words
    pick = rng.choice(pool)
    shown = pick[side][0]
    k = trivia_key(shown)
    answers = list(pick[1 - side])
    for w in EASY + HARD:                                  # the same word with another meaning, in either list
        if w is not pick and any(trivia_key(x) == k for x in w[side]):
            answers += [a for a in w[1 - side] if a not in answers]
    r = QuickRound("translate", shown, answers, int(cfg.get("round_seconds") or 30), clock, trivia_hint(answers[0]))
    r.show_choices, r.to = False, ("ar" if way == "en_ar" else "en")
    return r


def new_opposite(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    """1.15.0 «ضد»: a word; the first viewer to write its opposite wins. level easy (everyday) / hard. Either side of a
    pair can be shown; every opposite counts, from every line that holds the shown word («قديم»: جديد or حديث)."""
    from .opposites_ar import EASY, HARD
    pairs = HARD if cfg.get("level") == "hard" else EASY
    shown_all = [(p, 0) for p in pairs] + [(p, 1) for p in pairs]
    pool = [x for x in shown_all if x[0][x[1]][0] not in avoid] or shown_all
    pick, side = rng.choice(pool)
    shown = pick[side][0]
    k = trivia_key(shown)
    answers = list(pick[1 - side])
    for p in EASY + HARD:
        for s in (0, 1):
            if p is not pick and any(trivia_key(x) == k for x in p[s]):
                answers += [a for a in p[1 - s] if a not in answers]
    r = QuickRound("opposite", shown, answers, int(cfg.get("round_seconds") or 30), clock, trivia_hint(answers[0]))
    r.show_choices = False
    return r


def new_oddone(cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    """1.15.0 «الدخيل»: 4 words, 3 belong together; the first viewer to write the odd one wins. Like Easy «سؤال», writing
    one of the other three means that viewer can't answer again this round (so nobody can just send all four).
    level easy: 3 words of one group + 1 of a clearly different group; hard: the close sets in oddone_ar.HARD."""
    from .oddone_ar import EASY, HARD, RELATED
    if cfg.get("level") == "hard":
        pool = [x for x in HARD if x[0] not in avoid] or HARD
        rule, members, odds = rng.choice(pool)
        three, odd = rng.sample(members, 3), rng.choice(odds)
    else:
        pool = [g for g in EASY if g not in avoid] or list(EASY)
        rule = rng.choice(pool)
        near = {b for a, b in RELATED if a == rule} | {a for a, b in RELATED if b == rule}
        other = rng.choice([g for g in EASY if g != rule and g not in near])
        three, odd = rng.sample(EASY[rule], 3), rng.choice(EASY[other])
    choices = three + [odd]
    rng.shuffle(choices)
    r = QuickRound("oddone", " • ".join(choices), [odd], int(cfg.get("round_seconds") or 30), clock)
    r.choices, r.right, r.out, r.show_choices, r.why = choices, choices.index(odd), set(), True, rule
    return r


def new_quick(game: str, cfg: dict, avoid=(), clock=time.time, rng=random) -> QuickRound:
    if game == "ladder":
        return new_ladder(cfg, avoid, clock, rng)
    if game == "trivia":
        return new_trivia(cfg, avoid, clock, rng)
    if game == "riddle":
        return new_riddle(cfg, avoid, clock, rng)
    if game == "translate":
        return new_translate(cfg, avoid, clock, rng)
    if game == "opposite":
        return new_opposite(cfg, avoid, clock, rng)
    if game == "oddone":
        return new_oddone(cfg, avoid, clock, rng)
    if game == "emoji":
        return new_emoji(cfg, avoid, clock, rng)
    if game == "reverse":
        return new_reverse(cfg, avoid, clock, rng)
    return new_math(cfg, clock, rng)


# ---------- wins: a total per viewer plus how many came from each game ----------

PERIODS = ("week", "month")        # 1.15.0 (owner): weekly and monthly leaderboards next to all time


def period_ids(now=None) -> dict:
    """The current week (the date of its Sunday: the owner's choice) and month, on this PC's clock."""
    import datetime as _dt
    d = _dt.datetime.fromtimestamp(time.time() if now is None else now).date()
    sunday = d - _dt.timedelta(days=(d.weekday() + 1) % 7)
    return {"week": sunday.isoformat(), "month": d.strftime("%Y-%m")}


def add_win(wins: dict, uid: str, name: str, game: str = "letters", now=None) -> int:
    e = wins.setdefault(str(uid), {"name": name, "wins": 0, "games": {}})
    e["name"], e["wins"] = name, int(e.get("wins", 0)) + 1
    g = e.setdefault("games", {})
    g[game] = int(g.get(game, 0)) + 1
    for p, pid in period_ids(now).items():       # 1.15.0: this week / this month start again by themselves
        sub = e.get(p) if isinstance(e.get(p), dict) and e[p].get("id") == pid else {"id": pid, "wins": 0, "games": {}}
        sub["wins"] = int(sub.get("wins", 0)) + 1
        sub.setdefault("games", {})[game] = int(sub["games"].get(game, 0)) + 1
        e[p] = sub
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


def ar_wins(n: int) -> str:
    """1.18.0: the number of wins the way it's said in Arabic: فوز واحد، فوزتين، 3 فوزات … 10 فوزات، 11 فوز، 103 فوزات."""
    n = int(n)
    if n == 1:
        return "فوز واحد"
    if n == 2:
        return "فوزتين"
    return f"{n} فوزات" if 3 <= n % 100 <= 10 else f"{n} فوز"


def wins_of(e: dict, game: str | None = None, period: str | None = None, now=None) -> int:
    """All-time wins (all games or one); with period "week" / "month": only this week's / month's (0 once it's over)."""
    if not isinstance(e, dict):
        return 0
    if period:
        sub = e.get(period)
        if not isinstance(sub, dict) or sub.get("id") != period_ids(now)[period]:
            return 0
        e = sub
    if game is None:
        return int(e.get("wins", 0) or 0)
    return int((e.get("games") or {}).get(game, 0) or 0)


def top(wins: dict, n: int = 5, game: str | None = None, period: str | None = None, now=None) -> list:
    """[(name, wins)] best first: all games together, or one game; all time, or this week / month. Nobody with 0 wins."""
    rows = [(e.get("name", "?"), wins_of(e, game, period, now)) for e in wins.values() if isinstance(e, dict)]
    return sorted((r for r in rows if r[1] > 0), key=lambda x: (-x[1], str(x[0]).lower()))[:n]


_PERIOD_WORDS = {"week": {"اسبوع", "الاسبوع", "هالاسبوع", "اسبوعي", "week", "weekly"},
                 "month": {"شهر", "الشهر", "هالشهر", "شهري", "month", "monthly"}}


def period_named(word: str):
    """«أسبوع» / «شهر» (or week / month) -> "week" / "month", else None."""
    w = norm(str(word).strip().lstrip("!")).casefold()
    return next((p for p, ws in _PERIOD_WORDS.items() if w in {norm(x).casefold() for x in ws}), None)


def game_named(text: str):
    """The game for its short name: «حروف», «رتب», «ايموجي», «عكس», «احسب» (also with ! or ال), else None."""
    want = norm(str(text).strip().lstrip("!"))
    return next((k for k, v in GAME_NAMES.items() if norm(v) == want), None) if want else None


def breakdown(e: dict) -> str:
    """«حروف 5، رتب 4»: the games this viewer has won, in the games' order."""
    return "، ".join(f"{GAME_NAMES[k]} {wins_of(e, k)}" for k in GAME_KEYS if wins_of(e, k))


def set_wins(wins: dict, uid: str, name: str, games: dict) -> dict:
    """1.17.0 (owner): the streamer sets a viewer's all-time wins by hand (for one whose wins were lost). games: {game: n}.
    This week / month can't be more than the new numbers. All 0 = off the leaderboard."""
    uid = str(uid)
    g = {k: max(0, min(10 ** 6, int(games.get(k, 0) or 0))) for k in GAME_KEYS if k in games}
    g = {k: n for k, n in g.items() if n}
    if not g:
        wins.pop(uid, None)
        return wins
    e = dict(wins.get(uid) or {})
    e.update(name=name or e.get("name") or "?", wins=sum(g.values()), games=g)
    for p in PERIODS:
        sub = e.get(p)
        if isinstance(sub, dict) and isinstance(sub.get("games"), dict):
            pg = {k: min(int(n or 0), g.get(k, 0)) for k, n in sub["games"].items()}
            pg = {k: n for k, n in pg.items() if n}
            e[p] = dict(sub, games=pg, wins=sum(pg.values()))
    wins[uid] = e
    return wins


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
