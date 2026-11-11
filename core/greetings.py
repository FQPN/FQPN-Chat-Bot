"""Greeting a chosen person once per stream. Pure functions, so they can be tested without Twitch.

The bot greets a person from the list the first time they write in chat during a stream, a few
seconds later, with one of their messages picked at random (never the same one twice in a row)."""

import random
import re

GREETING_DELAY = 3   # seconds between the person's first message and the greeting

# The app's developers, by permanent Twitch user ID (a name can change, the ID never does). To add someone, add their ID here.
DEVELOPERS = frozenset({
    "1299878164",    # 1asoom
    "754527671",     # fqpn_
})
DEVELOPER_GREETING = "حيوووووو بالمبرمج الاسطوري 🔥"
DEVELOPER_GREETINGS = {"1299878164": "يهلا وغلا ب اقوى مبرمجة 🔥"}      # 1.15.0 (owner): 1asoom's own; anyone else: the one above


def messages_for(greetings: dict, login: str) -> list[str]:
    """The messages to choose from for this person, or [] if they have none / greetings are off."""
    if not greetings.get("enabled", True):
        return []
    for item in greetings.get("users", []):
        if item.get("enabled", True) and str(item.get("user", "")).lower() == login:
            return [m for m in item.get("messages", []) if isinstance(m, str) and m.strip()]
    return []


def has_entry(greetings: dict, login: str) -> bool:
    """True when the channel put this person on its greetings list (switched on or off: either way it is the channel's choice)."""
    return any(str(item.get("user", "")).lower() == login for item in greetings.get("users", []))


def developer_messages(greetings: dict, login: str, user_id, owner_id) -> list[str]:
    """The default developer greeting, for a developer the channel has not set its own greeting for.
    Nothing when greetings are switched off, when it is the channel's own account, or when the channel has a greeting for them
    (their own greeting is then sent by messages_for, so nobody is greeted twice)."""
    uid = str(user_id or "")
    if uid not in DEVELOPERS or uid == str(owner_id or "") or not greetings.get("enabled", True) or has_entry(greetings, login):
        return []
    return [DEVELOPER_GREETINGS.get(uid, DEVELOPER_GREETING)]


def claim(greeted: dict, session: str, login: str, messages: list[str], rng=random):
    """Decides whether to greet `login` now. Returns (new_state, message or None).
    `session` identifies the current stream; a new stream starts the list from scratch."""
    state = {
        "session": greeted.get("session", ""),
        "users": list(greeted.get("users", [])),
        "last": dict(greeted.get("last", {})),
    }
    if state["session"] != session:
        state["session"], state["users"] = session, []
    if login in state["users"] or not messages:
        return state, None
    state["users"].append(login)                      # marked now, so two quick messages can't greet twice
    last = state["last"].get(login)
    pick = rng.choice([m for m in messages if m != last] or messages)
    state["last"][login] = pick
    return state, pick


def release(greeted: dict, login: str) -> dict:
    """Takes the person off the 'already greeted' list (used when the greeting couldn't be sent)."""
    state = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in greeted.items()}
    state["users"] = [u for u in state.get("users", []) if u != login]
    return state

# ---------- 1.18.0: First-time chatters (a tab on the Events page; kept here, in greetings["welcome"]) ----------
# Someone writing in the channel's chat for the first time ever gets a welcome. "First time" = the app has never seen them
# (Stream stats keeps every name it has seen since 1.14.0, started from the last 30 days of activity), or Twitch's own
# first-time chatter intro. Kept in greetings["welcome"]; a missing part takes its default.
WELCOME_DEFAULT = {
    "enabled": True,
    "replies": None,         # None = the ready ones in the app's language (WELCOME_REPLIES)
    "salam_replies": None,   # the first message says السلام عليكم: these instead (empty = the normal replies)
    "follow_replies": None,  # they just followed (this stream, or in the last hour): these (empty = the normal replies)
    "salam_follow_replies": None,   # both (empty = the السلام replies, then the follow ones, then the normal ones)
    "delay": 3,              # seconds before the welcome (0, 3, 5 or 10)
    "skip_commands": True,   # a first message that is a command (!discord) gets no welcome
    "reply_bots": False,     # bots (Nightbot, Falkorie …) never get one unless this is on
}
WELCOME_REPLIES = {
    "en": ["Welcome {user}! First time here? Glad you made it", "Hey {user}, welcome to the stream! Make yourself at home"],
    "ar": ["{user} حياك نورت/ي"],
}
SALAM_REPLIES = {
    "en": ["Wa alaikum assalam {user}! Welcome to the stream"],
    "ar": ["وعليكم السلام {user}، حياك نورت/ي"],
}
FOLLOW_REPLIES = {
    "en": ["Welcome {user}, and thanks for the follow!"],
    "ar": ["{user} نورت/ي وشكرا عالفولو"],
}
SALAM_FOLLOW_REPLIES = {
    "en": ["Wa alaikum assalam {user}! Thanks for the follow"],
    "ar": ["وعليكم السلام {user}، نورت/ي وشكرا عالفولو"],
}
WELCOME_LISTS = (("salam_follow_replies", SALAM_FOLLOW_REPLIES), ("salam_replies", SALAM_REPLIES),
                 ("follow_replies", FOLLOW_REPLIES), ("replies", WELCOME_REPLIES))
JUST_FOLLOWED = 3600       # "just followed" = during this stream, or in the last hour if the stream started later
WELCOME_DELAYS = (0, 3, 5, 10)
KNOWN_BOTS = frozenset({
    "nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "falkorie", "soundalerts", "sery_bot",
    "kofistreambot", "botrixoficial", "commanderroot", "streamstickers", "pokemoncommunitygame", "blerp", "lumiastream",
})


def welcome_cfg(greetings, lang: str = "en") -> dict:
    """The welcome settings, every part filled in (the ready Arabic replies until you save your own)."""
    w = (greetings or {}).get("welcome") if isinstance(greetings, dict) else None
    out = dict(WELCOME_DEFAULT)
    if isinstance(w, dict):
        out.update({k: w[k] for k in WELCOME_DEFAULT if k in w})
    lang = "ar"   # 1.18.0: the ready replies are Arabic in every app language (the English ones stay for reference)
    for key, ready in WELCOME_LISTS:
        if out.get(key) is None:
            out[key] = list(ready[lang])
        out[key] = [str(r) for r in (out.get(key) or []) if str(r).strip()]
    return out


def is_bot(login: str, badges=()) -> bool:
    """A chat bot: a well-known bot account, or Twitch's own "Chat Bot" badge."""
    login = str(login or "").lower()
    return login in KNOWN_BOTS or any(
        str(getattr(b, "set_id", b) or "") in ("bot-badge", "chatbot") for b in (badges or ()))


_TASHKEEL = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u0640]")
_SALAM_AR = re.compile(r"(?:^|\s)(?:ال)?سلام\s*(?:عليكم|عليكو|عليكوم|عليك)|^\W*(?:ال)?سلام\W*$")
_SALAM_EN = re.compile(r"\b(?:a?s+)?sala+m+(?:u|o)?\b(?:\s*(?:a|3)?l[ae]y?[ck]+o?u?m+)?", re.I)


def says_salam(text: str) -> bool:
    """1.18.0: «السلام عليكم», «سلام عليكم», just «السلام» / «سلام», or «salam», «assalamu alaikum» …"""
    t = _TASHKEEL.sub("", str(text or "")).replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").strip()
    return bool(_SALAM_AR.search(t) or _SALAM_EN.search(t))


def welcome_list(cfg: dict, salam: bool = False, followed: bool = False) -> str:
    """Which list answers: السلام + just followed → السلام+follow, else السلام, else follow, else the normal replies (the
    first of those that has a reply)."""
    order = (["salam_follow_replies"] if salam and followed else []) + (["salam_replies"] if salam else []) \
        + (["follow_replies"] if followed else []) + ["replies"]
    return next((k for k in order if cfg.get(k)), "replies")


def pick_welcome(cfg: dict, last: str = "", rng=random, salam: bool = False, followed: bool = False) -> str:
    """One of the replies at random (not the same as last time when there are several)."""
    replies = cfg.get(welcome_list(cfg, salam, followed)) or []
    if not replies:
        return ""
    pool = [r for r in replies if r != last] or replies
    return rng.choice(pool)
