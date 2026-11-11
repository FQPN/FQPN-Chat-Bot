"""1.18.0: the Twitch panel ("FQPN Leaderboard", a panel extension under the stream).

The app sends the channel's leaderboards to the website (PUT /api/panel, the same Twitch login check as the public list);
the panel on Twitch reads them from there by the channel's ID. Only while Commands > Share > Twitch panel is on (off by
default); switching it off takes them off the website.

What is sent: for Watch time and Messages the top 100 of this week, this month and all time; for the mini games and First
in chat the top 10 (from the app's own data); each row is [the viewer's Twitch ID (or "@login"), their name, the number].
Plus the viewers' Twitch profile pictures (their public addresses), the app's language and accent color. Nothing else."""
import asyncio
import hashlib
import json
import logging
import re
import time

import aiohttp

from . import auth, minigames, pinfirst, publiclist
from . import viewerstats

log = logging.getLogger("twitchbot.panel")

FORMAT = 1
CHECK_EVERY = 60          # seconds between looks
SEND_GAP = 300            # the boards change all the time while live: sent at most every 5 minutes (a switch-on: at once)
TOP_BIG, TOP_SMALL = 100, 10
AVATAR_DAYS = 7           # a viewer's picture is looked up again after a week
AVATAR_RE = re.compile(r"^https://static-cdn\.jtvnw\.net/[A-Za-z0-9_\-./%]+$")
NUM_RE = re.compile(r"^\d{1,20}$")
RETRY = (60, 120, 300, 600, 1800)


def _rows(items, n):
    return [[str(k)[:40], str(name)[:40], int(v)] for k, name, v in items[:n] if int(v) > 0]


def _key(k: str, login: str) -> str:
    return k if NUM_RE.match(str(k)) else "@" + str(login or "").lower()


def boards(vstats_data: dict, wins: dict, first_state: dict, now=None) -> dict:
    """The four leaderboards: "t" (watch time, seconds), "m" (messages), "g" (mini game wins), "f" (First in chat)."""
    users = (vstats_data or {}).get("users") or {}
    out = {}
    for kind in ("t", "m"):
        b = {}
        for p in (None, "week", "month"):
            items = [(_key(k, e.get("l")), e.get("n") or e.get("l") or "?", viewerstats.value(e, kind, p, now))
                     for k, e in users.items() if isinstance(e, dict)]
            items = [x for x in items if x[2] > 0]
            items.sort(key=lambda x: (-x[2], str(x[1]).lower()))
            b[p or "all"] = _rows(items, TOP_BIG)
        out[kind] = b
    g = {}
    for p in (None, "week", "month"):
        items = [(str(uid), e.get("name") or "?", minigames.wins_of(e, None, p, now)) for uid, e in (wins or {}).items() if isinstance(e, dict)]
        items = [x for x in items if x[2] > 0]
        items.sort(key=lambda x: (-x[2], str(x[1]).lower()))
        g[p or "all"] = _rows(items, TOP_SMALL)
    out["g"] = g
    fb = pinfirst.boards(first_state, TOP_SMALL)
    out["f"] = {"peak": _rows([("@" + l, n, v) for l, n, v in fb["peak"]], TOP_SMALL),
                "count": _rows([("@" + l, n, v) for l, n, v in fb["count"]], TOP_SMALL),
                "now": ["@" + fb["now"][0], fb["now"][1][:40], int(fb["now"][2])] if fb["now"] else None}
    return out


def wanted_pictures(b: dict) -> set:
    keys = set()
    for kind, per in b.items():
        for rows in (per.values() if isinstance(per, dict) else []):
            if isinstance(rows, list) and rows and isinstance(rows[0], list):
                keys.update(r[0] for r in rows[:10])       # (pictures for the rows the panel can show at a glance)
            elif isinstance(rows, list) and rows and isinstance(rows[0], str):
                keys.add(rows[0])                          # f.now
    return keys


def build(b: dict, pictures: dict, lang: str, accent: str, login: str) -> dict:
    a = str(accent or "").strip().lower()
    av = {k: pictures[k][0] for k in wanted_pictures(b) if isinstance(pictures.get(k), list) and pictures[k] and pictures[k][0]}
    return {"v": FORMAT, "lang": "ar" if lang == "ar" else "en", "accent": a if publiclist.HEX_RE.match(a) else "",
            "login": str(login or "").lower(), "b": b, "av": av}


def digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


async def lookup_pictures(keys, token: str) -> dict:
    """Twitch profile pictures for IDs and "@login"s: {key: url} (whoever Twitch doesn't know is left out)."""
    ids = [k for k in keys if NUM_RE.match(k)][:500]
    logins = [k[1:] for k in keys if k.startswith("@") and re.match(r"^[a-z0-9_]{1,25}$", k[1:])][:500]
    out = {}
    headers = {"Authorization": f"Bearer {token}", "Client-Id": auth.CLIENT_ID}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            for field, vals, pre in (("id", ids, ""), ("login", logins, "@")):
                for i in range(0, len(vals), 100):
                    async with s.get("https://api.twitch.tv/helix/users", params=[(field, v) for v in vals[i:i + 100]], headers=headers) as r:
                        if r.status != 200:
                            return out
                        for u in (await r.json()).get("data") or []:
                            url = str(u.get("profile_image_url") or "")
                            if AVATAR_RE.match(url):
                                out[pre + (str(u.get("id")) if not pre else str(u.get("login") or "").lower())] = url
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        pass
    return out


class Syncer:
    """Runs next to the public list's syncer, for as long as the app runs."""

    def __init__(self, store, state, send=None, pictures=None, clock=time.time):
        self.store, self.state = store, state
        self.send = send or publiclist.http_send
        self.pictures = pictures or lookup_pictures
        self.clock = clock
        self.fails, self.next_try, self.last_put = 0, 0.0, 0.0
        self.status = {"state": "off", "at": None, "error": ""}
        state["panel_status"] = self.status
        self.wake = asyncio.Event()
        state["panel_wake"] = self.wake

    def _vdata(self) -> dict:
        b = self.state.get("bot")
        vs = getattr(b, "vstats", None) if b is not None else None
        return vs.data if vs is not None else (self.store.get("viewer_stats") or {})

    def _remember(self, **kw) -> None:
        st = dict(self.store.get("panel_state") or {})
        st.update(kw)
        self.store.save("panel_state", st)

    def _failed(self, error: str, retry=None) -> None:
        wait = RETRY[min(self.fails, len(RETRY) - 1)]
        if retry:
            wait = max(wait, min(int(retry), 3600))
        self.fails += 1
        self.next_try = self.clock() + wait
        self.status.update(state="error", error=error)

    async def step(self) -> None:
        if not publiclist.SITE:
            return
        now = self.clock()
        on = bool((self.store.get("panel") or {}).get("on"))
        saved = self.store.get("panel_state") or {}
        token = ((auth.load_token() or {}).get("access_token")) or ""
        login = str(self.state.get("account") or "").lower()
        if not token or not login:
            self.status.update(state="login" if on else "off")
            return
        if now < self.next_try:
            return
        if not on:
            if saved.get("sent") and saved.get("site") == publiclist.SITE:
                code, body, retry = await self.send("DELETE", token, None, "/api/panel")
                if code in (200, 204, 404):
                    self.fails = 0
                    self._remember(sent=False, digest="")
                else:
                    self._failed(str((body or {}).get("error") or code), retry)
                    return
            self.status.update(state="off", error="")
            return
        b = boards(self._vdata(), self.store.get("game_wins") or {}, self.store.get("first_state") or {}, now)
        pics = dict(saved.get("pictures") or {})
        need = [k for k in wanted_pictures(b) if not (isinstance(pics.get(k), list) and len(pics[k]) == 2 and now - float(pics[k][1] or 0) < AVATAR_DAYS * 86400)]
        if need:
            found = await self.pictures(need, token)
            for k in need:
                pics[k] = [found.get(k, ""), int(now)]
            if len(pics) > 3000:                    # (old ones go: the newest looked-up stay)
                pics = dict(sorted(pics.items(), key=lambda kv: -float(kv[1][1] or 0))[:2000])
            self._remember(pictures=pics)
        ui = self.store.get("ui") or {}
        payload = build(b, pics, "ar" if ui.get("language") == "ar" else "en", ui.get("accent"), login)
        d = digest(payload)
        if saved.get("sent") and saved.get("digest") == d and saved.get("site") == publiclist.SITE and saved.get("login") == login:
            self.status.update(state="ok", at=saved.get("at"), error="")
            return
        first = not (saved.get("sent") and saved.get("site") == publiclist.SITE and saved.get("login") == login)
        if not first and now - self.last_put < SEND_GAP:
            return
        code, body, retry = await self.send("PUT", token, payload, "/api/panel")
        if code == 200 and (body or {}).get("ok"):
            self.fails, self.last_put = 0, now
            self._remember(sent=True, digest=d, site=publiclist.SITE, login=login, at=int(now))
            self.status.update(state="ok", at=int(now), error="")
        elif code == 0:
            self._failed("offline", retry)
        elif code in (404, 405):
            self._failed("site", 3600)              # the website doesn't know the panel yet (not updated): in an hour
        else:
            self._failed(str((body or {}).get("error") or code), retry)

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Twitch panel: a pass failed")
            try:
                await asyncio.wait_for(self.wake.wait(), CHECK_EVERY)
                self.next_try = 0.0              # switched on / off in the app: try at once, not after the wait
                self.last_put = 0.0
            except asyncio.TimeoutError:
                pass
            self.wake.clear()
