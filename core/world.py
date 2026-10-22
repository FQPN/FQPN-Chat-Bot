"""$(weather city) and $(time city) (1.13.0): the weather and the local time of a city, in the app's language.

Uses Open-Meteo (free, no account or key): its geocoding finds the city, its forecast gives the current weather and the
city's time offset (so no time-zone database is needed on the PC). Answers are cached for a few minutes, so a busy chat
asking the same city doesn't hammer the service. Nothing here ever raises: a problem becomes a short "(...)" text."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import aiohttp

log = logging.getLogger("twitchbot.world")

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search?count=1&format=json&language={lang}&name={name}"
WX_URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone=auto"
          "&current=temperature_2m,weather_code,is_day")
CACHE_SECONDS = 600       # weather: 10 minutes (it doesn't change faster than that); places: kept for the whole run

# WMO weather codes (what Open-Meteo sends) -> words
CODES = {
    0: ("clear sky", "صافٍ"), 1: ("mainly clear", "صافٍ غالبًا"), 2: ("partly cloudy", "غائم جزئيًا"), 3: ("cloudy", "غائم"),
    45: ("fog", "ضباب"), 48: ("fog", "ضباب"),
    51: ("light drizzle", "رذاذ خفيف"), 53: ("drizzle", "رذاذ"), 55: ("heavy drizzle", "رذاذ كثيف"),
    56: ("freezing drizzle", "رذاذ متجمد"), 57: ("freezing drizzle", "رذاذ متجمد"),
    61: ("light rain", "مطر خفيف"), 63: ("rain", "مطر"), 65: ("heavy rain", "مطر غزير"),
    66: ("freezing rain", "مطر متجمد"), 67: ("freezing rain", "مطر متجمد"),
    71: ("light snow", "ثلج خفيف"), 73: ("snow", "ثلج"), 75: ("heavy snow", "ثلج كثيف"), 77: ("snow grains", "حبيبات ثلج"),
    80: ("rain showers", "زخات مطر"), 81: ("rain showers", "زخات مطر"), 82: ("heavy rain showers", "زخات مطر غزيرة"),
    85: ("snow showers", "زخات ثلج"), 86: ("snow showers", "زخات ثلج"),
    95: ("thunderstorm", "عاصفة رعدية"), 96: ("thunderstorm with hail", "عاصفة رعدية مع برد"), 99: ("thunderstorm with hail", "عاصفة رعدية مع برد"),
}
TEXT = {
    "en": {"none": "(type a city)", "notfound": "(city not found)", "failed": "(weather unavailable)", "tfailed": "(time unavailable)"},
    "ar": {"none": "(اكتب اسم مدينة)", "notfound": "(لم يتم العثور على المدينة)", "failed": "(الطقس غير متاح)", "tfailed": "(الوقت غير متاح)"},
}

_places: dict = {}        # (city, lang) -> place dict or None
_weather: dict = {}       # (lat, lon) -> (time, data)


async def get_json(url: str) -> dict:
    """GET a public JSON address (the tests replace this)."""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
        async with s.get(url, headers={"User-Agent": "FQPNsChatBot"}) as r:
            if r.status != 200:
                raise OSError(f"answered {r.status}")
            return await r.json(content_type=None)


def _clean_city(city: str) -> str:
    return " ".join(str(city or "").replace("\x00", "").split())[:80].strip(" ,.@")


async def find_place(city: str, lang: str, fetch=get_json):
    key = (city.casefold(), lang)
    if key in _places:
        return _places[key]
    data = await fetch(GEO_URL.format(lang="ar" if lang == "ar" else "en", name=quote(city, safe="")))
    rows = (data or {}).get("results") or []
    place = None
    if rows:
        r = rows[0]
        place = {"name": str(r.get("name") or city), "country": str(r.get("country") or ""),
                 "lat": float(r["latitude"]), "lon": float(r["longitude"])}
    if len(_places) > 500:
        _places.clear()
    _places[key] = place
    return place


async def _current(place, fetch=get_json) -> dict:
    key = (round(place["lat"], 3), round(place["lon"], 3))
    hit = _weather.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    data = await fetch(WX_URL.format(lat=place["lat"], lon=place["lon"]))
    if len(_weather) > 300:
        _weather.clear()
    _weather[key] = (time.time(), data)
    return data


def _label(place, lang: str) -> str:
    sep = "، " if lang == "ar" else ", "
    return place["name"] + (sep + place["country"] if place["country"] and place["country"] != place["name"] else "")


async def weather(city: str, lang: str = "en", fetch=get_json) -> str:
    """"Riyadh, Saudi Arabia: 31°C, clear sky" / "الرياض، السعودية: 31°م، صافٍ"."""
    lang = "ar" if lang == "ar" else "en"
    city = _clean_city(city)
    if not city:
        return TEXT[lang]["none"]
    try:
        place = await find_place(city, lang, fetch)
        if place is None:
            return TEXT[lang]["notfound"]
        cur = (await _current(place, fetch)).get("current") or {}
        temp = round(float(cur["temperature_2m"]))
        words = CODES.get(int(cur.get("weather_code", -1)), ("", ""))[1 if lang == "ar" else 0]
        if lang == "ar":
            return f"{_label(place, lang)}: {temp}°م" + (f"، {words}" if words else "")
        return f"{_label(place, lang)}: {temp}°C" + (f", {words}" if words else "")
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, KeyError, TypeError) as e:
        log.warning("$(weather) failed for %r: %r", city, e)
        return TEXT[lang]["failed"]


def format_clock(when: datetime, lang: str) -> str:
    h = when.hour % 12 or 12
    if lang == "ar":
        return f"{h}:{when.minute:02d} " + ("ص" if when.hour < 12 else "م")
    return f"{h}:{when.minute:02d} " + ("AM" if when.hour < 12 else "PM")


async def local_time(city: str, lang: str = "en", fetch=get_json, now=None) -> str:
    """"Riyadh, Saudi Arabia: 3:42 PM" / "الرياض، السعودية: 3:42 م"."""
    lang = "ar" if lang == "ar" else "en"
    city = _clean_city(city)
    if not city:
        return TEXT[lang]["none"]
    try:
        place = await find_place(city, lang, fetch)
        if place is None:
            return TEXT[lang]["notfound"]
        offset = int((await _current(place, fetch))["utc_offset_seconds"])
        when = (now or datetime.now(timezone.utc)) + timedelta(seconds=offset)
        return f"{_label(place, lang)}: {format_clock(when, lang)}"
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, KeyError, TypeError) as e:
        log.warning("$(time) failed for %r: %r", city, e)
        return TEXT[lang]["tfailed"]
