"""bot.log safety: no Twitch login keys in the log, and the same error written once a minute (with a count), not every 10 seconds."""
import logging
import re
import time

_SECRET = re.compile(r"((?:refresh_token|access_token|client_secret|code|token)=)[^&\s'\"]+|((?:OAuth|Bearer)\s+)[A-Za-z0-9]{12,}", re.IGNORECASE)


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: (m.group(1) or m.group(2)) + "[hidden]", text)


class SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def install(fmt: str = "%(asctime)s %(levelname)s %(message)s") -> None:
    """Every log handler hides login keys from now on (bot.log and the console)."""
    for h in logging.getLogger().handlers:
        h.setFormatter(SafeFormatter(fmt))


class Throttle:
    """Writes an error with its details the first time, then at most once a minute: "(the same again 6 times)"."""

    def __init__(self, every: float = 60.0, clock=time.time):
        self.every, self.clock, self.seen = every, clock, {}

    def exception(self, log, key: str, msg: str) -> None:
        now = self.clock()
        last, count = self.seen.get(key, (0.0, 0))
        if now - last >= self.every:
            log.exception(msg + (f" (and {count} more times since the last report)" if count else ""))
            self.seen[key] = (now, 0)
        else:
            self.seen[key] = (last, count + 1)
