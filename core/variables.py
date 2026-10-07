"""Nightbot-style variables: $(user) $(touser) $(query) $(querystring)
$(count) $(urlfetch URL) $(eval MATH) $(channel) $(game) $(title) $(uptime) $(viewers)

Safety rules:
- Only the response template is expanded. Text that comes from chat (the
  query, usernames) or from a URL is never expanded again, so a viewer can't
  sneak in "$(urlfetch ...)" through $(query).
- $(urlfetch) only talks to public internet addresses, never to this PC or
  anything on the local network.
- $(eval) is a small, safe calculator (numbers, + - * / %, parentheses and a few
  Math functions). It is NOT a JavaScript engine, so it can't run code.
"""

import asyncio
import calendar
import ipaddress
import logging
import math
import random
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import quote, urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver

log = logging.getLogger("twitchbot.variables")

_ALLOW_PRIVATE = False  # only flipped by tests
_EVAL_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*|\.\d+)|([A-Za-z_][A-Za-z0-9_.]*)|(.))")


def _innermost(s: str) -> list[tuple[int, int]]:
    """(start, end) of every $( ... ) that has no other $( inside it. Plain ( ) inside are fine
    as long as they are balanced, so $(eval Math.floor(Math.random() * 101)) is one group."""
    found, i = [], 0
    while True:
        a = s.find("$(", i)
        if a < 0:
            return found
        depth, j = 1, a + 2
        while j < len(s) and depth:
            depth += (s[j] == "(") - (s[j] == ")")
            j += 1
        if depth or "$(" in s[a + 2:j - 1]:   # never closed, or has an inner group that goes first
            i = a + 2
            continue
        found.append((a, j))
        i = j
_TOKEN = re.compile(r"\x00(\d+)\x00")
LEGACY = {"{user}": "$(user)", "{streamer}": "$(channel)", "{uptime}": "$(uptime)", "{streak}": "$(streak)", "{channel}": "$(channel)"}


class FetchError(Exception):
    pass


# ---------- safe URL fetching ----------

class _SafeResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        out = []
        for fam, _, _, _, addr in infos:
            if not _ALLOW_PRIVATE and not ipaddress.ip_address(addr[0]).is_global:
                raise OSError("blocked address")
            out.append({"hostname": host, "host": addr[0], "port": addr[1],
                        "family": fam, "proto": 0, "flags": socket.AI_NUMERICHOST})
        return out

    async def close(self):
        pass


_fetch_cache: dict[str, tuple[float, str]] = {}


async def fetch_url(url: str, cache_seconds: int = 20) -> str:
    url = url.strip()
    hit = _fetch_cache.get(url)
    if hit and time.time() - hit[0] < cache_seconds:
        return hit[1]

    text = None
    for _ in range(4):  # follow at most 3 redirects, re-checking each hop
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise FetchError("invalid URL")
        try:
            ip = ipaddress.ip_address(parts.hostname)
        except ValueError:
            ip = None
        if ip is not None and not ip.is_global and not _ALLOW_PRIVATE:
            raise FetchError("blocked address")

        connector = aiohttp.TCPConnector(resolver=_SafeResolver())
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(url, allow_redirects=False, headers={"User-Agent": "TwitchBot/1.0"}) as r:
                if r.status in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                    url = urljoin(url, r.headers["Location"])
                    continue
                if r.status >= 400:
                    if (r.headers.get("Content-Type") or "").lower().startswith("text/plain"):
                        note = " ".join((await r.content.read(1024)).decode(r.charset or "utf-8", errors="replace").split())[:300]
                        if note:
                            return note   # the service explained the problem itself; not cached
                    raise FetchError(f"HTTP {r.status}")
                raw = await r.content.read(2048)
                text = raw.decode(r.charset or "utf-8", errors="replace")
        break
    if text is None:
        raise FetchError("too many redirects")

    text = " ".join(text.split())[:400]
    if len(_fetch_cache) > 100:
        _fetch_cache.clear()
    _fetch_cache[url] = (time.time(), text)
    return text


# ---------- $(eval): a small safe calculator ----------

class EvalError(Exception):
    pass


_MATH_FUNCS = {
    "Math.floor": (1, 1, lambda a: math.floor(a)),
    "Math.ceil": (1, 1, lambda a: math.ceil(a)),
    "Math.round": (1, 1, lambda a: math.floor(a + 0.5)),      # JavaScript rounds .5 up
    "Math.trunc": (1, 1, lambda a: math.trunc(a)),
    "Math.abs": (1, 1, lambda a: abs(a)),
    "Math.sqrt": (1, 1, lambda a: math.sqrt(a)),
    "Math.pow": (2, 2, lambda a, b: a ** b),
    "Math.min": (1, 10, lambda *a: min(a)),
    "Math.max": (1, 10, lambda *a: max(a)),
    "Math.random": (0, 0, lambda: random.random()),
}
_MATH_CONSTS = {"Math.PI": math.pi, "Math.E": math.e}


def safe_eval(expr: str) -> str:
    """Evaluates numbers, + - * / %, parentheses and the Math functions above, like Nightbot's
    $(eval Math.floor(Math.random() * 101)). Anything else raises EvalError."""
    if len(expr) > 200:
        raise EvalError("expression too long")
    toks, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = _EVAL_TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise EvalError("unexpected text")
        num, name, other = m.groups()
        toks.append(("n", float(num)) if num else ("i", name) if name else ("o", other))
        pos = m.end()
    if not toks:
        raise EvalError("empty expression")
    i = 0

    def peek():
        return toks[i] if i < len(toks) else (None, None)

    def take(kind=None, val=None):
        nonlocal i
        k, v = peek()
        if k is None or (kind and k != kind) or (val and v != val):
            raise EvalError("unexpected end or symbol")
        i += 1
        return v

    def check(x):
        if isinstance(x, complex) or not math.isfinite(x) or abs(x) > 1e300:
            raise EvalError("number out of range")
        return x

    def expr_(depth):
        if depth > 30:
            raise EvalError("too deeply nested")
        x = term(depth)
        while peek() in (("o", "+"), ("o", "-")):
            op = take()
            y = term(depth)
            x = check(x + y if op == "+" else x - y)
        return x

    def term(depth):
        x = unary(depth)
        while peek() in (("o", "*"), ("o", "/"), ("o", "%")):
            op = take()
            y = unary(depth)
            if op == "*":
                x = check(x * y)
            elif y == 0:
                raise EvalError("division by zero")
            else:
                x = check(x / y if op == "/" else math.fmod(x, y))
        return x

    def unary(depth):
        if peek() in (("o", "+"), ("o", "-")):
            return check(-unary(depth) if take() == "-" else unary(depth))
        return primary(depth)

    def primary(depth):
        k, v = peek()
        if k == "n":
            take()
            return v
        if k == "o" and v == "(":
            take()
            x = expr_(depth + 1)
            take("o", ")")
            return x
        if k == "i":
            take()
            if v in _MATH_CONSTS:
                return _MATH_CONSTS[v]
            if v not in _MATH_FUNCS:
                raise EvalError(f"unknown name {v}")
            lo, hi, fn = _MATH_FUNCS[v]
            take("o", "(")
            args = []
            if peek() != ("o", ")"):
                args.append(expr_(depth + 1))
                while peek() == ("o", ","):
                    take()
                    args.append(expr_(depth + 1))
            take("o", ")")
            if not lo <= len(args) <= hi:
                raise EvalError(f"{v} needs {lo} argument(s)")
            try:
                return check(fn(*args))
            except (ValueError, OverflowError, ZeroDivisionError, TypeError):
                raise EvalError("invalid number")
        raise EvalError("unexpected symbol")

    result = expr_(0)
    if i != len(toks):
        raise EvalError("unexpected symbol")
    if result == int(result) and abs(result) < 1e21:
        return str(int(result))
    return repr(float(result))


# ---------- expansion ----------

def follow_date(dt: datetime) -> str:
    return f"{dt:%B} {dt.day}, {dt.year}"


def follow_age(start: datetime, now: datetime | None = None) -> str:
    """'1 year, 2 months, 3 days' between start and now."""
    now = now or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    y, m, d = now.year - start.year, now.month - start.month, now.day - start.day
    if d < 0:
        m -= 1
        prev_year, prev_month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        d += calendar.monthrange(prev_year, prev_month)[1]
    if m < 0:
        y -= 1
        m += 12
    parts = [f"{n} {word}{'' if n == 1 else 's'}" for n, word in ((y, "year"), (m, "month"), (d, "day")) if n]
    return ", ".join(parts) or "less than a day"


@dataclass
class Context:
    user: str = ""
    query: str = ""
    channel: str = ""
    uptime: str = ""
    viewers: int = 0        # how many people are watching right now (updated with every live check)
    count: Callable[[], int] = lambda: 0
    game: Callable[[], Awaitable[str]] | None = None
    title: Callable[[], Awaitable[str]] | None = None
    followed_at: Callable[[], Awaitable[datetime | None]] | None = None
    is_owner: bool = False
    login: str = ""          # the viewer's Twitch login name (always plain letters/numbers)
    streak: int | None = None   # a viewer's Watch Streak (only set for the Watch Streak reply)
    extra: dict = field(default_factory=dict)   # variables of a Twitch event: bits, gifts, raider, viewers, level, tier, months, message
    fetch: Callable[[str], Awaitable[str]] = fetch_url

    @property
    def args(self) -> list[str]:
        return self.query.split()


def uses_variable(template: str, name: str) -> bool:
    return f"$({name}" in translate_legacy(template).lower()


def translate_legacy(template: str) -> str:
    for old, new in LEGACY.items():
        template = template.replace(old, new)
    return template


async def expand(template: str, ctx: Context) -> str:
    template = translate_legacy(template).replace("\x00", "")
    for name in ctx.extra:   # {bits} works like $(bits) in an event reply
        template = template.replace("{" + name + "}", "$(" + name + ")")
    values: list[str] = []

    url_values: list[str] = []   # the same values as they must look inside a web address

    def tok(v: str, url_form: str | None = None) -> str:
        v = str(v).replace("\x00", "")
        values.append(v)
        url_values.append(v if url_form is None else str(url_form).replace("\x00", ""))
        return f"\x00{len(values) - 1}\x00"

    def restore(s: str) -> str:
        return _TOKEN.sub(lambda m: values[int(m.group(1))], s)

    def restore_url(s: str) -> str:
        return _TOKEN.sub(lambda m: url_values[int(m.group(1))], s)

    async def resolve(body: str, original: str) -> tuple[str, str]:
        """(text for chat, text for use inside a $(urlfetch ...) address).
        Inside an address everything a viewer can type is percent-encoded, and $(user) and the
        default $(touser) use the plain login name (display names can be in other alphabets)."""
        value = await resolve_text(body, original)
        key = body.strip().partition(" ")[0].lower()
        if key == "querystring":
            return value, value
        if key in ("user", "touser"):
            name = ctx.login or ctx.user
            if key == "touser" and ctx.args and ctx.args[0].lstrip("@"):
                name = ctx.args[0].lstrip("@")
            return value, quote(name, safe="")
        return value, quote(value, safe="")

    async def resolve_text(body: str, original: str) -> str:
        name, _, arg = body.strip().partition(" ")
        key = name.lower()
        if key == "user":
            return ctx.user
        if key == "touser":
            return (ctx.args[0].lstrip("@") if ctx.args else "") or ctx.user
        if key == "query":
            return ctx.query
        if key == "querystring":
            return quote(ctx.query, safe="")
        if key == "count":
            return str(ctx.count())
        if key == "channel":
            return ctx.channel
        if key == "uptime":
            return ctx.uptime
        if key == "game" and ctx.game:
            return await ctx.game()
        if key == "title" and ctx.title:
            return await ctx.title()
        if key in ("follow", "followdate", "followage"):
            if ctx.is_owner:
                return "owns this channel" if key == "follow" else "(channel owner)"
            if not ctx.followed_at:
                return "(unknown)"
            try:
                when = await ctx.followed_at()
            except Exception:
                return "(follow lookup failed)"
            if when is None:
                return f"isn't following {ctx.channel}" if key == "follow" else "(not following)"
            if key == "followdate":
                return follow_date(when)
            if key == "followage":
                return follow_age(when)
            return f"followed {ctx.channel} on {follow_date(when)} ({follow_age(when)} ago)"
        if key == "streak" and ctx.streak is not None:
            return str(ctx.streak)
        if key == "viewers" and "viewers" not in ctx.extra:
            return str(ctx.viewers)          # in a raid reply, $(viewers) still means the size of the raid (it is in ctx.extra)
        if key in ctx.extra:
            return str(ctx.extra[key])
        if key == "eval":
            try:
                return safe_eval(restore(arg))
            except EvalError as e:
                log.warning("$(eval) failed for %r: %s", restore(arg), e)
                return "(eval failed)"
        if key == "urlfetch":
            address = restore_url(arg)
            try:
                return await ctx.fetch(address)
            except (FetchError, aiohttp.ClientError, OSError, asyncio.TimeoutError, ValueError) as e:
                log.warning("$(urlfetch) failed for %s: %r", address, e)   # shown in the terminal so the cause can be found
                return "(urlfetch failed)"
            except Exception:
                # anything unexpected must never stop the command from answering
                log.exception("$(urlfetch) crashed for %s", address)
                return "(urlfetch failed)"
        return original  # unknown variable: leave it as typed

    s = template
    for _ in range(10):  # innermost first, so $(urlfetch x$(querystring)) works
        groups = _innermost(s)
        if not groups:
            break
        out, last = [], 0
        for a, b in groups:
            out.append(s[last:a])
            text_form, url_form = await resolve(s[a + 2:b - 1], s[a:b])
            out.append(tok(text_form, url_form))
            last = b
        out.append(s[last:])
        s = "".join(out)
    return restore(s)