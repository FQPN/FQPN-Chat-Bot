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


_chime: bytes = b""


def chime() -> bytes:
    """1.14.0: the app's own notification sound (instead of Windows' standard beep): three soft, rising bell notes
    (C6, E6, G6), about half a second. Made here, in memory, as a small WAV: no sound file to ship or lose."""
    global _chime
    if _chime:
        return _chime
    import io, math, struct, wave
    rate, total = 22050, 0.75
    notes = ((0.00, 1046.50), (0.09, 1318.51), (0.18, 1567.98))        # when each note starts (s), its pitch (Hz)
    n = int(rate * total)
    samples = []
    for i in range(n):
        t, v = i / rate, 0.0
        for start, f in notes:
            x = t - start
            if x < 0:
                continue
            env = min(1.0, x / 0.006) * math.exp(-x * 7.5)               # a quick, soft attack, then a bell-like fade
            v += env * (math.sin(2 * math.pi * f * x) + 0.22 * math.sin(4 * math.pi * f * x) + 0.06 * math.sin(6 * math.pi * f * x))
        tail = min(1.0, (total - t) / 0.05)                                 # no click at the very end
        samples.append(int(max(-1.0, min(1.0, v * 0.24 * tail)) * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    _chime = buf.getvalue()
    return _chime


def _beep() -> None:
    """Plays the chime without holding anything up (a sound from memory can't be played "in the background" by Windows,
    so a short helper thread plays it). Falls back to Windows' beep."""
    def play():
        try:
            import winsound
            try:
                winsound.PlaySound(chime(), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            except Exception:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:       # not Windows, or no sound device
            pass
    import threading
    threading.Thread(target=play, daemon=True).start()


def play_sound() -> None:
    """Settings > Notifications > Listen."""
    _beep()


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
    if key == "falkorie_level":
        return "Falkorie: new level", f"{user} reached level {value}"
    if key == "falkorie_streak":
        return "Falkorie: streak", f"{user} watched {value} streams in a row"
    if key == "donation":
        return "Donation", f"{user} donated {extra.get('amount', value)} {extra.get('currency', '')}".strip()
    return "FQPN's Chat Bot", f"{key.replace('_', ' ')} from {user}"


def event(prefs: dict, key: str, user: str, value: int, extra: dict | None = None) -> bool:
    title, message = event_text(key, user, value, extra)
    return send(prefs, title, message)


def error(prefs: dict, message: str) -> bool:
    return send(prefs, "FQPN's Chat Bot", message)
