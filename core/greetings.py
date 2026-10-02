"""Greeting a chosen person once per stream. Pure functions, so they can be tested without Twitch.

The bot greets a person from the list the first time they write in chat during a stream, a few
seconds later, with one of their messages picked at random (never the same one twice in a row)."""

import random

GREETING_DELAY = 3   # seconds between the person's first message and the greeting


def messages_for(greetings: dict, login: str) -> list[str]:
    """The messages to choose from for this person, or [] if they have none / greetings are off."""
    if not greetings.get("enabled", True):
        return []
    for item in greetings.get("users", []):
        if item.get("enabled", True) and str(item.get("user", "")).lower() == login:
            return [m for m in item.get("messages", []) if isinstance(m, str) and m.strip()]
    return []


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