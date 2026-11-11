"""1.17.0 (beta): Voice commands. Turns what the streamer said (already speech-to-text) into an action.

Pure functions, no Windows parts, so they can be tested anywhere. English and Arabic (as people actually say it, also
English words said in Arabic letters, like «تايم اوت»).

parse(text) -> {"act": ..., ...} or None
  timeout  {who, secs}          ban {who}           unban {who}
  vip / unvip / mod / unmod {who}                   (1.18.0)
  count {what, op: add | sub | set, n}   runcmd {name}   ignore / unignore {who}   clear       (1.18.0)
  addcmd   {name, reply}        editcmd {name, reply}   delcmd {name}       reset {what}
  game     {game | "random"}    pause / resume      giveaway
  title    {text}               setgame {text}       say {text} (sent in chat after a yes)
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
    t = re.sub("[أإآٱ]", "ا", t).replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي").replace("ڤ", "ف")
    t = t.replace("’", "'").replace("'", "")
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


# ---------- numbers and durations ----------

_EN_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
           "fifty": 50, "sixty": 60, "ninety": 90, "hundred": 100}
_AR_NUM = {"واحد": 1, "وحده": 1, "اثنين": 2, "اثنان": 2, "ثنتين": 2, "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4,
           "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثمانيه": 8, "ثمن": 8, "تسع": 9,
           "تسعه": 9, "عشر": 10, "عشره": 10, "حداش": 11, "احدعش": 11, "اطناش": 12, "اثنعش": 12, "ثلطعش": 13,
           "ربعطعش": 14, "خمسطعش": 15, "خمستعش": 15, "ستطعش": 16, "عشرين": 20, "ثلاثين": 30, "اربعين": 40,
           "خمسين": 50, "ستين": 60, "تسعين": 90, "مية": 100, "ميه": 100}
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


_FRAC = {"نص": 0.5, "half": 0.5, "ربع": 0.25, "quarter": 0.25}


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
        if i > 0 and words[i - 1] in _FRAC:                               # «نص ساعه», «ربع ساعه», "half an hour"
            n, start = _FRAC[words[i - 1]], i - 1
        elif i > 1 and words[i - 1] in ("a", "an") and words[i - 2] in _FRAC:
            n, start = _FRAC[words[i - 2]], i - 2
        end = i
        if i + 2 < len(words) + 1 and words[i + 1:i + 3] in (["و", "نص"], ["and", "half"]):
            n, end = n + 0.5, i + 2                                       # «ساعه ونص» (split as «و نص» below)
        elif words[i + 1:i + 2] in (["ونص"], ["وربع"]):
            n, end = n + (0.5 if words[i + 1] == "ونص" else 0.25), i + 1
        return int(max(1, round(n * u))), words[start:end + 1]
    return None


# ---------- the phrases ----------

YES = {"yes", "yeah", "yep", "yup", "sure", "confirm", "ok", "okay", "do it", "go", "go ahead", "yes please", "نعم", "ايوه",
       "ايه", "اي", "اكيد", "تمام", "اوكي", "اوك", "يس", "ايوا", "نفذ", "طبعا", "يب", "اوكيه", "صح", "اكيد نعم", "ايوه نفذ", "يلا"}
NO = {"no", "nope", "cancel", "stop", "dont", "never mind", "nevermind", "no no", "لا", "لاء", "الغاء", "الغي", "كنسل", "خلاص لا",
      "نو", "لا لا", "خلاص", "لا تسوي", "لا خلاص", "ما ابي", "لا تنفذ"}
UNDO = {"cancel", "undo", "cancel that", "undo that", "cancel it", "take it back", "كنسل", "كانسل", "كنسله", "تراجع",
        "الغي", "الغاء", "الغيها", "الغيه", "رجعها", "رجعه", "رجع اللي سويته", "تراجع عنها", "كنسلها", "خلاص كنسل"}
PICK = {"one": 1, "first": 1, "1": 1, "two": 2, "second": 2, "2": 2, "three": 3, "third": 3, "3": 3,
        "واحد": 1, "الاول": 1, "اول": 1, "اثنين": 2, "الثاني": 2, "ثاني": 2, "ثلاثه": 3, "الثالث": 3, "ثالث": 3,
        "ثنين": 2, "اثنان": 2, "ثلاث": 3}

# (act, list of lead-in patterns). The lead-in is matched at the start; what follows is the "rest".
_VIPW = r"(?:vip|vips|في اي بي|في ايبي|فيايبي|في اي بيه|فيب|فيبي|ف اي ب)"
_MODW = r"(?:mod|mods|moderator|مود|مودريتر|موديريتر|مودرتر|اشراف|الاشراف|مشرف|مشرفه)"
LEADS = [
    # 1.18.0: the Chat box overlay hidden / shown on stream («خبّي الشات», «ورّ الشات»)
    ("hidechat", [r"hide( the)? chat( box)?", r"(خب|خبي|خبى|اخفي|اخف|سكر|طفي) (ال)?(شات|تشات|chat)( بوكس)?( من البث| عن البث)?"]),
    ("showchat", [r"(show|unhide)( the)? chat( box)?", r"(ور|وري|اعرض|رجع|طلع|افتح|اظهر) (ال)?(شات|تشات|chat)( بوكس)?( على البث| علي البث| في البث)?"]),
    # 1.18.0: chat cleared, a command run, someone ignored / no longer ignored by the bot
    ("clear", [r"clear( the)? chat", r"(امسح|نظف|نضف|كلير|فضي|فرمت|امسحي) (ال)?(شات|تشات|chat)( كله| كامل)?"]),
    ("unignore", [r"(un ?ignore|stop ignoring|dont ignore)", r"(فك|شيل|الغي|وقف) (ال)?(تجاهل|تطنيش)( عن| من)?", r"(لا تتجاهل|لا تطنش|رجع)"]),
    ("ignore", [r"ignore", r"(تجاهل|طنش|تطنيش|انطنش)( ل| على)?"]),
    ("runcmd", [r"(run|use|trigger|do)( the)? command", r"(run|use|trigger)( the)?(?= \S+ command$)", r"(شغل|شغ|شغلي|نفذ|سو|سوي|ارسل|رسل|استخدم) (ال)?(امر|كوماند)",
                r"(امر|الامر|كوماند)"]),
    # 1.18.0: VIP and moderator (the removals first: «شيل الفي اي بي عن فقبن», «شيل المود عن فقبن»)
    ("unvip", [r"un ?vip", r"(remove|take)( the)? vip( from)?", r"(شيل|سحب|اسحب|نزل|فك|احذف|ارفع|نزع|انزع) (ال)?" + _VIPW + r"( عن| من| حق)?"]),
    ("unmod", [r"un ?mod", r"(de ?mod|demote)", r"(remove|take)( the)? (mod|moderator)( from)?",
               r"(شيل|سحب|اسحب|نزل|فك|احذف|ارفع|نزع|انزع) (ال)?" + _MODW + r"( عن| من| حق)?"]),
    ("vip", [r"(make|give)( him| her)?( a)? vip( to)?", r"vip",
             r"(عط|عطه|اعط|اعطي|عطي|حط|خل|خلي|سو|سوي|ضيف) (ال)?" + _VIPW + r"( ل| على| حق)?", _VIPW + r"( ل)?"]),
    ("mod", [r"(make|give)( him| her)?( a)? (mod|moderator)( to)?", r"(mod|modded)",
             r"(عط|عطه|اعط|اعطي|عطي|حط|خل|خلي|سو|سوي|ضيف) (ال)?" + _MODW + r"( ل| على| حق)?", r"(مود|مشرف)( ل)?"]),
    ("unban", [r"un ?ban", r"unbanned", r"(فك|شيل|ارفع) (ال)?(بان|باند|حظر|البند)( عن| من)?", r"(انبان|ان بان|انبن)", r"فك عن"]),
    ("ban", [r"(ban|band|banned|bann)", r"(بان|باند|بند|بنّد|احظر|حظر|احظره|بنده|اطرد|اطرده|كيك)( ل| على)?",
             r"(عط|عطه|اعط|اعطي|عطي) (ال)?(بان|باند|حظر)( ل)?"]),
    ("timeout", [r"(time ?out|timed out|timeout|mute|silence)", r"(تايم ?اوت|تايماوت|تيم اوت|ميوت|اسكت|سكت|سكته|اسكته|طرد مؤقت)( ل| على)?",
                 r"(عط|عطه|اعط|اعطي|عطي|حط) (ال)?(تايم ?اوت|تايماوت|ميوت)( ل| على)?"]),
    ("reset", [r"reset( the)?", r"(صفر|تصفير|صفري|ريست|ريسيت|ريسيت ل)( ال| عداد| العداد)?", r"(رجع|خل|خلي) (عداد )?.* (ل|الى |علي )?صفر"]),
    ("title", [r"(change|set)( the)? (stream )?title( to)?", r"(غير|حط|عدل|خل|خلي) (ال)?(عنوان|تايتل|title)( الى| ل| الي| يصير| يكون)?"]),
    ("setgame", [r"(change|set)( the)? (game|category)( to)?", r"(غير|حط|خل|خلي) (ال)?(لعبه|كاتيقوري|قسم|قيم|game|category)( الى| ل| الي| يصير| تصير)?"]),
    ("say", [r"(say|send|type|write|tell chat)(?: (?:in|to|on) (?:the )?chat| chat)?",
             r"(قول|قل|قولي|قوله|قولهم|قولو|اكتب|ارسل|رسل)(?: (?:في|على|ب|ل) ?(?:ال)?شات| (?:ال|لل|بال)?شات)?"]),
    ("game", [r"(start|play|begin|launch|lets play)( a| the)?( game)?( of)?",
              r"(ابدا|شغل|العب|ابدي|ستارت|يلا|نبي|ابي|ودي|خلنا نلعب|نلعب|يلا نلعب|بلش|بدينا|ابدأ|فتح|افتح|نزل)( لعبه| جوله| ال)?",
              r"(lets do|do|run|open)( a| the)?( game| round)?( of)?", r"(جوله|لعبه|اللعبه|round of|game of)"]),
]
FILLERS = ["hey bot", "hey", "ok bot", "please", "can you", "could you", "can u", "now", "يا بوت", "بوت", "لو سمحت", "ممكن",
           "طيب", "يلا يا بوت", "الحين", "تكفى", "ياخي", "اخوي", "بسرعه", "please bot"]
_LEADS = [(act, [re.compile(r"^(?:" + p + r")(?:\s+|$)") for p in pats]) for act, pats in LEADS]
_FILL = sorted((norm(f) for f in FILLERS), key=len, reverse=True)


def _unfill(t: str) -> str:
    """Drops polite and filler words at the start and end: «يا بوت لو سمحت …», "… please"."""
    changed = True
    while changed and t:
        changed = False
        for f in _FILL:
            if t.startswith(f + " "):
                t, changed = t[len(f) + 1:], True
            elif t.endswith(" " + f) and f not in ("بوت", "hey", "ممكن"):      # (a name can end in «بوت»: «سبام بوت»)
                t, changed = t[:-len(f) - 1], True
    return t.strip()


# a word anywhere in the sentence that says which action it is (for any word order: «سامي عطه تايم اوت»)
ANYWHERE = [
    ("unvip", ["unvip", "شيل الفي اي بي", "شيل vip", "سحب الفي اي بي"]),
    ("unmod", ["unmod", "شيل المود", "شيل الاشراف", "سحب المود", "سحب الاشراف"]),
    ("vip", ["vip", "في اي بي", "فيب"]),
    ("mod", ["مشرف", "مود", "moderator"]),
    ("unban", ["unban", "انبان", "فك البان", "فك الحظر", "فك البند"]),
    ("timeout", ["timeout", "time out", "تايم اوت", "تايماوت", "تيم اوت", "ميوت", "mute"]),
    ("ban", ["ban", "بان", "باند", "حظر", "بند"]),
]
_DROP = {"عط", "عطه", "اعط", "اعطي", "عطي", "حط", "ل", "على", "علي", "عن", "حق", "give", "to", "for", "him", "her", "the", "user",
         "a", "an", "لمده", "مده", "ذا", "هذا", "اللي", "يوزر", "الولد", "واحد", "ابي", "نبي", "like", "about", "around",
         "تقريبا", "حوالي", "بس", "فقط", "just"}

GAME_WORDS = {      # every way a game gets called: the short name, the card's name, English, and what the engine mishears
    "letters": ["letters", "letter", "the letters game", "huroof", "horoof", "hurof", "حروف", "الحروف", "حرف", "حروب",
                "اسم جماد", "اسم جماد نبات", "اسم جماد نبات حيوان", "اسم جماد نبات حيوان بلاد", "اسماء"],
    "scramble": ["scramble", "unscramble", "scrambled", "rattib", "rateb", "رتب", "رتب الكلمه", "رتبها", "ترتيب", "رتيب"],
    "emoji": ["emoji", "emojis", "emoticons", "ايموجي", "ايموجيز", "ايموجيات", "اموجي", "ايموشن", "خمن من الايموجي",
              "خمن الايموجي"],
    "reverse": ["reverse", "backwards", "backward", "reversed", "aks", "عكس", "الكلمه المقلوبه", "مقلوب", "مقلوبه",
                "اقلب", "المقلوب"],
    "math": ["math", "maths", "quick math", "sum", "sums", "calculate", "numbers", "ahsib", "احسب", "حساب", "حساب سريع",
             "رياضيات", "ارقام", "جمع", "احسبها"],
    "ladder": ["ladder", "sullam", "سلم", "السلم", "سلالم", "درج"],
    "trivia": ["trivia", "question", "questions", "quiz", "سوال", "سؤال", "اسئله", "سوال وجواب", "سؤال وجواب", "مسابقه",
               "معلومات", "سوالف"],
    "riddle": ["riddle", "riddles", "lughz", "لغز", "الغاز", "لغز لي", "حزوره", "حزازير", "فوازير"],
    "translate": ["translate", "translation", "tarjim", "ترجم", "ترجمه", "الترجمه", "ترجملي", "انجليزي", "انقلش"],
    "opposite": ["opposite", "opposites", "antonym", "antonyms", "ضد", "الضد", "اضداد", "الاضداد", "عكس الكلمه",
                 "عكسها", "ضدها"],
    "oddone": ["odd one out", "odd one", "odd", "the odd one", "dakheel", "dakhil", "الدخيل", "دخيل", "الكلمه الدخيله",
               "الدخيله", "مين الدخيل", "وش الدخيل", "الغريب"],
}
EXTRA_GAMES = {}     # the streamer's own game commands (Mini games > settings), set by core/voice.py: {"name": "letters"}


def _game_pool(extra=None) -> dict:
    pool = {}
    for key, names in GAME_WORDS.items():
        for n in names:
            pool.setdefault(norm(n), key)
    for n, key in (extra if extra is not None else EXTRA_GAMES).items():
        n = norm(str(n).replace("!", " ").replace("؟", " ").replace("?", " "))
        if n and key in GAME_WORDS:
            pool.setdefault(n, key)
    return pool


# ---------- 1.18.0: spelling fixes: what the engine keeps hearing wrong → what it should be ----------
# Built in (common mishearings of the command words), plus the streamer's own and the ones learned by themselves
# (core/voice.py sets FIXES from the "voice_fixes" store: [{"heard": .., "to": ..}, …]).
BUILTIN_FIXES = [
    ("تايم ات", "تايم اوت"), ("تام اوت", "تايم اوت"), ("تايمن اوت", "تايم اوت"), ("تايم آوت", "تايم اوت"), ("تيماوت", "تايماوت"),
    ("time art", "timeout"), ("tame out", "timeout"), ("tie mount", "timeout"), ("time ought", "timeout"),
    ("بانّد", "باند"), ("بنّد", "بند"),
    ("un band", "unban"), ("anne ban", "unban"),
    ("في آي بي", "vip"), ("في أي بي", "vip"), ("فى اى بى", "vip"), ("ڤي آي بي", "vip"), ("في اي بي", "vip"), ("في.آي.بي", "vip"),
    ("v i p", "vip"), ("v.i.p", "vip"), ("vip's", "vip"), ("v ip", "vip"),
    ("مودريتور", "مود"), ("مودريتر", "مود"), ("موديريتور", "مود"), ("مودرايتر", "مود"), ("modd", "mod"),
    ("un mod", "unmod"), ("un vip", "unvip"),
    ("صفّر", "صفر"), ("ريسيت", "ريست"), ("re set", "reset"),
    ("ايموجى", "ايموجي"), ("إيموجي", "ايموجي"), ("ايموشي", "ايموجي"), ("سؤآل", "سؤال"), ("سوءال", "سؤال"), ("حرووف", "حروف"),
    ("دئايق", "دقايق"), ("دقائق", "دقايق"), ("دقيقة", "دقيقه"), ("ربع ساعة", "ربع ساعه"), ("نص ساعة", "نص ساعه"),
    ("كانسل", "كنسل"), ("كنسّل", "كنسل"), ("كنسللها", "كنسلها"),
    ("طايم اوت", "تايم اوت"), ("تايم اوط", "تايم اوت"), ("تايم آت", "تايم اوت"), ("تايم اووت", "تايم اوت"), ("تايمز اوت", "تايم اوت"),
    ("فيآيبي", "vip"), ("في اي بيه", "vip"), ("في آي پي", "vip"), ("ڤي آي پي", "vip"), ("في آي بيز", "vip"),
    ("مودريتورز", "مود"), ("موديريتر", "مود"), ("مود ريتر", "مود"),
    ("time outs", "timeout"), ("timeouts", "timeout"), ("timed-out", "timeout"), ("time-out", "timeout"),
    ("un-ban", "unban"), ("un-mod", "unmod"), ("un-vip", "unvip"), ("de-mod", "demod"), ("v.i.p.", "vip"), ("vee eye pee", "vip"),
    ("moderater", "moderator"), ("moderators", "moderator"), ("re-set", "reset"),
    ("ايموجيه", "ايموجي"), ("ايموجيز", "ايموجي"), ("حروووف", "حروف"), ("لغزز", "لغز"), ("ترجمي", "ترجم"),
    ("دقايء", "دقايق"), ("ديقيقه", "دقيقه"), ("ساعا", "ساعه"), ("ثواني", "ثانيه"),
]
FIXES = []           # [{"heard": "...", "to": "..."}]: yours and the learned ones (set by core/voice.py)


def _fix_list(extra=None):
    """(heard words, right spelling, built in?): yours and learned ones first (they win), then the built-in ones."""
    out, seen = [], set()
    mine = [(f.get("heard"), f.get("to"), False) for f in (extra if extra is not None else FIXES) if isinstance(f, dict)]
    for h, to, built in mine + [(h, to, True) for h, to in BUILTIN_FIXES]:
        h = norm(h)
        if h and to and h != norm(to) and h not in seen:
            seen.add(h)
            out.append((h.split(), str(to), built))
    return sorted(out, key=lambda x: len(x[0]), reverse=True)     # the longest first: «سامي قيمر» before «سامي»


BUILTIN_SPAN = 4      # built-in fixes only touch the first words (the command word), never a title or a message


def apply_fixes(text: str, extra=None, builtins: bool = True) -> str:
    """Puts the right spelling in place of what was heard wrong, whole words only (Arabic letters compared the easy way:
    أ/ا, ة/ه, ى/ي, no tashkeel). The rest of the sentence stays exactly as said."""
    fixes = _fix_list(extra)
    if not fixes or not text:
        return text
    words = str(text).split()
    keys = [norm(w) for w in words]
    out, i = [], 0
    while i < len(words):
        for h, to, built in fixes:
            n = len(h)
            if (not built or (builtins and i < BUILTIN_SPAN)) and keys[i:i + n] == h:
                out.append(to)
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


_FREE_TEXT = [rx for act, pats in _LEADS if act in ("say", "title", "setgame") for rx in pats]


def parse(text: str):
    t0 = _unfill(norm(text))           # your own words (say / title / game): only your fixes, never the built-in ones
    text = apply_fixes(text, builtins=not any(rx.match(t0) for rx in _FREE_TEXT))
    t = _unfill(norm(text))
    if not t:
        return None
    t = fix_words(t)
    words = t.split()
    if t in UNDO:
        return {"act": "undo"}
    m = re.match(r"^(?:رجع|خل|خلي|حط)(?: عداد)? (.+?) (?:ل|الى |الي |علي |على )?صفر$", t)
    if m:                                              # «رجع الموتات صفر», «خل الموتات صفر»
        return {"act": "reset", "what": m.group(1)}
    if words[0] in _ADD_W or words[0] in _SUB_W or (len(words) >= 2 and (words[1] in _ADD_W or words[1] in _SUB_W)) \
            or re.match(r"^(?:set|حط|خل|خلي|غير) \S+ (?:to |على |الى |ل |يصير |يكون )?\S+$", t) and (words[-1].isdigit() or _num(words[-1]) is not None):
        out = _count_op(t)                             # 1.18.0: counters + / − / set
        if out:
            return out
    if len(words) > 1 and words[0] == "لا" and words[1] in ("تتجاهل", "تطنش", "تجاهل"):     # «لا تتجاهل سامي»
        return {"act": "unignore", "who": _who(" ".join(words[2:]))} if words[2:] else None
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
            if out and out.get("who"):
                out["who"] = _who(out["who"])
            if out and act == "say":
                msg = said_after(text, t, m.end())
                out["text"] = punct(msg) if msg else punct(out["text"])
                return out if out["text"] else None
            if out:
                if out.get("reply"):                   # the reply as it was said (capitals, ى, punctuation), not simplified
                    k = len(out["reply"].split())
                    said = [w for w in str(text).split() if norm(w)]
                    if k and len(said) >= k:
                        out["reply"] = " ".join(said[-k:]).rstrip(".。")
                return out
    return _anywhere(t)


def said_after(original: str, t: str, end: int) -> str:
    """The words after the command word, exactly as said (capitals, ى, punctuation, and words like «الحين» that are
    dropped elsewhere). `t` is the simplified sentence and `end` where its command word ends."""
    full = norm(original)
    core = _unfill(full)
    skip = len(full[:max(0, full.find(core))].split()) + len(t[:end].split())
    out, n = [], 0
    for w in str(original or "").split():
        if n >= skip:
            out.append(w)
        elif norm(w):
            n += 1
    msg = " ".join(out).strip()
    return msg[:-1].rstrip() if msg.endswith((".", "。")) and not msg.endswith("..") else msg


_BANG = {"تعجب", "exclamation", "exclamationmark", "exclamationpoint"}
_QUES = {"استفهام", "questionmark"}
_MARK = {"علامه", "علامة", "mark", "point"}


def punct(msg: str) -> str:
    """«تعجب» → !   «استفهام» / «علامة استفهام» → ؟ (? after an English word), "exclamation mark" → !, "question mark" → ?
    The mark sticks to the word before it, so «هلا والله تعجب» is sent as «هلا والله!»; said first, it sticks to the word
    after it: «تعجب when» → !when."""
    words = str(msg or "").split()
    out, i, lead = [], 0, ""
    while i < len(words):
        n = norm(words[i]).replace(" ", "")
        nxt = norm(words[i + 1]).replace(" ", "") if i + 1 < len(words) else ""
        two = n + nxt
        mark, used = None, 1
        if n in _MARK and (nxt in _BANG or nxt in _QUES):        # «علامة تعجب», «علامة استفهام»
            mark, used = ("!" if nxt in _BANG else "?"), 2
        elif two in _BANG or two in _QUES:                        # "exclamation mark", "question mark"
            mark, used = ("!" if two in _BANG else "?"), 2
        elif n in _BANG or n in _QUES:
            mark = "!" if n in _BANG else "?"
        if mark:
            if out and not lead:                                  # after a word: «when استفهام» → when?
                if mark == "?" and re.search(r"[\u0600-\u06FF]", out[-1]):
                    mark = "؟"
                out[-1] = out[-1].rstrip(".,،") + mark
            else:                                                 # at the start: «تعجب when» → !when (sticks to the next word)
                lead += mark
            i += used
            continue
        w = words[i]
        if lead:
            if "?" in lead and re.search(r"[\u0600-\u06FF]", w):
                lead = lead.replace("?", "؟")
            w, lead = lead + w, ""
        out.append(w)
        i += 1
    if lead:                                                      # only marks were said
        out.append(lead.replace("?", "؟") if not out or re.search(r"[\u0600-\u06FF]", out[-1]) else lead)
    return " ".join(out)[:500]


def _who(name: str) -> str:
    w = [x for x in name.split() if x not in _DROP]
    if w and len(w[0]) > 4 and w[0].startswith("لل"):
        w[0] = w[0][2:]                               # «للسبام» (ل + ال) → «سبام»
    elif w and len(w[0]) > 3 and w[0].startswith("ل") and not w[0].startswith("ال"):
        w[0] = w[0][1:]                               # «لسامي» → «سامي»
    if w and len(w[0]) > 4 and w[0].startswith("ال"):
        w[0] = w[0][2:]                               # «السبام» → «سبام»
    return " ".join(w)


def _anywhere(t: str):
    """The action word somewhere else in the sentence: «سامي تايم اوت عشر دقايق», "give sami a timeout"."""
    for act, keys in ANYWHERE:
        for k in keys:
            m = re.search(r"(?:^|\s)" + re.escape(norm(k)) + r"(?:\s|$)", t)
            if not m:
                continue
            rest = (t[:m.start()] + " " + t[m.end():]).split()
            out = _finish(act, " ".join(rest))
            if out and out.get("who"):
                out["who"] = _who(out["who"])
                if out["who"]:
                    return out
    return None


def _strip(rest: str, *drop) -> str:
    w = rest.split()
    while w and w[0] in drop:
        w = w[1:]
    return " ".join(w)


def _finish(act: str, rest: str):
    if act in ("hidechat", "showchat"):
        return {"act": act} if set(rest.split()) <= {"now", "الحين", "please", "on", "stream", "box", "عن", "من", "على", "علي", "في", "البث"} else None
    if act == "clear":
        return {"act": "clear"} if rest.split() == [] or set(rest.split()) <= {"كله", "كامل", "now", "الحين", "please"} else None
    if act in ("ignore", "unignore"):
        who = " ".join(w for w in rest.split() if w not in ("him", "her", "the", "user", "عن", "من", "ل", "على"))
        return {"act": act, "who": who} if who else None
    if act == "runcmd":
        name = re.sub(r"\s+command$", "", _strip(rest, "called", "named", "the", "اسمه", "حق")).lstrip("!")
        return {"act": "runcmd", "name": name} if name else None
    if act == "count":
        return _count(rest)
    if act in ("timeout", "ban", "unban", "vip", "unvip", "mod", "unmod"):
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
        words = [w for w in words if w not in ("for", "لمده", "مده", "ل", "the", "user", "ذا", "هذا", "اللي", "يوزر", "a", "an",
                                               "يصير", "يكون", "صار", "خله", "خليه", "to", "as", "be")
                 and not (act in ("vip", "unvip", "mod", "unmod") and w in ("make", "خل", "خلي", "سو", "سوي", "him", "her", "from"))]
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
    if act == "editcmd":
        words = _strip(rest, "called", "named").split()
        if not words:
            return None
        reply = " ".join(words[1:])
        for sep in ("to say ", "to ", "so it says ", "says ", "reply ", "with ", "الى ", "الي ", "ل ", "يقول ", "رده ", "الرد ", "خله يقول ", "خليه يقول "):
            if reply.startswith(sep):
                reply = reply[len(sep):]
                break
        return {"act": "editcmd", "name": words[0], "reply": reply.strip()}
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
    if act == "say":
        return {"act": "say", "text": rest} if rest else None
    if act == "game":
        rest = _GAME_LEAD.sub("", rest + " ").strip() or rest
        if rest in {norm(x) for x in ("random", "random game", "any game", "a random game", "عشوائية", "اي لعبة", "لعبة عشوائية", "أي شي", "اي وحده", "عشوائية", "عشوائي",
                                         "اي شي", "any", "random one", "anything", "اي لعبه", "على كيفك", "انت اختار")}:
            return {"act": "game", "game": "random"}
        g = game_of(rest)
        return {"act": "game", "game": g} if g else None
    return None


_ADD_W = {"زيد", "زود", "ضيف", "اضف", "زد", "كثر", "add", "plus", "increase", "up"}
_SUB_W = {"نقص", "نزل", "انقص", "قلل", "ناقص", "subtract", "minus", "decrease", "lower"}


def _count(rest: str, op: str = ""):
    """1.18.0: «زيد الموتات», «زيد الموتات ثلاث», «نقص الموتات», «حط الموتات 50», "deaths plus one", "add 2 to deaths",
    "set deaths to 50". {act: count, what, op, n}"""
    words = [w for w in rest.split() if w not in ("to", "from", "the", "counter", "عداد", "العداد", "على", "الى", "ل", "من",
                                                   "يصير", "يكون", "by", "واحد") or w == "واحد" and False]
    n = None
    keep = []
    for w in words:
        v = _num(w) if not w.isdigit() else int(w)
        if v is not None and n is None:
            n = v
        else:
            keep.append(w)
    what = " ".join(keep).strip()
    if not what:
        return None
    return {"act": "count", "what": what, "op": op or "add", "n": n}


def _count_op(t: str):
    """The counter sentences in any order: "deaths plus one", «الموتات زيد», "set deaths to 50"."""
    w = t.split()
    if not w:
        return None
    if w[0] in ("set", "حط", "خل", "خلي", "غير") and len(w) >= 3 and (w[-1].isdigit() or _num(w[-1]) is not None):
        out = _count(" ".join(w[1:]), "set")
        return out if out and out["n"] is not None else None
    for i, x in enumerate(w):
        if x in _ADD_W or x in _SUB_W:
            out = _count(" ".join(w[:i] + w[i + 1:]), "add" if x in _ADD_W else "sub")
            if out:
                return out
    return None


# ---------- the nearest word: when the speech engine heard a word slightly wrong ----------

VOCAB = ["timeout", "ban", "unban", "reset", "start", "play", "change", "title", "game", "cancel", "undo",
         "تايماوت", "تايم", "اوت", "ميوت", "بان", "باند", "احظر", "حظر", "فك", "صفر", "تصفير", "ريست", "ابدا", "شغل", "العب",
         "يلا", "غير", "العنوان", "اللعبه", "كنسل", "تراجع", "الغي", "دقيقه", "دقايق", "دقيقتين", "ساعه", "ثانيه",
         "minutes", "minute", "seconds", "hour",
         "مشرف", "مودريتر", "اشراف", "شيل", "سحب", "moderator", "unmod", "unvip",
         "زيد", "زود", "نقص", "تجاهل", "طنش", "امسح", "الشات", "نفذ", "increase", "decrease", "ignore", "unignore", "clear", "minus", "plus"]
_SHORT_OK = {"بان", "فك", "صفر", "اوت", "ban", "يلا", "غير"}      # (short words: only exact, never guessed)


def _near(w: str):
    if w in VOCAB or len(w) < 4 or w.isdigit():
        return None
    m = difflib.get_close_matches(w, [v for v in VOCAB if v not in _SHORT_OK], n=1, cutoff=0.85)
    if m:                                                  # «تايمات» → تايماوت
        return m[0]
    for v in sorted(VOCAB, key=len, reverse=True):         # «صفرلي» → صفر, «ابدالي» → ابدا
        if len(v) >= 3 and (v not in _SHORT_OK or v == "صفر") and w.startswith(v) and len(w) - len(v) <= 3:
            return v
    m = difflib.get_close_matches(w, [v for v in VOCAB if v not in _SHORT_OK], n=1, cutoff=0.8)
    return m[0] if m else None


def fix_words(t: str) -> str:
    """Puts the nearest command word in place of one that was heard a little wrong («تايمات» → تايماوت, "tame out" →
    timeout, «صفّرلي» → صفر). Only the first words of a sentence (where the command word is) are touched, so names and
    replies stay exactly as they were said."""
    w = t.split()
    out, i = [], 0
    while i < len(w):
        if i < 3 and i + 1 < len(w):                       # two words heard as one: "tame out" → timeout
            joined = _near(w[i] + w[i + 1])
            if joined in ("timeout", "تايماوت") and w[i] not in VOCAB:
                out.append(joined)
                i += 2
                continue
        fixed = _near(w[i]) if i < 3 else None
        out.append(fixed or w[i])
        i += 1
    return " ".join(out)


_GAME_LEAD = re.compile(r"^(?:(?:the|a|an|game|games|round|a round|round of|game of|of|some|اللعبه|لعبه|لعبة|جوله|جولة|"
                        r"جولتين|لنا|لي|معنا|معانا|ب|في|من)\s+)+")


def game_of(text: str, extra=None):
    """Which mini game was named: the exact name anywhere in what was said (the longest name first, so «عكس الكلمة» is
    Opposites, not Backwards), then the nearest name to a word or two («حرووف», "trivial", «الدخيلل»), then the same in
    Latin letters (when the engine wrote «سلم» as "sullam")."""
    t = _GAME_LEAD.sub("", norm(text) + " ").strip()
    if not t:
        return None
    pool = _game_pool(extra)
    words = t.split()
    variants = []
    for w in words:
        variants.append(w)
        for pre in ("وال", "بال", "لل", "ال", "ب", "و"):          # «بالحروف», «للدخيل», «الاضداد»
            if w.startswith(pre) and len(w) - len(pre) >= 2:
                variants.append(w[len(pre):])
    padded = " " + t + " "
    for name in sorted(pool, key=len, reverse=True):              # 1. the exact name, anywhere
        if " " + name + " " in padded or (" " not in name and name in variants):
            return pool[name]
    names = [n for n in pool if len(n) >= 3]
    tries = [" ".join(words[:3]), " ".join(words[:2])] + variants[:6]
    for cand in tries:                                            # 2. the nearest name
        if len(cand) < 3:
            continue
        m = difflib.get_close_matches(cand, names, n=1, cutoff=0.78)
        if m:
            return pool[m[0]]
    lat = {}                                                      # 3. the same, in Latin letters
    for n, key in pool.items():
        lat.setdefault(latin(n).replace(" ", ""), key)
    for cand in tries[:2] + variants[:4]:
        if not re.fullmatch(r"[a-z ]+", cand):                   # only for words the engine wrote in English letters
            continue
        c = cand.replace(" ", "")
        if len(c) < 4:
            continue
        m = difflib.get_close_matches(c, [x for x in lat if len(x) >= 3], n=1, cutoff=0.8)
        if m:
            return lat[m[0]]
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
    s = " ".join(str(_AR_NUM[w]) if w in _AR_NUM else w for w in norm(s).split())     # «سامي تسعه» → sami 9
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
        scored = [x for x in scored if x[0] >= best - 0.15]
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
        else:                            # 1.18.0: Arabic letters said for an English name («ديسكورد» → !discord)
            lw, lb = _vowelless(re.sub(r"[^a-z0-9]", "", latin(want).replace("k", "c").replace("w", ""))), \
                _vowelless(re.sub(r"[^a-z0-9]", "", latin(b).replace("k", "c").replace("w", "")))
            if lw and lb and len(lw) >= 3:
                r = max(r, 0.9 * difflib.SequenceMatcher(None, lw, lb).ratio())
        if r > score:
            best, score = n, r
    return best if score >= cutoff else None


# 1.18.0: the built-in commands by easy spoken names («شغل امر كوماندات» = !cmlist, «شغل امر برنامج» = app?)
BUILTIN_SPOKEN = {
    "commands": ("cmlist", "cm list", "commands", "command list", "commands list", "my commands", "كوماندات", "الكوماندات",
                 "كوماند", "اوامر", "الاوامر", "قائمه الاوامر", "قايمه الاوامر", "لسته الاوامر", "سي ام ليست"),
    "app": ("app", "the app", "برنامج", "البرنامج", "تطبيق", "التطبيق", "ابلكيشن"),
    "title": ("title", "settitle", "stream title", "عنوان", "العنوان", "عنوان البث", "تايتل", "التايتل"),
    "game": ("game", "setgame", "current game", "لعبه", "اللعبه", "قيم", "القيم", "اللعبه الحاليه"),
}
# Arabic letters said by name, for one-letter commands («شين» = !ش, «حا حا» = !حح)
_LETTER_NAMES = {"الف": "ا", "با": "ب", "باء": "ب", "تا": "ت", "تاء": "ت", "ثا": "ث", "ثاء": "ث", "جيم": "ج", "حا": "ح",
                 "حاء": "ح", "خا": "خ", "خاء": "خ", "دال": "د", "ذال": "ذ", "را": "ر", "راء": "ر", "زاي": "ز", "زين": "ز",
                 "سين": "س", "شين": "ش", "صاد": "ص", "ضاد": "ض", "طا": "ط", "طاء": "ط", "ظا": "ظ", "ظاء": "ظ", "عين": "ع",
                 "غين": "غ", "فا": "ف", "فاء": "ف", "قاف": "ق", "كاف": "ك", "لام": "ل", "ميم": "م", "نون": "ن", "ها": "ه",
                 "هاء": "ه", "واو": "و", "يا": "ي", "ياء": "ي"}


def _spelled(said: str) -> str:
    """«شين» → «ش», «حا حا» → «حح»; "" when it isn't letters said by name."""
    w = norm(said).split()
    return "".join(_LETTER_NAMES[x] for x in w) if w and all(x in _LETTER_NAMES for x in w) else ""


def match_command(said: str, customs: dict, builtins: list):
    """1.18.0 «شغل امر ...»: which command was meant. customs = {name: response} (your commands), builtins = the built-in
    keys that are on. Returns ("custom", name), ("builtin", key) or None. In order: your command by its exact name (also
    spelled letter by letter), a built-in by an easy name («كوماندات», «برنامج»), a short name the word starts with
    («الدسكور» → !دس), the closest name, and last a short command whose reply has the word («الشكر» → !ش: «شكرا ع الفولو»)."""
    want = _bare(said)
    if not want:
        return None
    alt = _spelled(said)
    for n in customs:
        if _bare(n) and _bare(n) in (want, alt):
            return ("custom", n)
    spoken = {}
    for k in builtins:
        for a in BUILTIN_SPOKEN.get(k, ()):
            spoken[_bare(a)] = k
    if want in spoken:
        return ("builtin", spoken[want])
    w0 = want.replace(" ", "")
    pre = [n for n in customs if len(_bare(n)) >= 2 and w0.startswith(_bare(n).replace(" ", "")) and len(w0) - len(_bare(n)) <= 4]
    if pre:
        return ("custom", max(pre, key=lambda n: len(_bare(n))))
    hit = match_name(said, list(customs) + list(spoken))
    if hit in customs:
        return ("custom", hit)
    if hit:
        return ("builtin", spoken[hit])
    if len(w0) >= 3:
        found = [n for n, r in customs.items() if len(_bare(n)) <= 3 and _bare(n)[:1] == w0[:1]
                 and any(x.startswith(w0[:3]) for x in norm(r).split())]
        if len(found) == 1:
            return ("custom", found[0])
    return None


def command_name(said: str) -> str:
    """The name of a new command said out loud: "socials" → "!socials", «روابط» → «!روابط»."""
    w = norm(said).split()
    return ("!" + w[0].lstrip("!")) if w else ""
