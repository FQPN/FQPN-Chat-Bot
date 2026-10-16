"""The Support page (1.11.0): a suggestion or a problem, with pictures, sent to the developers.

The page -> the app (/api/support, checked here) -> the website (SITE/api/support, with the channel's Twitch login so it
knows who sent it) -> the developers' Discord channel. The Discord link lives only on the website, never in the app.
Nothing is sent unless the streamer presses Send."""

import asyncio
import base64
import logging
import platform
from logging.handlers import RotatingFileHandler
from pathlib import Path

import aiohttp

from . import publiclist
from .version import VERSION

log = logging.getLogger("twitchbot.support")

MAX_TEXT, MAX_CONTACT = 2000, 50
MAX_IMAGES, MAX_IMAGE, MAX_ALL = 4, 4 * 1024 * 1024, 8 * 1024 * 1024
LOG_TAIL = 250 * 1024                 # the end of bot.log (the website takes up to 256 kB)
TIMEOUT = 60
_MAGIC = (("png", b"\x89PNG"), ("jpg", b"\xff\xd8\xff"), ("gif", b"GIF8"), ("webp", b"RIFF"))


class SupportError(ValueError):
    """code: a short word the page turns into words in English or Arabic; detail: the reason in English."""
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code, self.detail = code, detail


def image_kind(data: bytes) -> str:
    for kind, magic in _MAGIC:
        if data.startswith(magic) and (kind != "webp" or data[8:12] == b"WEBP"):
            return kind
    return ""


def windows_version() -> str:
    try:
        return f"{platform.system()} {platform.release()} ({platform.version()})"[:80]
    except Exception:
        return ""


def prepare(data) -> dict:
    """What the page sent, checked: {kind, text, contact, images: [(name, bytes)], log}. Raises SupportError."""
    if not isinstance(data, dict):
        raise SupportError("bad", "The message couldn't be read.")
    kind = data.get("kind")
    if kind not in ("suggestion", "problem"):
        raise SupportError("kind", "Choose Suggestion or Problem.")
    text = str(data.get("text") or "").replace("\r\n", "\n").strip()
    if len(text) < 5:
        raise SupportError("short", "Write a few words first.")
    if len(text) > MAX_TEXT:
        raise SupportError("long", f"A message can be at most {MAX_TEXT} characters.")
    contact = " ".join(str(data.get("contact") or "").split())[:MAX_CONTACT]
    raw = data.get("images") or []
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES:
        raise SupportError("count", f"At most {MAX_IMAGES} images.")
    images, total = [], 0
    for i, im in enumerate(raw):
        try:
            b = base64.b64decode(str((im or {}).get("data") or ""), validate=True)
        except (ValueError, TypeError):
            raise SupportError("type", "Only pictures can be sent (PNG, JPG, WebP or GIF).")
        kind_ = image_kind(b)
        if not kind_:
            raise SupportError("type", "Only pictures can be sent (PNG, JPG, WebP or GIF).")
        if len(b) > MAX_IMAGE:
            raise SupportError("size", "A picture can be at most 4 MB.")
        total += len(b)
        images.append((f"image{i + 1}.{kind_}", b))
    if total > MAX_ALL:
        raise SupportError("total", "All pictures together can be at most 8 MB.")
    return {"kind": kind, "text": text, "contact": contact, "images": images, "log": kind == "problem" and data.get("log") is True}


def log_path():
    """bot.log, wherever the launcher put it (None when running without one)."""
    for h in logging.getLogger().handlers:
        if isinstance(h, RotatingFileHandler):
            return Path(h.baseFilename)
    return None


def log_tail(path, limit: int = LOG_TAIL) -> bytes:
    """The end of the log, starting at a whole line."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - limit))
            data = f.read()
    except OSError:
        return b""
    if size > limit and b"\n" in data:
        data = data[data.index(b"\n") + 1:]
    return data


async def http_post(form_fields: list, files: list, token: str):
    """(status, JSON body). 0 = the website couldn't be reached."""
    form = aiohttp.FormData()
    for k, v in form_fields:
        form.add_field(k, v)
    for field, name, data, ctype in files:
        form.add_field(field, data, filename=name, content_type=ctype)
    headers = {"Authorization": f"OAuth {token}", "User-Agent": f"FQPN-Chat-Bot/{VERSION}"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as s:
            async with s.post(publiclist.SITE + "/api/support", data=form, headers=headers) as r:
                try:
                    body = await r.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    body = {}
                return r.status, body if isinstance(body, dict) else {}
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return 0, {}


CTYPE = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


async def send(prep: dict, token: str, post=None, logfile=None) -> dict:
    """Sends a prepared message. {"ok": True} or raises SupportError (offline | limit | notsetup | login | banned | failed)."""
    if not publiclist.SITE:
        raise SupportError("notsetup", "This version of the app has no website to send to.")
    fields = [("kind", prep["kind"]), ("text", prep["text"]), ("contact", prep["contact"]), ("version", VERSION)]
    if prep["kind"] == "problem":
        fields.append(("os", windows_version()))
    files = [("image", name, data, CTYPE[name.rsplit(".", 1)[1]]) for name, data in prep["images"]]
    if prep["log"]:
        tail = log_tail(logfile or log_path()) if (logfile or log_path()) else b""
        if tail:
            files.append(("log", "bot.log", tail, "text/plain"))
    status, body = await (post or http_post)(fields, files, token)
    if status == 200 and body.get("ok"):
        log.info("Support message sent (%s, %d picture(s))", prep["kind"], len(prep["images"]))
        return {"ok": True}
    why = str(body.get("error") or "")
    if status == 0:
        raise SupportError("offline", "The website can't be reached. Check the internet and try again.")
    if status == 429:
        raise SupportError("limit", why)
    if status == 503 and "set up" in why:
        raise SupportError("notsetup", why)
    if status == 401:
        raise SupportError("login", why)
    if status == 403 and "can't send" in why:
        raise SupportError("banned", why)
    raise SupportError("failed", why or f"The website answered {status}.")
