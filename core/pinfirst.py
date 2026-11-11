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
WINDOW_MIN = 5           # 1.14.0: only in the first 5 minutes of the stream; nobody by then = the streak is broken
WINDOW_CHOICES = (0, 1, 2, 3, 5, 10, 15, 30)     # minutes; 0 = any time in the stream

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


def matches(text: str, words, own_names=()) -> bool:
    """The message starts with one of the trigger words (a word of its own: "first!" and "FIRST hi" count, "firstly" doesn't).
    1.14.0: never a command or a question: "!first", "!اول", "first?", "اول؟", or a message that is one of the channel's own
    command names (like a command «اول؟» that shows the streak)."""
    raw = str(text or "").strip()
    if not raw or raw[0] in "!！":
        return False
    first = raw.split()[0]
    if first.rstrip("!.،,~") and first.rstrip("!.،,~")[-1] in "?؟":
        return False
    names = {str(n).strip().casefold() for n in own_names or ()}
    if raw.casefold() in names or first.casefold() in names:
        return False
    msg = [n for n in (norm(w) for w in raw.split()) if n]
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
    peaks = dict(st.get("peaks") or {})          # 1.14.0: each viewer's best streak ever ($(firststreakpeak))
    if st.get("stream") == stream_id and st.get("winner"):
        if once or now - float(st.get("at") or 0) < REPLAY_GAP:
            return None
        st["at"] = now
        return st, int(st.get("streak") or 0) if st.get("winner") == login else 0     # a later pin: the streak stays the first winner's
    streak = int(st.get("streak") or 0) + 1 if st.get("winner") == login else 1
    peaks[login] = max(int(peaks.get(login) or 0), streak)
    counts = dict(st.get("counts") or {})        # 1.18.0 (Twitch panel): how many streams each viewer was first in
    counts[login] = int(counts.get(login) or 0) + 1
    names = dict(st.get("names") or {})          # and the name they show with
    names[login] = str(user or login)[:40]
    return {"stream": stream_id, "winner": login, "user": user, "streak": streak, "at": now, "peaks": peaks, "counts": counts, "names": names}, streak


def missed(state: dict, stream_id) -> dict:
    """1.14.0: the first minutes of this stream passed and nobody was first: the streak is broken (best streaks are kept).
    Returns the new state, or None when this stream already has a winner or was already marked."""
    st = dict(state or {})
    if st.get("stream") == stream_id:
        return None
    return {"stream": stream_id, "winner": "", "user": "", "streak": 0, "at": 0, "peaks": dict(st.get("peaks") or {}),
            "counts": dict(st.get("counts") or {}), "names": dict(st.get("names") or {})}


def peak_of(states: dict, login: str) -> int:
    """$(firststreakpeak): this viewer's best streak ever (any Pin first message command)."""
    best = 0
    for st in (states or {}).values():
        if isinstance(st, dict):
            best = max(best, int((st.get("peaks") or {}).get(login) or 0))
    return max(best, streak_of(states, login))


def streak_of(states: dict, login: str) -> int:
    """$(firststreak) for this viewer: their streak if they are the latest first winner of a Pin first message command."""
    best = 0
    for st in (states or {}).values():
        if isinstance(st, dict) and st.get("winner") == login:
            best = max(best, int(st.get("streak") or 0))
    return best


def boards(states: dict, n: int = 10) -> dict:
    """1.18.0 (Twitch panel): First in chat, all Pin first message commands together.
    {"peak": [(login, name, best streak)], "count": [(login, name, streams first)], "now": (login, name, streak) or None}.
    "count" only knows the firsts since 1.18.0 (before that the app kept the streaks, not how many times)."""
    peak, count, names, now = {}, {}, {}, None
    for st in (states or {}).values():
        if not isinstance(st, dict):
            continue
        names.update({k: str(v) for k, v in (st.get("names") or {}).items()})
        for k, v in (st.get("peaks") or {}).items():
            peak[k] = max(peak.get(k, 0), int(v or 0))
        for k, v in (st.get("counts") or {}).items():
            count[k] = count.get(k, 0) + int(v or 0)
        if st.get("winner") and int(st.get("streak") or 0) > 0 and (now is None or int(st["streak"]) > now[2]):
            now = (st["winner"], str(st.get("user") or st["winner"]), int(st["streak"]))
            names.setdefault(st["winner"], now[1])
    def rows(d):
        r = [(k, names.get(k) or k, v) for k, v in d.items() if v > 0]
        r.sort(key=lambda x: (-x[2], x[1].lower()))
        return r[:n]
    return {"peak": rows(peak), "count": rows(count), "now": now}
