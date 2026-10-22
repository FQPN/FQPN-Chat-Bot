"""Public command list: keeps a copy of the channel's public commands on the command-list website, so viewers can open one
short link (SITE/<channel>) that always shows the latest list. On by default for new installs since 1.10.0 (existing users keep
their choice); the streamer can switch it off on the Commands page.

What is sent: the names of the switched-on commands that are not hidden from the public list, and who can use them;
1.13.0: plus a short example of each reply (unless settings.public_examples is off; $(urlfetch) links never), the mini
games' commands and each built-in's key. Never: cooldowns, aliases, settings.
The channel's Twitch login goes with it so the website can ask Twitch whose channel it is; the website does not keep it.
Nothing else in the app depends on the website: if it is down or switched off, the bot and !cmlist work as before."""
import asyncio
import re
import hashlib
import json
import logging
import time

import aiohttp

from . import auth, manage
from .version import VERSION

log = logging.getLogger("twitchbot.publiclist")

# The website's address, with no slash at the end, e.g. "https://fqpn-commands.fqpn.workers.dev".
# Empty = the feature is not set up in this build (the page says so and nothing is ever sent).
SITE = "https://fqpnbot.com"           # 1.10.1: the domain (1.10.0 used commands.fqpnbot.workers.dev: the same worker, still works)

FORMAT = 1              # the version of the data format; the website reads older formats too (room to add fields later)
CHECK_EVERY = 5         # seconds between looks at the commands (a save in the app wakes it straight away)
SETTLE = 4              # the list must stop changing for this long first, so a burst of edits becomes one save
RETRY = (30, 60, 120, 300, 600)   # after a failure, wait this long (seconds) before the next try
TIMEOUT = 15
MAX_COMMANDS = 500      # the website refuses more (it keeps lists small)


def page_url(login: str) -> str:
    return f"{SITE}/{login}" if SITE and login else ""


BUILTIN_PUBLIC = (("commands", "everyone"), ("title", "everyone"), ("game", "everyone"), ("app", "everyone"),
                  ("addcom", "moderator"), ("editcom", "moderator"), ("delcom", "moderator"))


HEX_RE = re.compile(r"^#[0-9a-f]{6}$")
LB_ROWS = 10


def leaderboard(wins, n: int = LB_ROWS) -> dict:
    """1.13.0: the games' top 10 for the public page: all games together (with each game's part), حروف, رتب."""
    from . import minigames
    rows = []
    for e in (wins or {}).values():
        if isinstance(e, dict):
            rows.append({"n": str(e.get("name") or "?")[:40], "w": int(minigames.wins_of(e, None) or 0),
                         "l": int(minigames.wins_of(e, "letters") or 0), "u": int(minigames.wins_of(e, "scramble") or 0)})
    def best(key):
        r = [x for x in rows if x[key] > 0]
        r.sort(key=lambda x: (-x[key], x["n"].lower()))
        return r[:n]
    return {"all": [{"n": x["n"], "w": x["w"], "l": x["l"], "u": x["u"]} for x in best("w")],
            "l": [{"n": x["n"], "w": x["l"]} for x in best("l")], "u": [{"n": x["n"], "w": x["u"]} for x in best("u")]}


EXAMPLE_MAX = 100
ANNOUNCE_RE = re.compile(r"^/announce(?:blue|green|orange|purple)?\s+", re.IGNORECASE)
SAMPLES = {   # 1.13.0: what a reply looks like on the public page: variables become example values, in the app's language
    "en": {"user": "viewer", "touser": "sam", "query": "…", "querystring": "…", "count": "7", "game": "(the game)", "title": "(the stream title)",
           "uptime": "2h 15m", "viewers": "120", "followers": "(the follower count)", "follow": "1 year, 2 months", "followage": "1 year, 2 months",
           "followdate": "Jan 5, 2025", "accountage": "3 years, 4 months", "random.chatter": "(a random viewer)", "firststreak": "3",
           "weather": "(the weather in {a})", "time": "(the time in {a})", "eval": "(a calculated value)", "urlfetch": "(text from a website)",
           "act_game": "(moderators change the stream's game with it)", "act_title": "(moderators change the stream title with it)"},
    "ar": {"user": "مشاهد", "touser": "سامي", "query": "…", "querystring": "…", "count": "7", "game": "(اللعبة)", "title": "(عنوان البث)",
           "uptime": "2س 15د", "viewers": "120", "followers": "(عدد المتابعين)", "follow": "سنة وشهران", "followage": "سنة وشهران",
           "followdate": "5 يناير 2025", "accountage": "3 سنوات و4 أشهر", "random.chatter": "(مشاهد عشوائي)", "firststreak": "3",
           "weather": "(الطقس في {a})", "time": "(الوقت في {a})", "eval": "(قيمة محسوبة)", "urlfetch": "(نص من موقع)",
           "act_game": "(يغيّر به المشرفون لعبة البث)", "act_title": "(يغيّر به المشرفون عنوان البث)"},
}


def _fill(text: str, S: dict, channel: str, depth: int = 0) -> str:
    """$(...) -> example values, innermost first. $(eval ...) and $(urlfetch ...) are never shown as written (a link can hold
    a private key)."""
    out, i = [], 0
    while i < len(text):
        j = text.find("$(", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        k, d = j + 2, 1
        while k < len(text) and d:
            d += {"(": 1, ")": -1}.get(text[k], 0)
            k += 1
        if d:                                    # no closing bracket: leave the rest out
            break
        name, _, arg = text[j + 2:k - 1].strip().partition(" ")
        key = name.lower()
        if key in ("eval", "urlfetch"):
            out.append(S[key])
        else:
            arg = _fill(arg, S, channel, depth + 1).strip() if depth < 5 else ""
            if key == "channel":
                out.append(channel or "…")
            elif key in ("weather", "time"):
                out.append(S[key].replace("{a}", arg or "…"))
            elif key == "touser" and arg:
                out.append(arg.lstrip("@"))
            else:
                out.append(S.get(key, "…"))
        i = k
    return "".join(out)


def example(cmd: dict, lang: str = "en", channel: str = "") -> str:
    """1.13.0: a short example of what a command answers, for the public page."""
    S = SAMPLES["ar" if lang == "ar" else "en"]
    action = cmd.get("action", "text")
    if action in ("game", "title"):
        return S["act_" + action]
    text = ANNOUNCE_RE.sub("", str(cmd.get("response") or "").strip())
    text = " ".join(_fill(text, S, channel).split())
    text = re.sub(r"[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]", "", text)
    return text if len(text) <= EXAMPLE_MAX else text[:EXAMPLE_MAX - 1].rstrip() + "…"


def game_rows(games: dict) -> list:
    """1.13.0: the mini games' chat commands of the games that are switched on (the website shows them in their own group;
    it words what each one does from "game" + "what")."""
    from . import minigames
    games = games or {}
    out = []
    on = [g for g in ("letters", "scramble") if (games.get(g) or {}).get("enabled")]
    perm = lambda who: who if who in ("everyone", "subscriber", "vip", "moderator") else "moderator"
    for g in on:
        cfg = games[g]
        out += [{"name": n, "perm": perm(cfg.get("who_starts")), "game": g, "what": "start"} for n in minigames.aliases(cfg.get("start_cmd"))]
        if g == "letters":
            out += [{"name": n, "perm": "moderator", "game": g, "what": "approve"} for n in minigames.aliases(cfg.get("approve_cmd"))]
    if on:
        sh = games.get("shared") or {}
        out += [{"name": n, "perm": "everyone", "game": "shared", "what": "wins"} for n in minigames.aliases(sh.get("wins_cmd"))]
        out += [{"name": n, "perm": "everyone", "game": "shared", "what": "top"} for n in minigames.aliases(sh.get("top_cmd"))]
    return out


def build(commands, settings, wins=None, accent=None, games=None, lang: str = "en", channel: str = "") -> dict:
    """The data the website gets: switched-on commands that are not hidden, by name, with who can use them.
    1.13.0: with a short example of each reply ("ex", unless Commands > Public list says not to), the mini games' commands
    (game + what) and each built-in's key (the website words what it does)."""
    hidden = set((settings or {}).get("public_hidden") or [])
    examples = (settings or {}).get("public_examples", True)
    out = []
    for name in sorted(commands or {}, key=lambda n: (n.lower(), n)):
        c = commands[name]
        if not isinstance(c, dict) or c.get("enabled") is False or name in hidden or c.get("action") == "pinfirst":
            continue
        row = {"name": name, "perm": manage.effective_permission(c)}
        if examples:
            ex = example(c, lang, channel)
            if ex:
                row["ex"] = ex
        out.append(row)
    # 1.12.0: the built-in commands that are switched on, marked as built-in (the website shows them in their own group).
    # Who can use them: everyone can ask (!settitle / !setgame with nothing after it show the title / game), only moderators
    # change things (!cmadd, !cmedit, !cmdel, and !settitle / !setgame with text).
    off = set((settings or {}).get("disabled_builtins") or [])
    for key, perm in BUILTIN_PUBLIC:
        if key in off:
            continue
        names = ["app?", "برنامج؟"] if key == "app" else [manage.BUILTIN_PREFIX + manage.BUILTIN_NAMES[key]]
        out.extend({"name": n, "perm": perm, "builtin": True, "key": key} for n in names)
    taken = {r["name"] for r in out}
    out.extend(r for r in game_rows(games) if r["name"] not in taken and r["name"] not in hidden)
    payload = {"v": FORMAT, "commands": out[:MAX_COMMANDS]}
    a = str(accent or "").strip().lower()
    if HEX_RE.match(a):
        payload["accent"] = a                    # 1.13.0: the page in the streamer's own color
    if wins is not None and (settings or {}).get("public_leaderboard", True):
        payload["leaderboard"] = leaderboard(wins)   # 1.13.0: viewers' names + wins (Commands > Public list can hide it)
    return payload


def digest(payload: dict, login: str) -> str:
    raw = json.dumps([login, payload], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def http_send(method: str, token: str, payload, path: str = "/api/list"):
    """(HTTP status, JSON body, Retry-After seconds or None). Status 0 = the website could not be reached."""
    headers = {"Authorization": f"OAuth {token}", "User-Agent": f"FQPN-Chat-Bot/{VERSION}"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as s:
            async with s.request(method, SITE + path, headers=headers, json=payload) as r:
                try:
                    body = await r.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    body = {}
                retry = r.headers.get("Retry-After")
                return r.status, body if isinstance(body, dict) else {}, int(retry) if retry and retry.isdigit() else None
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return 0, {}, None


class Syncer:
    """Runs for as long as the app runs. One pass (step) at a time, so it can be tested without a network."""

    def __init__(self, store, state, send=None, clock=time.time):
        self.store, self.state = store, state
        self.send = send or http_send
        self.clock = clock
        self.wake = asyncio.Event()
        self.pending = None          # (digest, first seen) of a list that has not been sent yet
        self.fails = 0
        self.next_try = 0.0
        self.status = {"state": "off", "url": "", "error": "", "at": None}
        state["publist"] = self.status
        state["publist_wake"] = self.wake

    def set(self, kind: str, url: str = "", error: str = "", at=None) -> None:
        self.status.update(state=kind, url=url, error=error, at=at)

    def sync_now(self) -> None:
        """The "Try again" button: no more waiting for a retry."""
        self.next_try = 0.0
        if self.pending:
            self.pending = (self.pending[0], 0.0)
        self.wake.set()

    def _failed(self, kind: str, error: str, retry_after=None) -> None:
        wait = RETRY[min(self.fails, len(RETRY) - 1)]
        if retry_after:
            wait = max(wait, min(int(retry_after), 3600))
        self.fails += 1
        self.next_try = self.clock() + wait
        self.set(kind, error=error)

    def _remember(self, **kw) -> None:
        saved = dict(self.store.get("publist_state") or {})
        saved.update(kw)
        self.store.save("publist_state", saved)

    async def step(self) -> None:
        if not SITE:
            self.set("nosite")
            return
        settings = self.store.get("settings") or {}
        saved = self.store.get("publist_state") or {}
        token = ((auth.load_token() or {}).get("access_token")) or ""
        login = self.state.get("account") or ""
        now = self.clock()

        if not settings.get("public_list"):
            self.pending = None
            if saved.get("uploaded") and token and login and saved.get("login") == login:
                # switched off: take the list off the website too (once it can be reached)
                if now < self.next_try:
                    return
                code, body, retry = await self.send("DELETE", token, None)
                if code in (200, 204, 404):
                    self.fails, self.next_try = 0, 0.0
                    self._remember(uploaded=False, digest="")
                elif code == 0:
                    self._failed("off", "offline", retry)
                    return
                else:
                    self._failed("off", str(body.get("error") or code), retry)
                    return
            self.set("off")
            return

        if not token or not login:
            self.set("login")
            return
        ui = self.store.get("ui") or {}
        # 1.13.0: the mini games' commands only go to a website that said it shows them in their own group. An older
        # website would drop their mark and file them among the streamer's own commands ("Everyone").
        site_ok = saved.get("features_site") == SITE and "games" in (saved.get("features") or [])
        payload = build(self.store.get("commands"), settings, self.store.get("game_wins"), ui.get("accent"), self.store.get("games") if site_ok else None,
                        "ar" if ui.get("language") == "ar" else "en", str(self.state.get("account") or ""))
        d = digest(payload, login)
        # 1.10.1: also the SAME website. After the address changes (a new domain, a new Cloudflare account with an empty
        # database) the list is sent again once, instead of "already uploaded" forever.
        if saved.get("uploaded") and saved.get("digest") == d and saved.get("login") == login and saved.get("site") == SITE:
            self.pending = None
            self.set("ok", url=page_url(login), at=saved.get("at"))
            return
        if self.pending is None or self.pending[0] != d:
            self.pending = (d, now)          # changed: wait until it stops changing
            if self.status["state"] not in ("error", "login", "offline"):
                self.set("waiting")
            return
        if now - self.pending[1] < SETTLE or now < self.next_try:
            return
        self.set("saving")
        code, body, retry = await self.send("PUT", token, payload)
        if code == 200 and body.get("ok"):
            who = str(body.get("login") or login)
            self.fails, self.next_try, self.pending = 0, 0.0, None
            feats = [str(f) for f in (body.get("features") or []) if isinstance(f, str)][:20]
            self._remember(uploaded=True, digest=d, login=login, at=int(now), site=SITE, features=feats, features_site=SITE)
            if "games" in feats and not site_ok:
                self.wake.set()          # the website can show them: send the list again with the mini games' commands
            self.set("ok", url=page_url(who), at=int(now))
        elif code == 0:
            self._failed("offline", "offline", retry)
        elif code == 401:
            self._failed("login", str(body.get("error") or "Twitch did not accept the login."), retry)
        else:
            self._failed("error", str(body.get("error") or f"The website answered {code}."), retry)

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Public command list: a sync pass failed")
            try:
                await asyncio.wait_for(self.wake.wait(), CHECK_EVERY)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()
