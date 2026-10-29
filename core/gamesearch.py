"""1.14.0: !game / !setgame find the game people mean: short and Arabic names (gta, جاتا, valo, ماين, سوالف…), then the
closest name among Twitch's search results, preferring what is popular on Twitch right now (Twitch's top games)."""
import difflib
import re

ALIASES = {
    "gta": "Grand Theft Auto V", "gta5": "Grand Theft Auto V", "gtav": "Grand Theft Auto V", "جاتا": "Grand Theft Auto V",
    "قراند": "Grand Theft Auto V", "قراند5": "Grand Theft Auto V", "cod": "Call of Duty", "كود": "Call of Duty",
    "warzone": "Call of Duty: Warzone", "وارزون": "Call of Duty: Warzone", "valo": "VALORANT", "val": "VALORANT",
    "فالو": "VALORANT", "فالورانت": "VALORANT", "lol": "League of Legends", "لول": "League of Legends",
    "cs": "Counter-Strike", "cs2": "Counter-Strike", "csgo": "Counter-Strike", "كاونتر": "Counter-Strike",
    "fn": "Fortnite", "فورت": "Fortnite", "فورتنايت": "Fortnite", "mc": "Minecraft", "ماين": "Minecraft",
    "ماينكرافت": "Minecraft", "apex": "Apex Legends", "ابكس": "Apex Legends", "rl": "Rocket League", "روكت": "Rocket League",
    "روكيت ليق": "Rocket League", "ow": "Overwatch 2", "ow2": "Overwatch 2", "اوفرواتش": "Overwatch 2",
    "pubg": "PUBG: BATTLEGROUNDS", "ببجي": "PUBG: BATTLEGROUNDS", "fifa": "EA Sports FC", "fc": "EA Sports FC",
    "فيفا": "EA Sports FC", "jc": "Just Chatting", "chatting": "Just Chatting", "سوالف": "Just Chatting",
    "دردشة": "Just Chatting", "rdr2": "Red Dead Redemption 2", "dota": "Dota 2", "دوتا": "Dota 2", "راست": "Rust",
    "روبلوكس": "Roblox", "eft": "Escape from Tarkov", "tarkov": "Escape from Tarkov", "elden": "ELDEN RING",
    "الدن رينق": "ELDEN RING", "r6": "Tom Clancy's Rainbow Six Siege", "tft": "Teamfight Tactics",
    "hs": "Hearthstone", "wow": "World of Warcraft", "gow": "God of War",
}


def plain(t: str) -> str:
    return re.sub(r"[\W_]+", "", str(t or "").casefold())


def query_for(q: str) -> str:
    """What to search for: a known short / Arabic name becomes the full name."""
    k = str(q or "").strip().casefold()
    return ALIASES.get(k) or ALIASES.get(plain(k)) or str(q or "").strip()


def score(query: str, name: str, top_rank=None) -> float:
    """How well `name` fits `query` (higher is better). top_rank: its place in Twitch's top games now (0 = first)."""
    q, n = plain(query), plain(name)
    if not q or not n:
        return 0.0
    s = 0.0
    if n == q:
        s += 100
    elif n.startswith(q):
        s += 45
    elif q in n:
        s += 30
    words = [plain(w) for w in re.split(r"[\s:\-]+", str(name)) if plain(w)]
    if q == "".join(w[0] for w in words if w):          # initials: "rdr" -> Red Dead Redemption
        s += 35
    s += 30 * difflib.SequenceMatcher(None, q, n[: max(len(q) + 6, 8)]).ratio()
    if top_rank is not None:
        s += 30 * max(0.0, 1 - top_rank / 100)          # popular on Twitch right now
    return s


def best(query: str, found: list, top: list):
    """found = search results [{"id", "name"}]; top = Twitch's top games, most watched first. The best {"id", "name"} or None.
    A top game that fits well also counts even when the search didn't return it."""
    rank = {str(g["id"]): i for i, g in enumerate(top or [])}
    pool = {str(g["id"]): g for g in (found or [])}
    for g in top or []:
        if plain(query) and (plain(query) in plain(g["name"]) or difflib.SequenceMatcher(None, plain(query), plain(g["name"])).ratio() > 0.75):
            pool.setdefault(str(g["id"]), g)
    if not pool:
        return None
    return max(pool.values(), key=lambda g: score(query, g["name"], rank.get(str(g["id"]))))
