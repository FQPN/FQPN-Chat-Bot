"""Greeting a chosen person once per stream. Pure functions, so they can be tested without Twitch.

The bot greets a person from the list the first time they write in chat during a stream, a few
seconds later, with one of their messages picked at random (never the same one twice in a row)."""

import random

GREETING_DELAY = 3   # seconds between the person's first message and the greeting

# The app's developers, by permanent Twitch user ID (a name can change, the ID never does). To add someone, add their ID here.
DEVELOPERS = frozenset({
    "1299878164",    # 1asoom
    "754527671",     # fqpn_
})
DEVELOPER_GREETING = "حيوووووو بالمبرمج الاسطوري 🔥"


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
    return [DEVELOPER_GREETING]


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