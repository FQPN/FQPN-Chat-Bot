"""Replies to Twitch events (watch streaks, follows, subs, gifted subs, raids, hype trains, bits) and donations.
Pure functions, so they can be tested without Twitch.

Every event has the same shape:  {"enabled": true, "tiers": [{"min": 100, "response": "..."}, ...]}
The bot answers with the tier that has the highest "min" the event reaches, so 1 / 100 / 500 / 1000 bits can
each get their own reply. Follows and watch streaks have a single reply."""

EVENT_KEYS = ("watch_streak", "follow", "subscription", "gift_sub", "raid", "hype_train", "bits", "donation")
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


def watch_streak_template(events: dict, streak: int):
    """Kept for older code: the Watch Streak reply for this streak."""
    return pick_reply(events, "watch_streak", streak)
