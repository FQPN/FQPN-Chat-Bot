"""Replies to Twitch events (watch streaks, follows, subs, gifted subs, raids, hype trains, bits) and donations.
Pure functions, so they can be tested without Twitch.

Every event has the same shape:  {"enabled": true, "tiers": [{"min": 100, "response": "..."}, ...]}
The bot answers with the tier that has the highest "min" the event reaches, so 1 / 100 / 500 / 1000 bits can
each get their own reply. Follows and watch streaks have a single reply."""

import re

EVENT_KEYS = ("watch_streak", "follow", "subscription", "gift_sub", "raid", "hype_train", "bits", "donation",
              "falkorie_level", "falkorie_streak")      # 1.17.1: replies to the Falkorie bot's messages (see falkorie())
DECIMAL = {"donation"}              # events whose "from" number can have cents (5.50)
SINGLE = {"follow", "watch_streak"}   # events that only ever have one reply (it answers every time)


def pick_reply(events: dict, key: str, value):
    """The reply text for this event and number (streak, months, gifts, viewers, level, bits), or None."""
    ev = events.get(key)
    if not isinstance(ev, dict) or not ev.get("enabled", True):
        return None
    tiers = [t for t in ev.get("tiers", []) if isinstance(t, dict) and str(t.get("response", "")).strip()]
    if not tiers:
        return None
    if key in SINGLE:
        return str(tiers[0]["response"]).strip()
    best = None
    for t in tiers:
        try:
            lowest = float(t.get("min", 0))
        except (TypeError, ValueError):
            continue
        if value >= lowest and (best is None or lowest > best[0]):
            best = (lowest, str(t["response"]).strip())
    return best[1] if best else None


_USER = re.compile(r"(?<![@\w])(\{user\}|\$\(user\))", re.I)


def at_user(template: str, name, login: str = "") -> str:
    """1.17.1: in event replies {user} becomes @{user}, so the viewer is tagged (@fqpn_ instead of fqpn_).
    Not twice (a reply that already has @{user} stays as it is), and not for a name with a space in it (a donor's
    name from Streamlabs, "An anonymous gifter"): those aren't Twitch names."""
    if not name or re.search(r"\s", str(name)) or str(name).startswith("@"):
        return template
    if login and re.fullmatch(r"\w{1,25}", str(login), re.A) and str(login).lower() != str(name).lower():
        return _USER.sub(lambda m: "@" + str(login).lower(), template)   # an Arabic display name: Twitch tags by login
    return _USER.sub(r"@\1", template)

# 1.17.1: the Falkorie bot (a viewer-level and watch-streak bot) writes in chat:
#   "auk78 is now level 6!"                    -> falkorie_level  (who, 6)
#   "FQPN_ has watched 112 streams in a row!"  -> falkorie_streak (who, 112)   (also its answer to !streak)
FALKORIE = "falkorie"
_F_LEVEL = re.compile(r"^@?(\S{1,25}) is now level (\d{1,6})\b", re.I)
_F_STREAK = re.compile(r"^@?(\S{1,25}) has watched (\d{1,6}) streams? in a row\b", re.I)


def falkorie(login: str, text: str):
    """(event key, viewer's name, number) when this chat message is Falkorie announcing a level or a streak, else None."""
    if str(login or "").lower() != FALKORIE:
        return None
    text = str(text or "").strip()
    for key, rx in (("falkorie_level", _F_LEVEL), ("falkorie_streak", _F_STREAK)):
        m = rx.match(text)
        if m:
            return key, m.group(1), int(m.group(2))
    return None


def watch_streak_template(events: dict, streak: int):
    """Kept for older code: the Watch Streak reply for this streak."""
    return pick_reply(events, "watch_streak", streak)
