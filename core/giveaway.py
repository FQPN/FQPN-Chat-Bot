"""Giveaways (1.13.0), like Nightbot's (without regulars). Three types:

  active   draw a random person who wrote in chat in the last N minutes (optionally only since the giveaway started)
  keyword  Open -> viewers type the word (like !join) to enter, once each -> Close -> Draw
  number   the bot picks a secret number in a range; the first viewer who types it wins (it closes by itself)

Who can enter: a user level (everyone / subscriber / vip / moderator), followers only (checked with Twitch when drawing),
subscriber luck 1x-5x (a sub counts that many times). Never: the bot, the streamer, people on the Blocklist.
After a draw the winner's chat messages are collected (so the streamer sees they are really there); Reroll draws someone
else, never the same person twice in one giveaway. The last 20 winners are kept.

Everything is in the store, so an app restart in the middle of a giveaway loses nothing:
  "giveaway": {"settings": {...}, "type", "status": idle|open|closed, "id", "started", "closes_at", "entries": {login: {...}},
               "secret", "winner": {...} | None, "past": [logins already drawn]}
  "giveaway_winners": [{"name", "login", "type", "at"}]   (newest first, at most 20)

The bot passed in is the real one (TwitchBot) or the Test chat's pretend one (practice): the same code runs both."""

import random
import secrets
import time

LEVELS = {"everyone": 0, "subscriber": 1, "vip": 2, "moderator": 3}
TYPES = ("active", "keyword", "number")
WINDOWS = (5, 10, 15, 30, 60)
MAX_ENTRIES = 5000
MAX_WINNER_MSGS = 20
KEEP_WINNERS = 20
DEFAULT_SETTINGS = {"type": "keyword", "window": 10, "since_start": False, "keyword": "!join", "auto_close": 0, "min": 1, "max": 100,
                    "level": "everyone", "followers": False, "sub_luck": 1, "announce": True, "say_winner": True,
                    "open_text": "", "close_text": "", "win_text": ""}
TEXTS = {   # "" in the settings = these, in the app's language (like the stream messages)
    "en": {"open_keyword": "🎉 Giveaway open! Type {keyword} in chat to join.",
           "open_number": "🔢 Guess the number between {min} and {max}! The first right guess wins.",
           "close": "⏹️ Entries are closed! {count} joined. Good luck!",
           "win": "🎉 {winner} won the giveaway! Congratulations!",
           "win_number": "🎯 {winner} guessed the number {number} and won the giveaway!"},
    "ar": {"open_keyword": "🎉 السحب مفتوح! اكتب {keyword} في الدردشة للمشاركة.",
           "open_number": "🔢 خمّن الرقم بين {min} و{max}! أول تخمين صحيح يفوز.",
           "close": "⏹️ أُغلقت المشاركة! شارك {count}. بالتوفيق!",
           "win": "🎉 {winner} فاز بالسحب! مبروك!",
           "win_number": "🎯 {winner} خمّن الرقم {number} وفاز بالسحب!"},
}


class GiveawayError(Exception):
    """A clear message for the page (code: a key the page words in the user's language)."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _fresh(settings=None) -> dict:
    return {"settings": dict(DEFAULT_SETTINGS, **(settings or {})), "type": (settings or {}).get("type", "keyword"), "status": "idle", "id": "",
            "started": 0, "closes_at": 0, "entries": {}, "secret": None, "winner": None, "past": []}


def load(store) -> dict:
    g = store.get("giveaway")
    if not isinstance(g, dict) or "settings" not in g:
        g = _fresh()
    base = _fresh(g.get("settings"))
    base.update({k: v for k, v in g.items() if k in base})
    base["settings"] = dict(DEFAULT_SETTINGS, **(g.get("settings") or {}))
    return base


def save(store, g) -> None:
    store.save("giveaway", g)


def clean_settings(raw: dict, old: dict) -> dict:
    """The settings the page sends, checked. Raises GiveawayError with a clear reason."""
    if not isinstance(raw, dict):
        raise GiveawayError("bad", "Settings must be an object.")
    s = dict(old)
    if "type" in raw:
        if raw["type"] not in TYPES:
            raise GiveawayError("bad", "Unknown giveaway type.")
        s["type"] = raw["type"]
    if "window" in raw:
        if raw["window"] not in WINDOWS or isinstance(raw["window"], bool):
            raise GiveawayError("bad", "Pick 5, 10, 15, 30 or 60 minutes.")
        s["window"] = int(raw["window"])
    if "keyword" in raw:
        kw = " ".join(str(raw["keyword"] or "").split())
        if not kw or len(kw) > 30:
            raise GiveawayError("keyword", "The keyword must be 1 to 30 characters.")
        s["keyword"] = kw
    for k, lo, hi in (("auto_close", 0, 240), ("min", 0, 1_000_000), ("max", 1, 1_000_000), ("sub_luck", 1, 5)):
        if k in raw:
            v = raw[k]
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                if k in ("min", "max"):
                    raise GiveawayError("range", f"The numbers must be from 0 to 1,000,000, and the highest bigger than the lowest.")
                raise GiveawayError(k, f"{k} must be a whole number from {lo} to {hi}.")
            s[k] = v
    if s["max"] <= s["min"]:
        raise GiveawayError("range", "The highest number must be bigger than the lowest.")
    if s["max"] - s["min"] > 1_000_000:
        raise GiveawayError("range", "The range is too big.")
    if "level" in raw:
        if raw["level"] not in LEVELS:
            raise GiveawayError("bad", "Unknown user level.")
        s["level"] = raw["level"]
    for k in ("since_start", "followers", "announce", "say_winner"):
        if k in raw:
            if not isinstance(raw[k], bool):
                raise GiveawayError("bad", f"{k} must be on or off.")
            s[k] = raw[k]
    for k in ("open_text", "close_text", "win_text"):
        if k in raw:
            v = " ".join(str(raw[k] or "").split())
            if len(v) > 400:
                raise GiveawayError("text", "A message can be at most 400 characters.")
            s[k] = v
    return s


def norm(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _lang(store) -> str:
    return "ar" if (store.get("ui") or {}).get("language") == "ar" else "en"


def text_for(store, g, key: str, **values) -> str:
    s = g["settings"]
    own = {"open_keyword": s["open_text"], "open_number": s["open_text"], "close": s["close_text"], "win": s["win_text"], "win_number": s["win_text"]}[key]
    out = own or TEXTS[_lang(store)][key]
    for k, v in values.items():
        out = out.replace("{" + k + "}", str(v))
    return out[:500]


def _excluded(store, bot) -> set:
    blocked = {u.lower() for u in (store.get("blocklist") or {}).get("users", [])}
    me = str((getattr(bot, "account", None) or {}).get("login", "")).lower()
    sender = str(getattr(getattr(bot, "sender", None), "login", "") or "").lower()
    return blocked | {me, sender} - {""}


def eligible_level(g, level: int) -> bool:
    return level >= LEVELS[g["settings"]["level"]]


def pool(store, g, bot) -> list:
    """Everyone who can win right now: [(login, name, user_id, sub)]."""
    out, now, skip = [], time.time(), _excluded(store, bot) | set(g["past"])
    if g["type"] == "active":
        since = max(now - g["settings"]["window"] * 60, g["started"] if g["settings"]["since_start"] else 0)
        info = getattr(bot, "_chat_info", {}) if bot is not None else {}
        for login, v in list(getattr(bot, "_chatters", {}).items() if bot is not None else []):
            lv, sub, uid = info.get(login, (0, False, ""))
            if v[0] >= since and login not in skip and eligible_level(g, lv):
                out.append((login, v[1], uid, sub))
    else:
        for login, e in g["entries"].items():
            if login not in skip:
                out.append((login, e["name"], e.get("id", ""), bool(e.get("sub"))))
    return out


def weighted_pick(people: list, luck: int, rng=random):
    """Subscriber luck: a sub counts `luck` times."""
    if not people:
        return None
    weights = [luck if p[3] else 1 for p in people]
    return rng.choices(people, weights=weights, k=1)[0]


# ---------------------------------------------------------------- the page's actions

async def start(store, bot, kind: str) -> dict:
    """A new giveaway of this type (entries, winner and rerolls start empty). Keyword / number: open at once (+ announce)."""
    if kind not in TYPES:
        raise GiveawayError("bad", "Unknown giveaway type.")
    old = load(store)
    g = _fresh(dict(old["settings"], type=kind))
    g.update(type=kind, id=secrets.token_hex(4), started=time.time(), status="open")
    s = g["settings"]
    if kind == "number":
        g["secret"] = random.randint(s["min"], s["max"])
    if kind == "keyword" and s["auto_close"]:
        g["closes_at"] = time.time() + s["auto_close"] * 60
    save(store, g)
    if kind != "active" and s["announce"] and bot is not None:
        key = "open_keyword" if kind == "keyword" else "open_number"
        await bot._send(text_for(store, g, key, keyword=s["keyword"], min=s["min"], max=s["max"]), why="giveaway", user="")
    return g


async def close(store, bot, auto: bool = False) -> dict:
    g = load(store)
    if g["status"] != "open":
        return g
    g["status"], g["closes_at"] = "closed", 0
    save(store, g)
    if g["type"] == "keyword" and g["settings"]["announce"] and bot is not None:
        await bot._send(text_for(store, g, "close", count=len(g["entries"])), why="giveaway", user="")
    return g


async def draw(store, bot, followed=None) -> dict:
    """Draws a winner (a reroll when there already is one: never someone already drawn). `followed(user_id)` -> bool | None
    checks followers-only (None = couldn't tell: they count). Raises GiveawayError("empty") when nobody can win."""
    g = load(store)
    if g["status"] == "idle":
        raise GiveawayError("idle", "Start a giveaway first.")
    if g["type"] == "number":
        raise GiveawayError("number", "In a random number giveaway, the first right guess wins.")
    if g["type"] == "keyword" and g["status"] == "open":
        g = await close(store, bot)
    people = pool(store, g, bot)
    winner = None
    while people:
        p = weighted_pick(people, g["settings"]["sub_luck"])
        if g["settings"]["followers"] and followed is not None and p[2]:
            try:
                ok = await followed(p[2])
            except Exception:
                ok = None
            if ok is False:
                people = [x for x in people if x[0] != p[0]]
                continue
        winner = p
        break
    if winner is None:
        raise GiveawayError("empty", "Nobody can win: no one entered (or everyone was already drawn).")
    return await _won(store, bot, g, winner)


async def _won(store, bot, g, p, number=None) -> dict:
    login, name = p[0], p[1]
    g["winner"] = {"login": login, "name": name, "at": time.time(), "messages": [], "number": number}
    g["past"] = (g["past"] + [login])[-200:]
    if g["type"] == "number":
        g["status"] = "closed"
    save(store, g)
    hist = [{"name": name, "login": login, "type": g["type"], "at": time.time()}] + list(store.get("giveaway_winners") or [])
    store.save("giveaway_winners", hist[:KEEP_WINNERS])
    if g["settings"]["say_winner"] and bot is not None:
        key = "win_number" if number is not None else "win"
        await bot._send(text_for(store, g, key, winner=name, number=number if number is not None else ""), why="giveaway", user=name)
    return g


def remove(store, login: str) -> dict:
    g = load(store)
    g["entries"].pop(str(login).lower(), None)
    save(store, g)
    return g


def clear(store) -> dict:
    """Ends this giveaway (the settings and the winners list stay)."""
    g = _fresh(load(store)["settings"])
    g["type"] = g["settings"]["type"]
    save(store, g)
    return g


def update_settings(store, raw) -> dict:
    g = load(store)
    g["settings"] = clean_settings(raw, g["settings"])
    if g["status"] == "idle":
        g["type"] = g["settings"]["type"]
    save(store, g)
    return g


async def tick(store, bot) -> None:
    """Closes a keyword giveaway when its time is up."""
    g = load(store)
    if g["status"] == "open" and g["closes_at"] and time.time() >= g["closes_at"]:
        await close(store, bot, auto=True)


# ---------------------------------------------------------------- chat

async def on_message(store, bot, login: str, name: str, user_id: str, level: int, sub: bool, text: str) -> bool:
    """A chat message. Enters a keyword giveaway, wins a number giveaway, or is kept as the winner's message.
    True when it was a winning guess (the caller sends nothing else for it)."""
    g = load(store)
    if not g["status"] or g["status"] == "idle":
        return False
    login = login.lower()
    changed = False
    w = g.get("winner")
    if w and w.get("login") == login:
        w["messages"] = (w.get("messages", []) + [{"t": time.time(), "text": str(text)[:300]}])[-MAX_WINNER_MSGS:]
        changed = True
    if g["status"] == "open" and login not in _excluded(store, bot) and eligible_level(g, level):
        if g["type"] == "keyword" and norm(text) == norm(g["settings"]["keyword"]) and login not in g["entries"]:
            if len(g["entries"]) < MAX_ENTRIES:
                g["entries"][login] = {"name": name, "id": str(user_id or ""), "sub": bool(sub), "at": time.time()}
                changed = True
        elif g["type"] == "number":
            t = str(text).strip()
            if t.lstrip("-").isdigit() and len(t) <= 8:
                if login not in g["entries"] and len(g["entries"]) < MAX_ENTRIES:     # who played (the page shows how many guessed)
                    g["entries"][login] = {"name": name, "id": str(user_id or ""), "sub": bool(sub), "at": time.time()}
                    changed = True
                if int(t) == g["secret"]:
                    await _won(store, bot, g, (login, name, user_id, sub), number=g["secret"])
                    return True
    if changed:
        save(store, g)
    return False


def view(store, g, bot, show_secret: bool = False) -> dict:
    """What the page shows."""
    out = {k: g[k] for k in ("type", "status", "id", "started", "closes_at", "winner", "settings")}
    out["entries"] = sorted(({"login": k, "name": v["name"], "sub": bool(v.get("sub")), "at": v.get("at", 0)} for k, v in g["entries"].items()),
                            key=lambda e: -e["at"])[:500]
    out["count"] = len(g["entries"])
    out["eligible"] = len(pool(store, g, bot)) if g["type"] == "active" and g["status"] != "idle" else None
    if g["type"] == "active" and g["status"] == "idle":
        tmp = dict(g, started=time.time())
        out["eligible"] = len(pool(store, tmp, bot))
    out["secret"] = g["secret"] if show_secret else None
    out["has_secret"] = g["secret"] is not None
    out["drawn"] = len(g["past"])
    out["winners"] = list(store.get("giveaway_winners") or [])[:KEEP_WINNERS]
    out["connected"] = bot is not None
    out["now"] = time.time()
    return out
