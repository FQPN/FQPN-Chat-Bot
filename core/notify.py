"""Desktop pop-ups (and a short sound) for things that happen in chat.
The app window's tray icon does the showing: the launcher registers it with register(). When the app runs from source
there is no tray, so nothing is shown."""

import logging

log = logging.getLogger("notify")

_sender = None   # a function (title, message) that shows one pop-up


def register(fn) -> None:
    global _sender
    _sender = fn


def available() -> bool:
    return _sender is not None


def _beep() -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:       # not Windows, or no sound device
        pass


def send(prefs: dict, title: str, message: str) -> bool:
    """Shows a pop-up if the user turned notifications on and a tray icon exists. Never raises."""
    if not prefs.get("notify", True) or _sender is None:
        return False
    try:
        _sender(title[:60], message[:240])
    except Exception:
        log.exception("Could not show a notification")
        return False
    if prefs.get("notify_sound", False):
        _beep()
    return True


def event_text(key: str, user: str, value: int, extra: dict | None = None) -> tuple:
    extra = extra or {}
    user = user or "Someone"
    if key == "follow":
        return "New follower", f"{user} followed your channel"
    if key == "subscription":
        return "New subscriber", f"{user} subscribed ({extra.get('tier', 'Tier 1')}, {value} month{'s' if value != 1 else ''})"
    if key == "gift_sub":
        return "Gifted subs", f"{user} gifted {value} sub{'s' if value != 1 else ''}"
    if key == "raid":
        return "Raid", f"{extra.get('raider', user)} raided with {value} viewer{'s' if value != 1 else ''}"
    if key == "hype_train":
        return "Hype Train", f"Level {value}"
    if key == "bits":
        return "Bits", f"{user} cheered {value} bit{'s' if value != 1 else ''}"
    if key == "watch_streak":
        return "Watch streak", f"{user} shared a {value}-stream streak"
    return "FQPN's Chat Bot", f"{key.replace('_', ' ')} from {user}"


def event(prefs: dict, key: str, user: str, value: int, extra: dict | None = None) -> bool:
    title, message = event_text(key, user, value, extra)
    return send(prefs, title, message)


def error(prefs: dict, message: str) -> bool:
    return send(prefs, "FQPN's Chat Bot", message)
