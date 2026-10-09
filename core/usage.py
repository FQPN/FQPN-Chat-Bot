"""Lets the developer know which channels use the app: about once a day it sends the channel name and the app version to the
website (SITE in publiclist.py). Nothing else is sent. This is always on, and it is explained to the streamer in Settings > App.

The channel's Twitch login goes with it only so the website can ask Twitch which channel it really is; the website does not keep it.
The bot never waits for this: if the website is down, the next try is later."""
import asyncio
import logging
import time

from . import auth, publiclist
from .version import VERSION

log = logging.getLogger("twitchbot.usage")

FIRST_DELAY = 30            # seconds after the app connects to Twitch
EVERY = 24 * 3600           # then once a day
RETRY = (300, 900, 1800, 3600)    # after a failure: 5 min, 15 min, 30 min, then every hour
BANNED_EVERY = 3600         # while the developer has turned the app off for this channel: ask every hour (an unban works soon)


def payload() -> dict:
    """Exactly what is sent: the data format number and the app version (the website learns the channel from Twitch)."""
    return {"v": 1, "version": str(VERSION)}


class Reporter:
    """Also learns from the answer whether the developer turned the app off for this channel (a ban). The answer is kept on
    disk, so a restart doesn't run the bot even briefly; if the website can't be reached, the last answer stands."""

    def __init__(self, state, send=None, clock=time.time, store=None, on_change=None):
        self.state = state
        self.store = store
        self.on_change = on_change
        self.send = send or (lambda token, data: publiclist.http_send("PUT", token, data, path="/api/seen"))
        self.clock = clock
        self.next_at = None          # when to send next (None = not yet planned)
        self.fails = 0
        self.last_ok = None

    async def step(self) -> None:
        if not publiclist.SITE:
            return
        token = (auth.load_token() or {}).get("access_token") or ""
        if not token or not self.state.get("account"):
            self.next_at = None      # not connected to Twitch yet: start counting once it is
            return
        now = self.clock()
        if self.next_at is None:
            self.next_at = now + FIRST_DELAY
        if now < self.next_at:
            return
        code, body, retry = await self.send(token, payload())
        if code in (200, 429):       # 429: already counted within the last hour, which is just as good
            banned = bool((body or {}).get("banned"))
            self.fails, self.last_ok, self.next_at = 0, now, now + (BANNED_EVERY if banned else EVERY)
            self.set_banned(banned)
        else:
            wait = RETRY[min(self.fails, len(RETRY) - 1)]
            self.fails += 1
            self.next_at = now + max(wait, int(retry or 0))
            log.info("Could not reach the website (%s); trying again in %s s", code, wait)

    def set_banned(self, banned: bool) -> None:
        if bool(self.state.get("banned")) == banned:
            return
        self.state["banned"] = banned
        if self.store is not None:
            self.store.save("usage_state", {"banned": banned})
        log.warning("The developer turned the app %s for this channel", "OFF" if banned else "back ON")
        if self.on_change:
            self.on_change()         # stops the bot (banned) or starts it again (unbanned)

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Usage report failed")
            await asyncio.sleep(10)
