"""1.18.0: the first follow date of every follower the bot has seen, kept on this PC.

Twitch forgets a follow when someone unfollows: if they follow again, Twitch's date is the new one. The app keeps the
first date it ever saw for each account (by Twitch user id, so a new name doesn't matter), and while they follow, the
earlier of the two is used: $(followage), $(followdate), $(follow) and the Follow anniversary event all count from it.
Someone not following now still counts as not following.
Stored in the "follow_dates" section: {user_id: [unix_time, login]}.
"""
from datetime import datetime, timezone

SECTION = "follow_dates"


def first_date(store, user_id: str, twitch_when, login: str = ""):
    """The date to use for this follower: Twitch's date, or the earlier one kept here. Keeps the earliest."""
    if twitch_when is None or not user_id:
        return twitch_when
    try:
        ts = twitch_when.timestamp()
    except Exception:
        return twitch_when
    data = store.get(SECTION) or {}
    if not isinstance(data, dict):
        data = {}
    old = data.get(str(user_id))
    try:
        old_ts = float(old[0]) if isinstance(old, (list, tuple)) and old else None
    except (TypeError, ValueError):
        old_ts = None
    if old_ts is not None and old_ts <= ts:
        if login and (len(old) < 2 or old[1] != login):
            data = dict(data)
            data[str(user_id)] = [old_ts, login]
            store.save(SECTION, data)
        return datetime.fromtimestamp(old_ts, tz=timezone.utc)
    data = dict(data)
    data[str(user_id)] = [ts, login or (old[1] if isinstance(old, (list, tuple)) and len(old) > 1 else "")]
    store.save(SECTION, data)
    return twitch_when


def anniversary(when, today) -> int:
    """Whole years since the first follow when today is the follow day (or up to 6 days after it), else 0.
    A 29 February follow has its day on 28 February in other years."""
    if when is None:
        return 0
    d = when.date() if hasattr(when, "date") else when
    for back in range(7):
        day = today.toordinal() - back
        cand = datetime.fromordinal(day).date()
        years = cand.year - d.year
        if years < 1:
            continue
        try:
            mark = d.replace(year=cand.year)
        except ValueError:                       # 29 February
            mark = d.replace(year=cand.year, day=28)
        if mark == cand:
            return years
    return 0


DONE = "follow_anniv"      # {user_id: year celebrated}: one anniversary reply per person per year


def celebrated(store, user_id: str, year: int) -> bool:
    return (store.get(DONE) or {}).get(str(user_id)) == year


def mark_celebrated(store, user_id: str, year: int) -> None:
    data = dict(store.get(DONE) or {})
    data[str(user_id)] = year
    store.save(DONE, data)
