"""1.18.0: the Chat box overlay: your Twitch chat on stream, view only (nothing can be sent from it).

It lives on the Overlays page and is part of the same overlay link as the counters and First in chat (core/overlays.py).
You drag it and pull its corners to place and size it there; everything else is in its settings (the "chatbox" section).

The bot puts every chat message it sees into one list kept in memory (ChatBuffer, at most MAX_KEEP): who wrote it, its
Twitch badges, its parts (text, Twitch / 7TV / BTTV / FFZ emotes, mentions, links), and what the app knows about the person
(mini game wins, first in chat streak, follow anniversary, first message ever). The bot's answer to a command is attached
to the message that asked for it. Deleted messages and the messages of someone timed out or banned are marked deleted.
Nothing is written to disk: a restart starts with an empty chat box.

view() turns the list into what the overlay draws, with the settings applied (hide bots / people / blocklist, commands,
spam folding, mini game guesses folded into one line, deleted messages). The overlay asks for it about once a second.
"""
import re
import time
import logging
import unicodedata
from collections import deque

log = logging.getLogger(__name__)

SECTION = "chatbox"
MAX_KEEP = 250                      # messages kept in memory
DEFAULT_BOX = [1.5, 44.0, 24.0, 52.0]   # x, y, width, height in % of the screen (bottom-left, like most chat overlays)
SPAM_SECONDS = 20                   # the same message again within this many seconds: one line with a count
ECHO_SECONDS = 60

STYLES = ("neon", "classic", "bubbles", "glass", "cards", "fade")
FONTS_EN = ("same", "outfit", "inter", "poppins", "montserrat", "nunito", "lexend", "fredoka")   # 1.18.0: the English font ("same": the Arabic one)
FONTS = ("tajawal", "cairo", "plex", "kufi", "almarai", "readex", "rubik", "changa", "messiri", "baloo", "lalezar", "noto")
DEFAULTS = {
    "on": False, "hidden": False,
    # Look
    "style": "neon", "size": 22, "font": "tajawal", "font_en": "same", "glow": "soft", "outline": "thin", "shadow": "soft", "bg": "none",
    "name_color": "twitch", "pics": False, "names": "display",
    # Layout ("shape": a box of lines, or one line where messages move sideways)
    "shape": "box", "flow": "bottom", "max": 8, "spacing": 1.5, "lines": 3, "anim": "slide", "hide_after": 30, "fade_old": True,
    # What shows
    "commands": "with", "spam": True, "replies": True, "shared": "mark", "hide_bots": True, "hide_people": [],
    "use_blocklist": True, "links": "word", "max_chars": 200, "delay": 3,
    # Emotes and badges
    "emotes": ["twitch", "7tv", "bttv"], "emote_size": 1.5, "big_emotes": True, "badges": ["mod", "vip", "sub"],
    "app_badges": ["wins", "streak", "first", "anniv"],
    # Smart
    "attach": True, "fold_games": True, "deleted": "gone", "mention": False,
    # 1.18.0: viewers pick their own name color with !color #hex
    "own_colors": True, "own_colors_who": "everyone",
}
CHOICES = {
    "style": STYLES, "font": FONTS, "font_en": FONTS_EN, "glow": ("off", "soft", "strong"), "outline": ("off", "thin", "thick"),
    "shadow": ("off", "soft", "strong"), "bg": ("none", "soft", "dark"), "name_color": ("twitch", "accent", "white"),
    "names": ("display", "login", "both"), "flow": ("bottom", "top"), "anim": ("slide", "fade", "pop", "none"),
    "commands": ("with", "answer", "hide"), "shared": ("mark", "hide"), "links": ("show", "word", "hide"),
    "deleted": ("gone", "note"), "shape": ("box", "line"), "own_colors_who": ("everyone", "subs", "vips"),
}
NUMBERS = {   # key: (lowest, highest, whole number?)
    "size": (12, 48, True), "max": (2, 30, True), "spacing": (1.0, 2.4, False), "max_chars": (40, 500, True),
}
SETS = {"hide_after": (0, 15, 30, 60, 120), "lines": (0, 1, 2, 3), "delay": (0, 3, 5, 10), "emote_size": (1, 1.5, 2)}
LISTS = {"emotes": ("twitch", "7tv", "bttv", "ffz"), "badges": ("mod", "vip", "sub", "other"),
         "app_badges": ("wins", "streak", "first", "anniv")}
BOOLS = ("on", "hidden", "pics", "fade_old", "spam", "replies", "hide_bots", "use_blocklist", "big_emotes", "attach",
         "fold_games", "mention", "own_colors")
_LOGIN = re.compile(r"[a-z0-9_]{1,25}")


COLORS = "chat_colors"        # 1.18.0: {Twitch user ID: {"c": "#rrggbb", "l": login}} (its own file)
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
COLOR_LEVEL = {"everyone": 0, "subs": 1, "vips": 2}     # the lowest user level allowed (sub 1, VIP 2, mod 3, streamer 4)


def parse_hex(text: str) -> str:
    """«#00e5ff», «00E5FF», «#0ef» -> "#00e5ff"; anything else -> ""."""
    m = HEX_RE.match(str(text or "").strip())
    if not m:
        return ""
    h = m.group(1).lower()
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)


def readable(hexcolor: str) -> str:
    """A color dark enough to vanish on stream is made brighter (the same hue); others stay as they are."""
    h = parse_hex(hexcolor)
    if not h:
        return ""
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum >= 0.15:                 # (pure red or a deep purple stay as chosen: only near-black and deep blue get lighter)
        return h
    f = min(0.85, (0.15 - lum) / 0.15 * 0.5 + 0.25)
    return "#" + "".join(f"{round(c + (255 - c) * f):02x}" for c in (r, g, b))


def own_color(store, uid: str) -> str:
    e = (store.get(COLORS) or {}).get(str(uid or ""))
    return readable(e.get("c")) if isinstance(e, dict) else ""


def set_color(store, uid: str, login: str, color: str) -> None:
    """color "" = back to the Twitch color."""
    data = dict(store.get(COLORS) or {})
    if color:
        data[str(uid)] = {"c": color, "l": str(login or "").lower()[:25], "at": int(time.time())}
    else:
        data.pop(str(uid), None)
    store.save(COLORS, data, allow_empty=True)


def forget_login(store, login: str) -> None:
    """Every color kept under this login (a mod's «!color @name reset»)."""
    data = dict(store.get(COLORS) or {})
    keep = {k: v for k, v in data.items() if not (isinstance(v, dict) and v.get("l") == str(login or "").lower())}
    if len(keep) != len(data):
        store.save(COLORS, keep, allow_empty=True)


def clean_colors(raw) -> dict:
    """A backup's colors, checked."""
    out = {}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        c = parse_hex((v or {}).get("c") if isinstance(v, dict) else "")
        if c and re.fullmatch(r"\d{1,20}", str(k)):
            out[str(k)] = {"c": c, "l": str((v or {}).get("l") or "").lower()[:25]}
            if isinstance(v.get("at"), (int, float)) and v["at"] > 0:
                out[str(k)]["at"] = int(v["at"])
    return out


COLORS_LIVE = "chat_colors_live"
COLORS_RESET_AFTER = 1800      # the stream offline this long: the colors chosen up to then go


def colors_tick(store, live: bool, was_live: bool, now=None) -> int:
    """1.18.0: !color lasts one stream. Called at every live check: while live it notes the time (at most once a
    minute); 30 minutes after the stream ended, every color chosen before it ended goes (a short drop keeps them; a
    color chosen after the stream, for the next one, stays). Returns how many went."""
    now = time.time() if now is None else now
    st = dict(store.get(COLORS_LIVE) or {})
    if live:
        if now - float(st.get("seen") or 0) >= 60:
            st["seen"] = int(now)
            st.pop("ended", None)
            store.save(COLORS_LIVE, st)
        return 0
    if was_live:
        st["ended"] = int(now)
        store.save(COLORS_LIVE, st)
    end = float(st.get("ended") or st.get("seen") or 0)        # (the app closed while live: the last time it saw it live)
    if not end or now - end < COLORS_RESET_AFTER or float(st.get("done") or 0) >= end:
        return 0
    data = dict(store.get(COLORS) or {})
    keep = {k: v for k, v in data.items() if isinstance(v, dict) and float(v.get("at") or 0) > end}
    if len(keep) != len(data):
        store.save(COLORS, keep, allow_empty=True)
    st["done"] = int(end)
    store.save(COLORS_LIVE, st)
    return len(data) - len(keep)


def cfg_of(store) -> dict:
    """The settings, with anything missing or broken replaced by the default (never fails)."""
    return validate(store.get(SECTION) or {})


def box_of(store) -> list:
    """Where the chat box is and how big: [x, y, width, height] in % of the screen. Kept with the other overlays' places
    (the "counter_overlay" section, "chat_box"), so «Back to the corner» puts it back too."""
    b = _clean_box((store.get("counter_overlay") or {}).get("chat_box") or [])
    return b or list(DEFAULT_BOX)


def _clean_box(b):
    try:
        x, y, w, h = (float(v) for v in b)
    except (TypeError, ValueError):
        return None
    w, h = min(100.0, max(4.0, w)), min(100.0, max(4.0, h))
    x, y = min(100.0 - w, max(0.0, x)), min(100.0 - h, max(0.0, y))
    return [round(x, 2), round(y, 2), round(w, 2), round(h, 2)]


def validate(data) -> dict:
    """The saved settings: every key checked; an unknown or broken value goes back to its default (old files keep working)."""
    data = data if isinstance(data, dict) else {}
    out = {}
    for k, d in DEFAULTS.items():
        v = data.get(k, d)
        if k in BOOLS:
            out[k] = v if isinstance(v, bool) else d
        elif k in CHOICES:
            out[k] = v if v in CHOICES[k] else d
        elif k in NUMBERS:
            lo, hi, whole = NUMBERS[k]
            try:
                n = float(v)
                n = min(hi, max(lo, n))
                out[k] = int(round(n)) if whole else round(n, 2)
            except (TypeError, ValueError):
                out[k] = d
        elif k in SETS:
            out[k] = v if (not isinstance(v, bool) and v in SETS[k]) else d
        elif k in LISTS:
            out[k] = [x for x in LISTS[k] if isinstance(v, list) and x in v] if isinstance(v, list) else list(d)
        elif k == "hide_people":
            names = []
            for x in (v if isinstance(v, list) else [])[:200]:
                x = str(x or "").strip().lstrip("@").lower()
                if _LOGIN.fullmatch(x) and x not in names:
                    names.append(x)
            out[k] = names
        else:
            out[k] = d
    return out


def set_box(store, x, y, w, h) -> None:
    ov = dict(store.get("counter_overlay") or {})
    b = _clean_box([x, y, w, h])
    if b is None:
        ov.pop("chat_box", None)
    else:
        ov["chat_box"] = b
    store.save("counter_overlay", ov)


# ---------- emotes from 7TV, BTTV and FFZ (free, public; loaded by the bot, refreshed every hour) ----------

EMOTES = {"7tv": {}, "bttv": {}, "ffz": {}}
_EMOTES_AT = {"uid": None, "at": 0.0}


async def load_emotes(uid: str, session=None) -> None:
    """Fills EMOTES for the channel (its own emotes and the global ones). A service that doesn't answer keeps what it had."""
    import aiohttp
    if not uid or (_EMOTES_AT["uid"] == uid and time.time() - _EMOTES_AT["at"] < 3600):
        return
    _EMOTES_AT.update(uid=uid, at=time.time())
    own = session is None
    s = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))

    async def get(url):
        try:
            async with s.get(url) as r:
                return await r.json() if r.status == 200 else None
        except Exception:
            return None
    try:
        seven = {}
        for data in (await get("https://7tv.io/v3/emote-sets/global"), (await get(f"https://7tv.io/v3/users/twitch/{uid}") or {}).get("emote_set")):
            for e in (data or {}).get("emotes") or []:
                host = ((e.get("data") or {}).get("host") or {}).get("url") or ""
                if e.get("name") and host:
                    seven[e["name"]] = ("https:" + host if host.startswith("//") else host) + "/4x.webp"   # (the biggest: sharp at any size)
        if seven:
            EMOTES["7tv"] = seven
        bttv = {}
        ch = await get(f"https://api.betterttv.net/3/cached/users/twitch/{uid}") or {}
        for e in (await get("https://api.betterttv.net/3/cached/emotes/global") or []) + (ch.get("channelEmotes") or []) + (ch.get("sharedEmotes") or []):
            if isinstance(e, dict) and e.get("code") and e.get("id"):
                bttv[e["code"]] = f"https://cdn.betterttv.net/emote/{e['id']}/3x"
        if bttv:
            EMOTES["bttv"] = bttv
        ffz = {}
        for data in (await get("https://api.frankerfacez.com/v1/set/global"), await get(f"https://api.frankerfacez.com/v1/room/id/{uid}")):
            for st in ((data or {}).get("sets") or {}).values():
                for e in (st or {}).get("emoticons") or []:
                    urls = e.get("urls") or {}
                    u = urls.get("4") or urls.get("2") or urls.get("1") or ""
                    if e.get("name") and u:
                        ffz[e["name"]] = u if u.startswith("http") else "https:" + u
        if ffz:
            EMOTES["ffz"] = ffz
        log.info("Chat box: emotes loaded (7TV %d, BTTV %d, FFZ %d)", len(seven), len(bttv), len(ffz))
    except Exception:
        log.exception("Chat box: couldn't load the 7TV / BTTV / FFZ emotes")
    finally:
        if own:
            await s.close()


# ---------- turning a chat message into parts ----------

LINK = re.compile(r"(?i)\b(?:https?://\S+|www\.\S+|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|gg|tv|io|me|sa|co|ly|app|dev|xyz|ae|kw|qa|link|to|be)(?:/\S*)?)")


INVISIBLE = re.compile("[\U000E0000-\U000E007F\u034F\u200B-\u200D\u2060\uFEFF\u180E]")   # Twitch's "same message again" filler and other invisible marks


def _text_parts(text: str) -> list:
    """A plain text piece: links and 7TV / BTTV / FFZ emote names become their own parts."""
    out, buf = [], []
    text = INVISIBLE.sub("", text)
    for tok in re.split(r"(\s+)", text):
        if not tok:
            continue
        if tok.isspace():
            buf.append(tok)
            continue
        hit = None
        for src in ("7tv", "bttv", "ffz"):
            u = EMOTES[src].get(tok)
            if u:
                hit = ["e", tok, u, src]
                break
        if hit is None and LINK.fullmatch(tok):
            hit = ["l", tok]
        if hit:
            if buf:
                out.append(["t", "".join(buf)])
                buf = []
            out.append(hit)
        else:
            buf.append(tok)
    if buf:
        out.append(["t", "".join(buf)])
    return out


def parts_of(payload) -> list:
    """The message as parts: ["t", text] | ["e", name, url, source] | ["m", @name] | ["l", link]."""
    parts = []
    frags = getattr(payload, "fragments", None) or []
    if not frags:
        return _text_parts(str(getattr(payload, "text", "") or ""))
    for f in frags:
        kind, text = str(getattr(f, "type", "text") or "text"), str(getattr(f, "text", "") or "")
        if kind == "emote" and getattr(f, "emote", None) is not None:
            e = f.emote
            parts.append(["e", text, f"https://static-cdn.jtvnw.net/emoticons/v2/{e.id}/default/dark/3.0", "twitch"])
        elif kind == "mention":
            parts.append(["m", text])
        else:
            parts.extend(_text_parts(text))
    return parts


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", INVISIBLE.sub("", str(text or ""))).casefold()
    return " ".join(t.split())


BADGES = {}            # "set_id/version" -> picture URL: Twitch's global badges and your channel's own (loaded by the bot, every hour)


def badge_url(set_id: str, version: str = "1") -> str:
    return BADGES.get(f"{set_id}/{version}") or ""


def badge_samples() -> dict:
    """The real badge pictures for the made-up preview messages (your channel's sub badge when there is one)."""
    subs = sorted((k for k in BADGES if k.startswith("subscriber/")), key=lambda k: int(k.split("/")[1]) if k.split("/")[1].isdigit() else 9999)
    return {"mod": badge_url("moderator"), "vip": badge_url("vip"), "streamer": badge_url("broadcaster"),
            "sub": BADGES.get(subs[0], "") if subs else ""}


BADGE_GROUP = {"moderator": "mod", "lead_moderator": "mod", "vip": "vip", "subscriber": "sub", "founder": "sub"}
BADGE_OF = {"moderator": "mod", "lead_moderator": "mod", "vip": "vip", "subscriber": "sub", "founder": "sub",
            "broadcaster": "streamer", "partner": "partner", "premium": "prime", "turbo": "turbo", "staff": "staff",
            "artist-badge": "artist"}


class ChatBuffer:
    """The recent chat, in memory."""

    def __init__(self):
        self.items: deque = deque(maxlen=MAX_KEEP)
        self.by_id: dict = {}
        self.avatars: dict = {}            # login -> picture URL ("" = none)
        self.games: dict = {}              # round id -> {"game", "winner", "at"}
        self.seq = 0
        self.ver = 0                       # changes whenever something changes (the overlay redraws only then)

    def _touch(self, item=None):
        self.ver += 1
        if item is not None:
            item["rev"] = item.get("rev", 0) + 1

    def _put(self, item: dict) -> dict:
        self.seq += 1
        item.update(seq=self.seq, rev=1)
        if len(self.items) == self.items.maxlen:
            old = self.items[0]
            self.by_id.pop(old.get("id"), None)
        self.items.append(item)
        if item.get("id"):
            self.by_id[item["id"]] = item
        self._touch()
        return item

    def add(self, *, mid, login, name, uid="", color="", badges=(), parts=(), text="", first=False, shared=False,
            reply_to="", bot=False, mention=False, test=False, tb=()) -> dict:
        now = time.time()
        item = {"id": str(mid or f"x{self.seq + 1}"), "t": now, "login": str(login or "").lower(), "name": str(name or login or ""),
                "uid": str(uid or ""), "color": str(color or ""), "badges": [b for b in badges if b][:6],
                "parts": list(parts)[:120], "text": str(text or ""), "first": bool(first), "shared": bool(shared),
                "reply_to": str(reply_to or ""), "bot": bool(bot), "mention": bool(mention), "test": bool(test),
                "cmd": str(text or "").lstrip().startswith("!"), "answers": [], "deleted": False, "dup_of": None,
                "guess": None, "echo_of": None, "tb": [str(x) for x in tb][:8]}
        key = _norm(text)
        if key and not item["cmd"] and not bot:          # the same thing again from someone else: a spam copy
            for old in reversed(self.items):
                if now - old["t"] > SPAM_SECONDS:
                    break
                if old.get("dup_of") is None and not old["bot"] and not old["cmd"] and _norm(old["text"]) == key:   # (the same person again too)
                    item["dup_of"] = old["id"]
                    break
        if bot:
            for old in reversed(self.items):             # the bot's own message that answered a command: attached there
                if now - old["t"] > ECHO_SECONDS:
                    break
                if any(_norm(a) == key for a in old.get("answers") or []) and not old.get("echoed"):
                    item["echo_of"] = old["id"]
                    old["echoed"] = True
                    break
        return self._put(item)

    def attach(self, mid, text: str) -> None:
        """The bot answered this message (a command): the answer goes under it."""
        it = self.by_id.get(str(mid or ""))
        text = str(text or "").strip()
        if it is None or not text:
            return
        it["answers"] = (it.get("answers") or [])[-2:] + [text[:500]]
        key, now = _norm(text), time.time()
        for old in reversed(self.items):                 # its echo may have arrived first
            if now - old["t"] > ECHO_SECONDS:
                break
            if old["bot"] and old.get("echo_of") is None and _norm(old["text"]) == key:
                old["echo_of"] = it["id"]
                it["echoed"] = True
                self._touch(old)
                break
        self._touch(it)

    def delete(self, mid) -> None:
        it = self.by_id.get(str(mid or ""))
        if it is not None and not it["deleted"]:
            it["deleted"] = True
            self._touch(it)

    def clear_user(self, login) -> None:
        login = str(login or "").lower()
        for it in self.items:
            if it["login"] == login and not it["deleted"]:
                it["deleted"] = True
                self._touch(it)

    def clear_all(self) -> None:
        for it in self.items:
            if not it["deleted"]:
                it["deleted"] = True
                self._touch(it)

    def guess(self, mid, rid, game: str) -> None:
        """A mini game answer (right or wrong): folded into the round's one line."""
        it = self.by_id.get(str(mid or ""))
        if it is None:
            return
        it["guess"] = str(rid)
        self.games.setdefault(str(rid), {"game": game, "winner": "", "at": time.time()})
        if len(self.games) > 40:
            for k in list(self.games)[:-40]:
                self.games.pop(k, None)
        self._touch(it)

    def won(self, rid, user: str) -> None:
        g = self.games.get(str(rid))
        if g is not None:
            g["winner"] = str(user or "")
            self._touch()

    def set_avatar(self, login, url) -> None:
        self.avatars[str(login or "").lower()] = str(url or "")
        if len(self.avatars) > 600:
            self.avatars.clear()
        self._touch()

    def test(self, lang: str = "en") -> None:
        """«Send test messages»: a few made-up lines (only in the chat box, never in your Twitch chat)."""
        for row in samples(lang):
            it = self.add(test=True, **row)
            if it["cmd"]:
                self.attach(it["id"], "discord.gg/fqpn")


BUF = ChatBuffer()


def samples(lang: str = "en") -> list:
    """Made-up messages for the preview and «Send test messages»."""
    ar = lang == "ar"
    return [
        dict(mid="", login="fqpn_", name="فقبن", color="#FF6B6B", badges=["streamer"], text="عيش حياتك برغبتك ومباديك", parts=[["t", "عيش حياتك برغبتك ومباديك"]]),
        dict(mid="", login="sara_gg", name="sara_gg", color="#7CC4FF", badges=["sub"], text="gg that clutch was insane 🔥", parts=[["t", "gg that clutch was insane 🔥"]]),
        dict(mid="", login="auk78", name="auk78", color="#C39BFF", badges=["vip"], text="!discord", parts=[["t", "!discord"]]),
        dict(mid="", login="newguy", name="newguy", color="#9BE59B", text="أول مرة أدخل، وش اللعبة؟" if ar else "first time here, what game is this?",
             parts=[["t", "أول مرة أدخل، وش اللعبة؟" if ar else "first time here, what game is this?"]], first=True),
        dict(mid="", login="mod_ali", name="mod_ali", color="#5BD38A", badges=["mod"], text="حياك الله، فالورانت" if ar else "welcome! it's Valorant",
             parts=[["t", "حياك الله، فالورانت" if ar else "welcome! it's Valorant"]], reply_to="newguy"),
    ]


# ---------- what the overlay draws ----------

def _app_badges(store, it, cfg, cache) -> dict:
    want = cfg.get("app_badges") or []
    out = {}
    uid, login = it.get("uid"), it.get("login")
    if "wins" in want and uid:
        try:
            from . import minigames
            n = minigames.wins_of((cache["wins"]).get(uid) or {})
            if n:
                out["wins"] = int(n)
        except Exception:
            pass
    if "streak" in want and login and cache.get("first") and cache["first"][0] == login:
        out["streak"] = cache["first"][1]
    if "first" in want and it.get("first"):
        out["first"] = True
    if "anniv" in want and uid:
        try:
            from . import followdates
            from datetime import datetime, timezone, date
            v = (cache["dates"]).get(uid)
            if isinstance(v, (list, tuple)) and v:
                if followdates.anniversary(datetime.fromtimestamp(float(v[0]), tz=timezone.utc), date.today()):
                    out["anniv"] = True
        except Exception:
            pass
    return out


def _first_now(store, bot) -> tuple | None:
    """(login, streak) of who was first in chat this stream."""
    try:
        sid = (bot._first_sid() if hasattr(bot, "_first_sid") else bot._stream_id()) if bot is not None else None
        if not sid:
            return None
        for st in (store.get("first_state") or {}).values():
            if isinstance(st, dict) and st.get("stream") == sid and st.get("winner"):
                return str(st["winner"]).lower(), max(1, int(st.get("streak") or 1))
    except Exception:
        pass
    return None


def view(store, cfg: dict, bot=None, owner: str = "", writer: str = "", buf: ChatBuffer = None) -> list:
    """The lines to draw, oldest first (at most 60), with the settings applied."""
    from . import greetings, blocks
    buf = buf or BUF
    hide = set(cfg.get("hide_people") or [])
    if cfg.get("use_blocklist"):
        hide |= blocks.blocked_logins(store.get("blocklist"))
    bots = set(greetings.KNOWN_BOTS) | ({writer.lower()} if writer and writer.lower() != owner.lower() else set())
    cache = {"wins": store.get("game_wins") or {}, "dates": store.get("follow_dates") or {}, "first": _first_now(store, bot)}
    colors = {}                     # 1.18.0: the colors viewers chose with !color
    if cfg.get("own_colors"):
        for k, e in (store.get(COLORS) or {}).items():
            c = readable(e.get("c")) if isinstance(e, dict) else ""
            if c:
                colors[str(k)] = c
    items = list(buf.items)
    by_id = buf.by_id
    out, folded, dups, last_of = [], {}, {}, {}
    # spam copies: counted on the first one, which moves to where the newest copy is
    if cfg.get("spam"):
        for it in items:
            if it.get("dup_of") and not it["deleted"]:
                dups.setdefault(it["dup_of"], []).append(it)
    games = {}
    if cfg.get("fold_games"):
        for it in items:
            if it.get("guess"):
                games.setdefault(it["guess"], []).append(it)
    for it in items:
        if it["login"] in hide:
            continue
        if it["shared"] and cfg.get("shared") == "hide":
            continue
        if it["bot"] or it["login"] in bots:
            if cfg.get("hide_bots"):
                continue
            if it.get("echo_of") and cfg.get("attach") and cfg.get("commands") != "hide":
                continue          # shown under the command that asked for it
            if it.get("echo_of") and cfg.get("commands") == "hide":
                continue
        if it["deleted"] and cfg.get("deleted") == "gone":
            continue
        if cfg.get("spam") and it.get("dup_of") and by_id.get(it["dup_of"]) is not None and not by_id[it["dup_of"]]["deleted"]:
            continue
        if cfg.get("fold_games") and it.get("guess"):
            rid = it["guess"]
            if rid in folded:
                continue
            group = games.get(rid) or [it]
            g = buf.games.get(rid) or {}
            folded[rid] = True
            last = max(group, key=lambda x: x["t"])
            out.append({"k": "fold", "id": "g" + rid, "rev": sum(x.get("rev", 0) for x in group) + (1 if g.get("winner") else 0),
                        "t": last["t"], "game": g.get("game", ""), "n": len(group), "winner": g.get("winner", ""), "_order": last["seq"]})
            continue
        if it["cmd"] and cfg.get("commands") == "hide":
            continue
        row = {"k": "msg", "id": it["id"], "rev": it.get("rev", 1), "t": it["t"], "name": it["name"], "login": it["login"],
               "color": (colors.get(it["uid"]) or it["color"]) if colors else it["color"], "badges": it["badges"], "parts": it["parts"], "first": it["first"],
               "shared": it["shared"], "reply": it["reply_to"] if cfg.get("replies") else "", "mention": it["mention"],
               "deleted": it["deleted"], "bot": it["bot"] or it["login"] in bots, "_order": it["seq"],
               "tb": [[x.split("/")[0], BADGES.get(x) or BADGES.get(x.split("/")[0] + "/1") or ""] for x in it.get("tb") or []]}
        if it["cmd"] and cfg.get("commands") == "answer":
            if not it.get("answers"):
                continue
            row.update(k="ans", parts=[], answers=list(it["answers"]))
        elif cfg.get("attach") and it.get("answers"):
            row["answers"] = list(it["answers"])
        d = dups.get(it["id"])
        if d:
            row["n"] = 1 + len(d)
            row["t"] = max(x["t"] for x in d)
            row["_order"] = max(x["seq"] for x in d)
            row["rev"] = row["rev"] + sum(x.get("rev", 0) for x in d)
        if cfg.get("pics"):
            row["pic"] = buf.avatars.get(it["login"], "")
        row["_it"] = it
        out.append(row)
    out.sort(key=lambda r: r["_order"])
    out = out[-60:]
    for r in out:               # 1.18.0: the app's badges only for the lines that are drawn (lighter: OBS asks every second)
        r.pop("_order", None)
        it = r.pop("_it", None)
        if it is not None:
            r["app"] = _app_badges(store, it, cfg, cache)
    return out
