"""bot.log safety: no Twitch login keys in the log, the same error written once a minute (with a count), not every 10 seconds,
and short plain lines instead of tracebacks when the internet blips."""
import logging
import re
import time

_SECRET = re.compile(r"((?:refresh_token|access_token|client_secret|code|token)=)[^&\s'\"]+|((?:OAuth|Bearer)\s+)[A-Za-z0-9]{12,}", re.IGNORECASE)


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: (m.group(1) or m.group(2)) + "[hidden]", text)


class SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


class Quiet(logging.Filter):
    """Keeps bot.log readable when the internet or Twitch blips. Nothing here hides a real problem:
    the watchdog still sees the drop and reconnects; only the noise around it goes.
    - twitchio's StarletteAdapter note: printed on every start, about a part this app never uses.
    - "Unable to resubscribe ... session does not exist": Twitch closed the old connection before
      twitchio could move to the new one. It comes in a burst of 9-10; one plain line is enough."""

    RESUB = "Unable to resubscribe to subscription"

    def __init__(self, every: float = 60.0, clock=time.time):
        super().__init__()
        self.every, self.clock, self.last_resub = every, clock, -1e18

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "StarletteAdapter" in msg:
            return False
        if msg.startswith(self.RESUB):
            now = self.clock()
            if now - self.last_resub < self.every:
                return False
            self.last_resub = now
            record.levelno, record.levelname = logging.WARNING, "WARNING"
            record.msg, record.args = "Twitch reset the connection; the bot reconnects by itself", ()
            record.exc_info = record.exc_text = None
        return True


def install(fmt: str = "%(asctime)s %(levelname)s %(message)s") -> None:
    """Every log handler hides login keys from now on (bot.log and the console), and skips the noise."""
    quiet = Quiet()
    for h in logging.getLogger().handlers:
        h.setFormatter(SafeFormatter(fmt))
        h.addFilter(quiet)


def _offline(exc) -> bool:
    """True when the error only means "no internet right now" (DNS failed, connection refused, timed out)."""
    import asyncio
    import socket
    seen = 0
    while exc is not None and seen < 8:
        if isinstance(exc, (socket.gaierror, ConnectionError, TimeoutError, asyncio.TimeoutError)):
            return True
        if type(exc).__name__ in ("ClientConnectorError", "ClientConnectorDNSError", "ServerDisconnectedError",
                                  "ClientOSError", "ServerTimeoutError"):
            return True
        exc, seen = exc.__cause__ or exc.__context__, seen + 1
    return False


class Throttle:
    """Writes an error with its details the first time, then at most once a minute: "(the same again 6 times)"."""

    def __init__(self, every: float = 60.0, clock=time.time):
        self.every, self.clock, self.seen = every, clock, {}

    def exception(self, log, key: str, msg: str) -> None:
        now = self.clock()
        last, count = self.seen.get(key, (0.0, 0))
        if now - last >= self.every:
            more = f" (and {count} more times since the last report)" if count else ""
            import sys
            if _offline(sys.exc_info()[1]):
                # no internet for a moment: one plain line, not a 25-line traceback
                log.warning("%s: no internet connection right now, trying again%s", msg, more)
            else:
                log.exception(msg + more)
            self.seen[key] = (now, 0)
        else:
            self.seen[key] = (last, count + 1)
