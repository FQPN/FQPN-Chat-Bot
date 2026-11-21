"""1.20.0: ONE renewal per Twitch renewal key, for the whole app.

Twitch's renewal key (refresh token) for this app's kind of login can be used once. Two parts of the app renewing the
same login at the same moment (the channel's running bot inside TwitchIO, and the sender when that channel writes for
another of your channels; most often right after the PC wakes up, when every login is expired at once) meant the second
renewal used a key that was already spent. Twitch then refused it, and could refuse the whole login: the app said
"connect Twitch again" every so often although nothing was wrong.

Now every renewal goes through renew(): the first caller asks Twitch, anyone asking with the same key at the same time
waits for that answer, and anyone asking later with an already-used key gets the answer it produced (a later renewal of
the NEW key is looked up the same way, so a late caller always ends with the newest login). Nothing is saved here: the
callers save the new login as before. Only this app's memory, never a file, and the keys are never logged."""

import asyncio
import logging
import time

log = logging.getLogger("tokenrenew")

KEEP = 24 * 3600          # how long a used key's answer is remembered (a login renews about every 4 hours)
MAX_KEEP = 200            # at most this many answers kept

_done: dict = {}           # used key -> (when, Twitch's answer as a dict)
_busy: dict = {}           # key being renewed right now -> future with the answer


def _forget_old(now: float) -> None:
    for k in [k for k, v in _done.items() if now - v[0] > KEEP]:
        _done.pop(k, None)
    if len(_done) > MAX_KEEP:
        for k, _ in sorted(_done.items(), key=lambda kv: kv[1][0])[: len(_done) - MAX_KEEP]:
            _done.pop(k, None)


async def renew(key: str, fetch) -> dict:
    """Twitch's answer (a dict with access_token, refresh_token, expires_in, scope) for renewing with `key`.
    fetch(): the caller's own call to Twitch, returning that dict or raising. It runs at most once per key."""
    now = time.time()
    _forget_old(now)
    hit = _done.get(key)
    if hit:
        log.info("A login renewal was already done a moment ago: using its result (no second renewal)")
        return dict(hit[1])
    fut = _busy.get(key)
    if fut is not None:
        return dict(await asyncio.shield(fut))
    fut = asyncio.get_running_loop().create_future()
    _busy[key] = fut
    try:
        data = await fetch()
        if not isinstance(data, dict) or not data.get("access_token"):
            raise ValueError("Twitch's renewal answer had no login in it")
        data = dict(data)
        data.setdefault("refresh_token", key)
        data.setdefault("token_type", "bearer")
        data.setdefault("scope", [])
        _done[key] = (time.time(), data)
        fut.set_result(data)
        return dict(data)
    except BaseException as e:
        if not fut.done():
            fut.set_exception(e if isinstance(e, Exception) else RuntimeError("renewal cancelled"))
            fut.exception()                       # (marks it seen: no "exception never retrieved" warning)
        raise
    finally:
        _busy.pop(key, None)


def install() -> None:
    """Sends TwitchIO's own renewals through renew() too (TwitchIO renews the running bots' logins)."""
    try:
        from twitchio.authentication import oauth as _oauth
        from twitchio.authentication.payloads import RefreshTokenPayload
    except Exception:
        log.warning("Couldn't hook TwitchIO's login renewal: renewals are not shared")
        return
    cls = _oauth.OAuth
    if getattr(cls.refresh_token, "_fqpn_shared", False):
        return
    original = cls.refresh_token

    async def refresh_token(self, refresh_token: str, /):
        async def fetch():
            payload = await original(self, refresh_token)
            raw = getattr(payload, "raw_data", None)
            if isinstance(raw, dict) and raw.get("access_token"):
                return raw
            return {"access_token": payload.access_token, "refresh_token": payload.refresh_token,
                    "expires_in": payload.expires_in, "scope": payload.scope, "token_type": payload.token_type}
        return RefreshTokenPayload(await renew(refresh_token, fetch))

    refresh_token._fqpn_shared = True
    cls.refresh_token = refresh_token
