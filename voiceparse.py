"""1.17.0 (beta): Voice commands. Turns what the streamer said (already speech-to-text) into an action.

Pure functions, no Windows parts, so they can be tested anywhere. English and Arabic (as people actually say it, also
English words said in Arabic letters, like «تايم اوت»).

parse(text) -> {"act": ..., ...} or None
  timeout  {who, secs}          ban {who}           unban {who}
  addcmd   {name, reply}        delcmd {name}       reset {what}
  game     {game | "random"}    pause / resume      giveaway
  title    {text}               setgame {text}
  yes / no / pick {n}           (answers while the app asks "Timeout sami_gamer?")
"""
import difflib
import re

_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_PUNCT = re.compile(r"[^\w\s!_]", re.UNICODE)
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def norm(text: str) -> str:
    """Small letters, no punctuation or Arabic diacritics, one spelling for أ إ آ ا / ة ه / ى ي, Western digits."""
    t = str(text or "").translate(_AR_DIGITS).casefold()
    t = _TASHKEEL.sub("", t)
    t = re.sub("[أإآٱ]", "ا", t).replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    t = t.replace("’", "'").replace("'", "")
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


# ---------- numbers and durations ----------

_EN_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
           "fifty": 50, "sixty": 60, "ninety": 90, "hundred": 100}
_AR_NUM = {"واحد": 1, "وحده": 1, "اثنين": 2, "اثنان": 2, "ثنتين": 2, "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4,
           "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثمانيه": 8, "ثمن": 8, "تسع": 9,
           "تسعه": 9, "عشر": 10, "عشره": 10, "ربع": 15, "عشرين": 20, "ثلاثين": 30, "نص": 30, "اربعين": 40,
           "خمسين": 50, "ستين": 60, "مية": 100, "ميه": 100}
_UNIT = [  # (words, seconds)
    (("second", "seconds", "sec", "secs", "ثانيه", "ثواني", "ثانيتين"), 1),
    (("minute", "minutes", "min", "mins", "دقيقه", "دقايق", "دقائق", "دقيقتين", "دقيقة"), 60),
    (("hour", "hours", "hr", "ساعه", "ساعات", "ساعتين"), 3600),
    (("day", "days", "يوم", "ايام", "يومين"), 86400),
]
_DUAL = {"دقيقتين": 2, "ساعتين": 2, "ثانيتين": 2, "يومين": 2}


def _num(word: str):
    if word.isdigit():
        return int(word)
    return _EN_NUM.get(word, _AR_NUM.get(word))


def _unit(word: str):
    for words, secs in _UNIT:
        if word in words:
            return secs
    return None


def duration(words: list):
    """(seconds, the words that said it) from the end of a phrase: "10 minutes", "ten minutes", "an hour",
    «عشر دقايق», «دقيقتين», «نص ساعه», «ساعه». None when no time was said."""
    for i, w in enumerate(words):
        u = _unit(w)
        if u is None:
            continue
        n, start = 1, i
        if w in _DUAL:
            n = _DUAL[w]
        elif i > 0 and _num(words[i - 1]) is not None:
            n, start = _num(words[i - 1]), i - 1
            if start > 0 and words[start - 1] in ("و", "and") and start > 1 and _num(words[start - 2]) is not None:
                n, start = n + _num(words[start - 2]), start - 2         # «خمس و عشرين دقيقه»
        if words[start - 1:start] == ["نص"] or words[start - 1:start] == ["half"]:
            n, start = 0.5, start - 1                                     # «نص ساعه», "half an hour" (→ 30 min)
        if w in ("ساعه", "hour") and i > 0 and words[i - 1] == "نص":
            n, start = 0.5, i - 1
        return int(max(1, round(n * u))), words[start:i + 1]
    return None


# ---------- the phrases ----------

YES = {"yes", "yeah", "yep", "yup", "sure", "confirm", "ok", "okay", "do it", "go", "نعم", "ايوه", "ايه", "اي", "اكيد",
       "تمام", "اوكي", "اوك", "يس", "ايوا", "نفذ"}
NO = {"no", "nope", "cancel", "stop", "dont", "never mind", "nevermind", "لا", "لاء", "الغاء", "الغي", "كنسل", "خلاص لا", "نو"}
PICK = {"one": 1, "first": 1, "1": 1, "two": 2, "second": 2, "2": 2, "three": 3, "third": 3, "3": 3,
        "واحد": 1, "الاول": 1, "اول": 1, "اثنين": 2, "الثاني": 2, "ثاني": 2, "ثلاثه": 3, "الثالث": 3, "ثالث": 3}

# (act, list of lead-in patterns). The lead-in is matched at the start; what follows is the "rest".
LEADS = [
    ("unban", [r"un ?ban", r"unbanned", r"فك (ال)?(بان|باند|حظر)( عن)?", r"انبان", r"ان بان", r"شيل (ال)?(بان|حظر)( عن)?"]),
    ("ban", [r"ban", r"band", r"banned", r"بان", r"باند", r"احظر", r"حظر", r"بند"]),
    ("timeout", [r"time ?out", r"timed out", r"mute", r"تايم ?اوت", r"تايماوت", r"تايم اوت", r"ميوت", r"اسكت", r"سكت"]),
    ("delcmd", [r"(delete|remove) (the )?command", r"(احذف|امسح|شيل) (ال)?امر"]),
    ("addcmd", [r"(add|new|create|make) (a )?(new )?command", r"(اضف|ضيف|سوي|اعمل) (لي )?(ال)?امر( جديد)?", r"امر جديد"]),
    ("reset", [r"reset( the)?", r"(صفر|تصفير|صفري)( ال| عداد| العداد)?", r"رجع .* (ل|الى )?صفر"]),
    ("resume", [r"(resume|unpause|start|turn on|wake up)( the)? bot", r"(شغل|كمل|رجع) (ال)?بوت"]),
    ("pause", [r"(pause|stop|turn off|mute)( the)? bot", r"(وقف|ايقاف|طفي|اوقف) (ال)?بوت"]),
    ("giveaway", [r"(start|begin|open)( a| the)? (give ?away|raffle)", r"(ابدا|افتح|سوي) (ال)?(سحب|قيف ?اواي|جيف ?اواي)", r"سحب جديد"]),
    ("title", [r"(change|set)( the)? (stream )?title( to)?", r"(غير|حط) (ال)?عنوان( الى| ل| الي)?"]),
    ("setgame", [r"(change|set)( the)? (game|category)( to)?", r"(غير|حط) (ال)?(لعبه|كاتيقوري|قسم)( الى| ل| الي)?"]),
    ("game", [r"(start|play|begin|launch)( a| the)?( game)?( of)?", r"(ابدا|شغل|العب|ابدي)( لعبه| ال)?"]),
]
_LEADS = [(act, [re.compile(r"^(?:hey bot |يا بوت |بوت )?(?:please |لو سمحت )?(?:" + p + r")(?:\s+|$)") for p in pats]) for act, pats in LEADS]

GAME_WORDS = {
    "letters": ["letters", "letter", "حروف", "اسم جماد", "اسم جماد نبات"],
    "scramble": ["scramble", "unscramble", "رتب"],
    "emoji": ["emoji", "emojis", "ايموجي", "ايموجيز"],
    "reverse": ["reverse", "backwards", "عكس"],
    "math": ["math", "maths", "sum", "احسب", "حساب"],
    "ladder": ["ladder", "سلم"],
    "trivia": ["trivia", "question", "quiz", "سوال", "سؤال", "اسئله"],
    "riddle": ["riddle", "riddles", "لغز", "الغاز"],
    "translate": ["translate", "translation", "ترجم", "ترجمه"],
    "opposite": ["opposite", "opposites", "ضد", "عكس الكلمه"],
    "oddone": ["odd one out", "odd one", "dakheel", "الدخيل", "دخيل"],
}


def parse(text: str):
    t = norm(text)
    if not t:
        return None
    words = t.split()
    if t in YES or " ".join(words[:2]) in YES:
        return {"act": "yes"}
    if t in NO or words[0] in NO:
        return {"act": "no"}
    for w in words[:3]:
        if w in PICK and len(words) <= 3:
            return {"act": "pick", "n": PICK[w]}
    for act, pats in _LEADS:
        for rx in pats:
            m = rx.match(t)
            if not m:
                continue
            rest = t[m.end():].strip()
            out = _finish(act, rest)
            if out:
                return out
    return None


def _strip(rest: str, *drop) -> str:
    w = rest.split()
    while w and w[0] in drop:
        w = w[1:]
    return " ".join(w)


def _finish(act: str, rest: str):
    if act in ("timeout", "ban", "unban"):
        words = rest.split()
        d = duration(words) if act == "timeout" else None
        if d:
            secs, said = d
            k = len(words) - len(said)
            for i in range(len(words) - len(said) + 1):
                if words[i:i + len(said)] == said:
                    k = i
                    break
            words = words[:k] + words[k + len(said):]
        words = [w for w in words if w not in ("for", "لمده", "مده", "ل", "the", "user", "ذا", "هذا", "اللي", "يوزر")]
        if not words:
            return None
        out = {"act": act, "who": " ".join(words)}
        if act == "timeout":
            out["secs"] = min(14 * 86400, d[0]) if d else 600            # 10 minutes when no time was said
        return out
    if act == "addcmd":
        words = _strip(rest, "called", "named", "اسمه", "باسم").split()
        if not words:
            return None
        name = words[0]
        reply = " ".join(words[1:])
        for sep in ("that says ", "says ", "saying ", "reply ", "with ", "يقول ", "رده ", "الرد ", "ويقول "):
            if reply.startswith(sep):
                reply = reply[len(sep):]
                break
        return {"act": "addcmd", "name": name, "reply": reply.strip()}
    if act == "delcmd":
        name = _strip(rest, "called", "named")
        return {"act": "delcmd", "name": name} if name else None
    if act == "reset":
        what = _strip(rest, "the", "counter", "عداد", "العداد")
        what = re.sub(r"\s*(counter|عداد|الى صفر|ل صفر|صفر)$", "", what).strip()
        return {"act": "reset", "what": what} if what else None
    if act in ("pause", "resume", "giveaway"):
        return {"act": act}
    if act in ("title", "setgame"):
        return {"act": act, "text": rest} if rest else None
    if act == "game":
        if rest in {norm(x) for x in ("random", "random game", "any game", "a random game", "عشوائية", "اي لعبة", "لعبة عشوائية", "أي شي", "اي وحده")}:
            return {"act": "game", "game": "random"}
        g = game_of(rest)
        return {"act": "game", "game": g} if g else None
    return None


def game_of(text: str):
    t = norm(text)
    t = re.sub(r"^(the |a |game |لعبه |ال(?=\S))", "", t).strip()
    for key, names in GAME_WORDS.items():
        for n in names:
            n = norm(n)
            if t == n or t.startswith(n + " ") or t == "ال" + n or (len(n) > 3 and t.startswith(n)):
                return key
    return None


# ---------- matching what was said to real names ----------

_AR_LATIN = {"ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "th", "ر": "r",
             "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f",
             "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "o", "ي": "i", "ء": "", "پ": "p",
             "گ": "g", "چ": "ch", "ڤ": "v"}


def latin(text: str) -> str:
    """A rough Latin spelling of an Arabic-letter name («سامي» → sami), so it can be compared with Twitch logins."""
    return "".join(_AR_LATIN.get(c, c) for c in norm(text))


def _squash(s: str) -> str:
    s = latin(s)
    for word, n in sorted(_EN_NUM.items(), key=lambda x: -len(x[0])):
        if len(word) > 2:
            s = re.sub(rf"\b{word}\b", str(n), s)
    return re.sub(r"[^a-z0-9]", "", s)


def _vowelless(s: str) -> str:
    return re.sub(r"[aeiouy]", "", s)


def match_people(said: str, people: list, limit: int = 3) -> list:
    """The people most likely meant: people = [(login, display name, seconds since they wrote)], most recent first.
    Returns up to `limit` [(login, display, score)], best first."""
    want = _squash(said)
    if not want:
        return []
    scored = []
    for login, display, ago in people:
        have = re.sub(r"[^a-z0-9]", "", str(login).lower())
        if not have:
            continue
        r = difflib.SequenceMatcher(None, want, have).ratio()
        if have.startswith(want) and len(want) >= 3:   # sami9x / sami_gamer: "sami" alone is a strong hint
            r = max(r, 0.8 + 0.1 * len(want) / max(len(have), 1))
        elif want in have and len(want) >= 3:
            r = max(r, 0.7 + 0.1 * len(want) / max(len(have), 1))
        rv = difflib.SequenceMatcher(None, _vowelless(want), _vowelless(have)).ratio()
        r = max(r, rv * 0.92)                      # Arabic speech loses vowels: «سمي» ~ sami
        r += max(0.0, 0.12 - ago / 600 * 0.12)     # who wrote in the last minutes counts more
        if r >= 0.45:
            scored.append((r, login, display))
    scored.sort(key=lambda x: -x[0])
    if scored:                                  # only names about as likely as the best one
        best = scored[0][0]
        scored = [x for x in scored if x[0] >= best - 0.2]
    return [(login, display, round(r, 2)) for r, login, display in scored[:limit]]


def _bare(name: str) -> str:
    n = norm(name).lstrip("!")
    return n[2:] if n.startswith("ال") and len(n) > 4 else n


def match_name(said: str, names: list, cutoff: float = 0.6):
    """The command or counter name meant ("deaths", «الموتات» → «!موتات»). None when nothing is close."""
    want = _bare(said)
    if not want:
        return None
    best, score = None, 0.0
    for n in names:
        b = _bare(n)
        if not b:
            continue
        r = difflib.SequenceMatcher(None, want, b).ratio()
        if b == want:
            r = 1.0
        elif latin(b) == latin(want):
            r = 0.95
        if r > score:
            best, score = n, r
    return best if score >= cutoff else None


def command_name(said: str) -> str:
    """The name of a new command said out loud: "socials" → "!socials", «روابط» → «!روابط»."""
    w = norm(said).split()
    return ("!" + w[0].lstrip("!")) if w else ""
