"""1.15.0 (owner): timed blocks on the Blocklist. Permanent blocks stay in blocklist["users"] exactly as before; a timed
block is {"user", "from", "until"} in blocklist["timed"]. When "until" has passed, the user is no longer blocked, and the
entry is removed from the list (by the bot's timer loop, by the page, and by any save)."""

import time

MAX_AMOUNT = 99                     # owner: 1 to 99 minutes or hours; more is clipped to 99, less to 1
UNITS = {"minutes": 60, "hours": 3600}


def clamp(amount) -> int:
    try:
        n = int(float(amount))
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_AMOUNT, n))


def timed(block: dict, now=None) -> list:
    """The timed blocks still running, soonest to end first."""
    now = time.time() if now is None else now
    items = [t for t in (block or {}).get("timed") or [] if isinstance(t, dict) and float(t.get("until") or 0) > now and t.get("user")]
    return sorted(items, key=lambda t: float(t["until"]))


def blocked_logins(block: dict, now=None) -> set:
    """Everyone blocked right now (lowercase): the permanent ones and the timed ones still running."""
    perm = {str(u).lower() for u in (block or {}).get("users") or []}
    return perm | {str(t["user"]).lower() for t in timed(block, now)}


def prune(block: dict, now=None) -> bool:
    """Removes timed blocks that have ended. True when something was removed (then save the blocklist)."""
    if not isinstance(block, dict) or not block.get("timed"):
        return False
    keep = timed(block, now)
    if len(keep) == len(block["timed"]):
        return False
    block["timed"] = keep
    return True


def add_timed(block: dict, user: str, amount, unit: str, now=None) -> dict:
    """Blocks `user` for 1-99 minutes or hours (a permanent or older timed block of the same user is replaced)."""
    now = time.time() if now is None else now
    user = str(user).strip().lstrip("@")
    secs = clamp(amount) * UNITS.get(unit, 60)
    block["users"] = [u for u in block.get("users") or [] if str(u).lower() != user.lower()]
    block["timed"] = [t for t in timed(block, now) if str(t["user"]).lower() != user.lower()] + [{"user": user, "from": now, "until": now + secs}]
    return block
