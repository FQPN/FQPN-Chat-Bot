"""Pin first message (1.13.0): a command type. The first viewer whose message starts with one of the trigger words
("first", "اول", "1", ...) gets that message pinned in chat by Twitch, and can get a reply ("$(user) is first!").

A command of this type looks like:
    {"action": "pinfirst", "words": ["first", "اول", "1"], "pin_secs": 0, "block_bad": True, "once": True,
     "reply_on": False, "response": "$(user) is first!", "permission": "everyone", "cooldown": 0, "enabled": True, "aliases": []}
pin_secs 0 = until the stream ends (Twitch allows 30 seconds to 30 minutes, or until the end).

Who won is kept in the store section "first_state" ({command name: {"stream", "winner", "user", "streak"}}), so an app
restart or a short drop during a stream never gives the win away twice. $(firststreak) = how many streams in a row
this viewer was first (it only counts each stream's FIRST winner)."""

import re
import unicodedata

ACTION = "pinfirst"
PIN_CHOICES = (0, 30, 60, 300, 600, 1800)      # 0 = until the stream ends
MAX_WORDS = 10
WORD_MAX = 25
DEFAULT_REPLY = "$(user) is first!"
REPLAY_GAP = 30          # with "Only once per stream" off: at most one pin every 30 s (Twitch's shortest pin)

_TASHKEEL = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "ک": "ك", "ی": "ي"})


def norm(word: str) -> str:
    """One word, ready to compare: lower case, one form of each Arabic letter, no tashkeel, no punctuation or symbols,
    repeated letters once ("Firsttt!!" -> "first", "أوّل" -> "اول")."""
    t = unicodedata.normalize("NFKC", str(word or "")).casefold()
    t = _TASHKEEL.sub("", t).translate(_AR)
    t = "".join(c for c in t if c.isalnum())
    return re.sub(r"(.)\1+", r"\1", t)


def clean_words(raw) -> list:
    """The trigger words as the page saves them: trimmed, no empty ones, no two that mean the same, at most 10."""
    out, seen = [], set()
    for w in raw or []:
        w = " ".join(str(w).split())[:WORD_MAX]
        key = " ".join(norm(x) for x in w.split())
        if not key.strip() or key in seen:
            continue
        seen.add(key)
        out.append(w)
    return out[:MAX_WORDS]


def matches(text: str, words) -> bool:
    """The message starts with one of the trigger words (a word of its own: "first!" and "FIRST hi" count, "firstly" doesn't)."""
    msg = [n for n in (norm(w) for w in str(text or "").split()) if n]
    if not msg:
        return False
    for trig in words or []:
        want = [n for n in (norm(w) for w in str(trig).split()) if n]
        if want and msg[:len(want)] == want:
            return True
    return False


def pin_commands(commands: dict) -> list:
    """(name, command) of every switched-on Pin first message command."""
    return [(n, c) for n, c in sorted((commands or {}).items())
            if isinstance(c, dict) and c.get("action") == ACTION and c.get("enabled", True) is not False]


def claim(state: dict, stream_id, login: str, user: str, once: bool = True, now: float = 0.0):
    """Someone wrote a trigger word in this stream. Returns (new state, streak) when they win, or None when the win is
    already taken (once per stream) or the last pin was less than 30 s ago (once per stream off)."""
    st = dict(state or {})
    if st.get("stream") == stream_id and st.get("winner"):
        if once or now - float(st.get("at") or 0) < REPLAY_GAP:
            return None
        st["at"] = now
        return st, int(st.get("streak") or 0) if st.get("winner") == login else 0     # a later pin: the streak stays the first winner's
    streak = int(st.get("streak") or 0) + 1 if st.get("winner") == login else 1
    return {"stream": stream_id, "winner": login, "user": user, "streak": streak, "at": now}, streak


def streak_of(states: dict, login: str) -> int:
    """$(firststreak) for this viewer: their streak if they are the latest first winner of a Pin first message command."""
    best = 0
    for st in (states or {}).values():
        if isinstance(st, dict) and st.get("winner") == login:
            best = max(best, int(st.get("streak") or 0))
    return best
