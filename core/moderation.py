"""Chat moderation filters: bad words (Arabic + English, hard to dodge), links, excess caps, emotes, symbols and repetitions.

Pure functions plus one small Moderator class that remembers strikes and recent messages, so everything can be tested without
Twitch. The bot asks check() about every message and then carries out what it says (delete, warn, timeout)."""
import re
import time
import unicodedata

FILTERS = ("badwords", "links", "caps", "emotes", "symbols", "repeats")
ACTIONS = ("delete", "steps")          # delete only, or warn then timeouts (steps)
STRIKE_RESET = 3600                    # a clean hour forgets earlier strikes

TRUSTED_DEFAULT = ["twitch.tv", "clips.twitch.tv", "youtube.com", "youtu.be", "x.com", "twitter.com", "instagram.com",
                   "tiktok.com", "discord.gg", "discord.com"]
COMMON = {"enabled": False, "exempt_vip": True, "exempt_sub": False, "action": "steps", "steps": [0, 60, 600], "warn_text": ""}


def defaults() -> dict:
    d = {"shared_chat": False}
    d["badwords"] = dict(COMMON, words=[], allowed=[])
    d["links"] = dict(COMMON, trusted=list(TRUSTED_DEFAULT))
    d["caps"] = dict(COMMON, percent=70, min_length=15)
    d["emotes"] = dict(COMMON, max=7)
    d["symbols"] = dict(COMMON, percent=50, min_length=15)
    d["repeats"] = dict(COMMON, word_repeats=6, same_message=3)
    return d


# ------------------------------------------------------------------------------------------------ text normalising
_TASHKEEL = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")     # harakat, small marks and tatweel (ـ)
_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "ک": "ك", "ی": "ي"})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})          # ("!" is left alone: it starts commands)
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def _base(text: str) -> str:
    """Lower case, Arabic letter forms unified, tashkeel and tatweel removed, look-alike digits/symbols turned into letters,
    and other accents dropped (é -> e)."""
    t = unicodedata.normalize("NFKC", str(text)).casefold()
    t = _TASHKEEL.sub("", t).translate(_AR).translate(_LEET)
    t = "".join(c for c in unicodedata.normalize("NFD", t) if not (unicodedata.category(c) == "Mn" and not "\u0600" <= c <= "\u06ff"))
    return t


def _squeeze(word: str) -> str:
    """Repeated letters count once: baaaad -> bad, كلببببب -> كلب (applied to both sides, so "good" still matches "good")."""
    return re.sub(r"(.)\1+", r"\1", word)


def tokens(text: str) -> list[str]:
    """The words of a message, ready to compare. Letters written one by one ("b a d", "b.a.d", "ح.م.ا.ر") are joined back
    into one word."""
    raw = re.findall(r"[^\W_]+", _base(text), re.UNICODE)
    out, run = [], []
    for w in raw:
        if len(w) == 1 and _LETTER.match(w):
            run.append(w)
            continue
        if len(run) >= 3:
            out.append("".join(run))
        else:
            out.extend(run)
        run = []
        out.append(w)
    out.extend(["".join(run)] if len(run) >= 3 else run)
    return [_squeeze(w) for w in out if w]


def squashed(text: str) -> str:
    """Only the letters, all together: for words that are never innocent ("anywhere" words)."""
    return _squeeze("".join(_LETTER.findall(_base(text))))


def bad_word(text: str, words: list, allowed: list) -> str | None:
    """The first listed word or phrase the message contains, or None. Each entry: {"w": "...", "anywhere": False}.
    By default a word matches only as a whole word ("ass" does not fire on "class"); "anywhere" also finds it inside words."""
    toks = tokens(text)
    ok_words = {t for a in allowed for t in tokens(a)}
    toks_checked = [t for t in toks if t not in ok_words]
    flat = squashed(" ".join(toks_checked))
    for e in words:
        w = e.get("w", "") if isinstance(e, dict) else str(e)
        want = tokens(w)
        if not want:
            continue
        if isinstance(e, dict) and e.get("anywhere"):
            if squashed(w) and squashed(w) in flat:
                return w
            continue
        n = len(want)
        for i in range(len(toks_checked) - n + 1):
            if toks_checked[i:i + n] == want:
                return w
    return None


# ------------------------------------------------------------------------------------------------ links
_TLDS = ("com net org io gg tv co me xyz ly app dev info biz ru sa ae uk de link site online store shop live us ca fr tk ml ga cf "
         "gq top club fun vip cc be to sh lol art pro page eu nl it es pl br in jp cn au ch se no fi dk at cz tr ir eg ma kw qa om "
         "bh jo iq lb sy ye ps su ws am fm gl im is ly mx nz ph pk sg tw ua vn za ai tech space website online icu cyou bond "
         "click download stream gift money win bet casino porn sex xxx cam chat media news social video").split()
_TLD_RE = "|".join(sorted(set(_TLDS), key=len, reverse=True))
_DOTWORD = re.compile(r"\s*(?:\(\s*dot\s*\)|\[\s*dot\s*\]|\{\s*dot\s*\}|\bdot\b)\s*", re.IGNORECASE)
_SPACED_DOT = re.compile(r"(?<=[a-z0-9])\s*\.\s*(?=(?:" + _TLD_RE + r")\b)", re.IGNORECASE)     # "spam . com" (a comma never counts as a dot)
_LINK = re.compile(r"(?:https?://)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:" + _TLD_RE + r"))(?![a-z0-9-])(?:[:/?#]\S*)?", re.IGNORECASE)
_IP = re.compile(r"\b(?:https?://)?(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?\b")


def links(text: str) -> list[str]:
    """Every website a message points to (just the domain), including hidden ones: "spam . com", "spam(dot)com"."""
    t = _DOTWORD.sub(".", str(text))
    t = _SPACED_DOT.sub(".", t)
    found = [m.group(1).lower().rstrip(".") for m in _LINK.finditer(t)]
    found += [m.group(1) for m in _IP.finditer(t)]
    return found


def trusted(domain: str, trusted_list: list) -> bool:
    d = domain.lower().removeprefix("www.")
    for t in trusted_list:
        t = str(t).lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
        if t and (d == t or d.endswith("." + t)):
            return True
    return False


def bad_link(text: str, trusted_list: list) -> str | None:
    for d in links(text):
        if not trusted(d, trusted_list):
            return d
    return None


# ------------------------------------------------------------------------------------------------ caps, emotes, symbols, repeats
def too_many_caps(text: str, percent: int, min_length: int, skip_words=()) -> bool:
    words = [w for w in str(text).split() if w not in set(skip_words)]      # emote names like KEKW don't count
    letters = [c for c in "".join(words) if c.isalpha() and c.lower() != c.upper()]   # only letters that have a capital form
    if len(letters) < max(1, min_length):
        return False
    return sum(c.isupper() for c in letters) * 100 >= percent * len(letters)


def too_many_symbols(text: str, percent: int, min_length: int) -> bool:
    t = "".join(str(text).split())
    marks = sum(1 for c in t if unicodedata.category(c) in ("Mn", "Me") and not "\u0600" <= c <= "\u06ff")
    if marks >= 6:
        return True                                                          # g̷l̸i̶t̷c̶h / zalgo text
    if len(t) < max(1, min_length):
        return False
    sym = sum(1 for c in t if not c.isalnum() and unicodedata.category(c)[0] in "SPC" and c not in ".,!?'\"-:;()؟،")
    return sym * 100 >= percent * len(t)


def repeated_word(text: str, limit: int) -> bool:
    toks = tokens(text)
    return bool(toks) and max(toks.count(t) for t in set(toks)) >= max(2, limit)


# ------------------------------------------------------------------------------------------------ the moderator
class Moderator:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.strikes: dict = {}          # (filter, user_id) -> (count, last time)
        self.recent: dict = {}           # user_id -> [(time, normalised message)]

    def exempt(self, cfg: dict, roles: dict) -> bool:
        if roles.get("broadcaster") or roles.get("moderator"):
            return True
        return bool((cfg.get("exempt_vip") and roles.get("vip")) or (cfg.get("exempt_sub") and roles.get("subscriber")))

    def check(self, settings: dict, text: str, user_id: str, roles: dict, emotes: int = 0, emote_words=()):
        """(filter, detail) for the first filter the message breaks, or None. Remembers the message for the repetition filter."""
        now = self.clock()
        norm = " ".join(tokens(text))
        past = [(t, m) for t, m in self.recent.get(user_id, []) if now - t < 60]
        self.recent[user_id] = (past + [(now, norm)])[-10:]
        for f in FILTERS:
            cfg = settings.get(f) or {}
            if not cfg.get("enabled") or self.exempt(cfg, roles):
                continue
            hit = None
            if f == "badwords":
                hit = bad_word(text, cfg.get("words", []), cfg.get("allowed", []))
            elif f == "links":
                hit = bad_link(text, cfg.get("trusted", []))
            elif f == "caps":
                hit = "caps" if too_many_caps(text, cfg.get("percent", 70), cfg.get("min_length", 15), emote_words) else None
            elif f == "emotes":
                hit = str(emotes) if emotes > int(cfg.get("max", 7)) else None
            elif f == "symbols":
                hit = "symbols" if too_many_symbols(text, cfg.get("percent", 50), cfg.get("min_length", 15)) else None
            elif f == "repeats":
                if repeated_word(text, int(cfg.get("word_repeats", 6))):
                    hit = "words"
                elif norm and sum(1 for _, m in past if m == norm) + 1 >= int(cfg.get("same_message", 3)):
                    hit = "message"
            if hit:
                return f, hit
        return None

    def punishment(self, cfg: dict, filt: str, user_id: str) -> int | None:
        """What to do now: None = only delete; 0 = delete and warn; N = delete and time out for N seconds. Counts strikes."""
        if cfg.get("action", "steps") == "delete":
            return None
        steps = [int(s) for s in (cfg.get("steps") or [0])]
        now = self.clock()
        n, last = self.strikes.get((filt, user_id), (0, 0))
        if now - last > STRIKE_RESET:
            n = 0
        self.strikes[(filt, user_id)] = (n + 1, now)
        return steps[min(n, len(steps) - 1)]

# ------------------------------------------------------------------------------------------------ your mods' actions (Logs)
# Twitch's "channel.moderate" event. Read defensively: TwitchIO objects or Twitch's raw field names both work, and an action
# this code doesn't know becomes a plain row instead of an error.
_SIMPLE = {"clear", "slowoff", "followers", "followersoff", "emoteonly", "emoteonlyoff", "subscribers", "subscribersoff",
           "uniquechat", "uniquechatoff", "unraid"}


def _g(obj, *names):
    for n in names:
        v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
        if v is not None:
            return v
    return None


def _who(u):
    if u is None:
        return ""
    if isinstance(u, str):
        return u
    return str(_g(u, "display_name", "name", "user_name", "user_login", "login") or "")


def describe_action(payload, now=None):
    """{"name": "timeout:600", "user": target, "by": moderator, "text": reason or message, "shared": bool} or None."""
    action = str(_g(payload, "action") or "").lower()
    if not action:
        return None
    shared = action.startswith("shared_chat_")
    key = action.removeprefix("shared_chat_")
    sub = _g(payload, action, key) or {}
    by = _who(_g(payload, "moderator")) or str(_g(payload, "moderator_user_name", "moderator_user_login") or "")
    user = _who(_g(sub, "user")) or str(_g(sub, "user_name", "user_login") or "")
    name, text = key, ""
    if key in ("ban", "warn"):
        text = _g(sub, "reason") or ""
    elif key == "timeout":
        text = _g(sub, "reason") or ""
        ends = _g(sub, "expires_at", "ends_at")
        secs = 0
        try:
            if hasattr(ends, "timestamp"):
                secs = int(round(ends.timestamp() - (now if now is not None else time.time())))
            elif isinstance(ends, str):
                from datetime import datetime
                secs = int(round(datetime.fromisoformat(ends.replace("Z", "+00:00")).timestamp() - (now if now is not None else time.time())))
        except (ValueError, TypeError, OverflowError):
            secs = 0
        name = f"timeout:{max(secs, 0)}"
    elif key == "delete":
        text = _g(sub, "text", "message_body") or ""
    elif key == "slow":
        name = f"slow:{int(_g(sub, 'wait_time_seconds') or 0)}"
    elif key == "raid":
        user = user or _who(_g(sub, "user"))
    elif key in ("unban", "untimeout", "mod", "unmod", "vip", "unvip") or key in _SIMPLE:
        pass
    else:
        name = key                         # automod terms, unban requests, ... shown as "Moderation: <action>"
    return {"name": name, "user": user, "by": by, "text": str(text)[:300], "shared": shared}
