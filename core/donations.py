"""Donation alerts from Streamlabs and StreamElements.

The app connects to the service with YOUR token and is told the moment a donation is made:
  - Streamlabs: the Socket API (a Socket.IO connection) with your "Socket API Token".
  - StreamElements: the Astro WebSocket gateway, topic "channel.tips", with your JWT.
It only sees donations made while the app is running. The tokens are kept encrypted with Windows' own protection (DPAPI,
tied to your Windows login) next to your Twitch login, and are never sent back to the dashboard."""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
import uuid
from collections import deque
from pathlib import Path

import aiohttp

from . import auth

log = logging.getLogger("donations")

SERVICES = ("streamlabs", "streamelements")
STREAMLABS_URL = "wss://sockets.streamlabs.com/socket.io/"
ASTRO_URL = "wss://astro.streamelements.com/"
SE_ME_URL = "https://api.streamelements.com/kappa/v2/channels/me"
MAX_TOKEN = 4000
MAX_BACKOFF = 60


# ---------------------------------------------------------------- tokens kept encrypted on this PC

def store_path() -> Path:
    return Path(auth.AUTH_DIR) / "donations.json"


def can_encrypt() -> bool:
    return sys.platform == "win32"


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows' own protection (DPAPI): only this Windows user, on this PC, can read what it protects."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = Blob()
    forbid_ui = 0x1       # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(blob_in), ctypes.c_wchar_p("FQPN's Chat Bot"), None, None, None,
                                      forbid_ui, ctypes.byref(blob_out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, forbid_ui, ctypes.byref(blob_out))
    if not ok:
        raise OSError("Windows could not " + ("protect" if protect else "unlock") + " the token")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def _read_file() -> dict:
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_file(data: dict) -> None:
    Path(auth.AUTH_DIR).mkdir(parents=True, exist_ok=True)
    path = store_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def save_token(service: str, token: str) -> None:
    raw = token.encode("utf-8")
    if can_encrypt():
        blob, enc = _dpapi(raw, True), True
    else:   # not Windows (running from source on another system): kept as plain text, and the page says so
        blob, enc = raw, False
    data = _read_file()
    data[service] = {"token": base64.b64encode(blob).decode("ascii"), "encrypted": enc}
    _write_file(data)


def load_token(service: str) -> str | None:
    entry = _read_file().get(service)
    if not isinstance(entry, dict):
        return None
    try:
        blob = base64.b64decode(entry["token"])
        raw = _dpapi(blob, False) if entry.get("encrypted") else blob
        return raw.decode("utf-8") or None
    except (KeyError, ValueError, OSError):
        return None          # unreadable (for example copied to another PC): the user connects again


def clear_token(service: str) -> None:
    data = _read_file()
    if data.pop(service, None) is not None:
        if data:
            _write_file(data)
        else:
            store_path().unlink(missing_ok=True)


def has_token(service: str) -> bool:
    return isinstance(_read_file().get(service), dict)


def clean_token(raw) -> str:
    """A token as pasted by the user: trimmed, and refused if it cannot be one."""
    if not isinstance(raw, str):
        raise ValueError("The token must be text.")
    token = raw.strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise ValueError("Paste your token first.")
    if len(token) > MAX_TOKEN or re.search(r"\s", token):
        raise ValueError("That doesn't look like a token (it has spaces or is far too long).")
    return token


# ---------------------------------------------------------------- turning service messages into donations

def _clean_text(value, limit: int) -> str:
    """Donor-provided text, made safe for chat: one line, no control characters, no command prefixes."""
    text = re.sub(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]", " ", str(value or ""))
    text = re.sub(r"(^|\s)[/!.\\]+(?=\S)", r"\1", text)      # nobody can sneak a "/ban" or "!command" through a donation
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _amount(value):
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return round(number, 2) if number == number and 0 <= number < 1e9 else None


def make_donation(service: str, dono_id, user, amount, currency, message, test=False):
    amount = _amount(amount)
    if amount is None:
        return None
    return {"service": service, "id": str(dono_id or ""), "user": _clean_text(user, 40) or "Anonymous", "amount": amount,
            "currency": _clean_text(currency, 8).upper(), "message": _clean_text(message, 200), "test": bool(test)}


def parse_streamlabs(payload) -> list:
    """Streamlabs 'event' messages: {"type": "donation", "message": [{"from", "amount", "currency", "message", ...}], "event_id"}."""
    if not isinstance(payload, dict) or payload.get("type") != "donation" or payload.get("for") not in (None, "", "streamlabs"):
        return []
    items = payload.get("message")
    items = [items] if isinstance(items, dict) else items if isinstance(items, list) else []
    out = []
    for i, m in enumerate(items):
        if not isinstance(m, dict):
            continue
        base = payload.get("event_id") or m.get("_id") or m.get("id") or m.get("donation_id") or ""
        dono = make_donation("streamlabs", f"{base}#{i}" if base and len(items) > 1 else base,
                             m.get("from") or m.get("name"), m.get("amount"), m.get("currency"), m.get("message"), m.get("isTest"))
        if dono:
            out.append(dono)
    return out


def parse_streamelements(msg) -> dict | None:
    """Astro 'message' on topic channel.tips: {"data": {"_id", "approved", "status", "donation": {"user": {"username"}, ...}}}."""
    if not isinstance(msg, dict) or msg.get("type") != "message" or msg.get("topic") != "channel.tips":
        return None
    data = msg.get("data")
    if not isinstance(data, dict):
        return None
    if data.get("approved") not in (None, "allowed") or data.get("status") not in (None, "success"):
        return None                      # held for moderation, or not paid: nothing to thank yet
    d = data.get("donation")
    if not isinstance(d, dict):
        return None
    user = d.get("user")
    name = user.get("username") if isinstance(user, dict) else user
    return make_donation("streamelements", data.get("_id") or data.get("transactionId") or msg.get("id"), name,
                         d.get("amount"), d.get("currency"), d.get("message"))


# ---------------------------------------------------------------- Socket.IO (Streamlabs), minimal and dependency-free

def parse_eio(text: str):
    """One Engine.IO text packet -> (kind, payload). Kinds: open, ping, pong, event, connect, connect_error, other."""
    if not text:
        return "other", None
    kind, rest = text[0], text[1:]
    if kind == "0":
        try:
            return "open", json.loads(rest)
        except ValueError:
            return "open", {}
    if kind == "1":
        return "close", None
    if kind == "2":
        return "ping", None
    if kind == "3":
        return "pong", None
    if kind == "4":                      # a Socket.IO packet
        if rest.startswith("0"):
            return "connect", None
        if rest.startswith("1"):
            return "disconnect", None
        if rest.startswith("2"):
            body = rest[1:]
            body = body[body.index("["):] if "[" in body else ""
            try:
                arr = json.loads(body)
            except ValueError:
                return "other", None
            if isinstance(arr, list) and arr and isinstance(arr[0], str):
                return "event", (arr[0], arr[1] if len(arr) > 1 else None)
        if rest.startswith("4"):
            try:
                return "connect_error", json.loads(rest[1:])
            except ValueError:
                return "connect_error", None
    return "other", None


class Refused(Exception):
    """The service says the token is wrong."""


class Service:
    """One live connection with its own status. `connector(url, headers=None)` is an async context manager that gives a
    WebSocket-like object (receive_str, send_str, close), which is what aiohttp provides and what the tests pretend."""

    def __init__(self, name: str, manager):
        self.name, self.m = name, manager
        self.state, self.detail, self.account = "none", "", ""
        self.task = None

    def public(self) -> dict:
        return {"state": self.state, "detail": self.detail, "account": self.account}

    def set(self, state: str, detail: str = "", account: str | None = None) -> None:
        self.state, self.detail = state, detail
        if account is not None:
            self.account = account

    def start(self) -> None:
        self.stop()
        self.set("connecting")
        self.task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = None

    async def _run(self) -> None:
        delay, quick = 2, 0
        while True:
            token = load_token(self.name)
            if not token:
                self.set("none")
                return
            began = time.time()
            try:
                await (self._streamlabs(token) if self.name == "streamlabs" else self._streamelements(token))
            except asyncio.CancelledError:
                raise
            except Refused as e:
                self.set("invalid", str(e))
                return                       # a wrong token will not fix itself: wait for a new one
            except Exception as e:
                log.warning("%s connection ended: %s", self.name, e)
                self.set("error", self.m.say("lost", self.name))
            lasted = time.time() - began
            quick = quick + 1 if lasted < 20 else 0
            wait = 2 if lasted > 60 else delay                   # a connection that held for a minute starts over at 2 s
            delay = min(MAX_BACKOFF, wait * 2)                   # 2, 4, 8 ... up to a minute
            if quick >= 4 and self.state != "connected":
                self.set("error", self.m.say("keeps_closing", self.name))
            await self.m.sleep(wait)

    async def _streamlabs(self, token: str) -> None:
        last_error = None
        for eio in (4, 3):                  # the current protocol first, the older one if the server refuses it
            url = f"{STREAMLABS_URL}?token={token}&transport=websocket&EIO={eio}"
            try:
                async with self.m.connector(url) as ws:
                    await self._socketio(ws, eio)
                return
            except Refused:
                raise
            except Exception as e:
                last_error = e
                if getattr(e, "status", None) in (400,) and eio == 4:
                    continue
                raise
        raise last_error or RuntimeError("could not connect")

    async def _socketio(self, ws, eio: int) -> None:
        ping_every = 25.0
        pinger = None
        try:
            while True:
                text = await ws.receive_str()
                kind, payload = parse_eio(text)
                if kind == "open":
                    ping_every = float((payload or {}).get("pingInterval", 25000)) / 1000
                    await ws.send_str("40")                              # join the default namespace
                    if eio == 3:
                        pinger = asyncio.create_task(self._client_pings(ws, ping_every))
                elif kind == "connect":
                    self.set("connected")
                elif kind == "ping":
                    await ws.send_str("3")
                elif kind == "connect_error":
                    msg = (payload or {}).get("message", "") if isinstance(payload, dict) else ""
                    raise Refused(self.m.say("refused", self.name) + (f" ({msg})" if msg else ""))
                elif kind in ("close", "disconnect"):
                    return
                elif kind == "event" and payload[0] == "event":
                    if self.state != "connected":
                        self.set("connected")
                    for dono in parse_streamlabs(payload[1]):
                        await self.m.deliver(dono)
        finally:
            if pinger:
                pinger.cancel()

    async def _client_pings(self, ws, every: float) -> None:       # the older protocol makes the client ping the server
        while True:
            await self.m.sleep(every)
            await ws.send_str("2")

    async def _streamelements(self, token: str) -> None:
        channel = await self.m.se_channel(token)                   # also proves the token works
        self.account = channel.get("username", "") or self.account
        async with self.m.connector(ASTRO_URL) as ws:
            while True:
                raw = await ws.receive_str()
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                kind = msg.get("type")
                if kind == "welcome":
                    await ws.send_str(json.dumps({"type": "subscribe", "nonce": str(uuid.uuid4()), "data": {
                        "topic": "channel.tips", "room": channel["_id"], "token": token, "token_type": "jwt"}}))
                elif kind == "response":
                    if msg.get("error") in ("err_unauthorized",):
                        raise Refused(self.m.say("refused", self.name))
                    if msg.get("error"):
                        raise RuntimeError(f"{msg.get('error')}: {(msg.get('data') or {}).get('message', '')}")
                    self.set("connected")
                elif kind == "reconnect":
                    return                                          # the server is restarting: connect again
                elif kind == "message":
                    dono = parse_streamelements(msg)
                    if dono:
                        await self.m.deliver(dono)


class DonationManager:
    def __init__(self, on_donation, connector=None, sleep=asyncio.sleep):
        self.on_donation = on_donation
        self.connector = connector or self._aiohttp_connector
        self.sleep = sleep
        self.services = {name: Service(name, self) for name in SERVICES}
        self._seen: deque = deque(maxlen=300)
        self._session = None

    # ----- what the page shows
    def public(self) -> dict:
        out = {name: s.public() for name, s in self.services.items()}
        out["encrypted"] = can_encrypt()
        return out

    @staticmethod
    def say(what: str, service: str) -> str:
        name = "Streamlabs" if service == "streamlabs" else "StreamElements"
        return {"refused": f"{name} refused this token. Copy it again from your {name} account.",
                "lost": f"The connection to {name} was lost. Trying again…",
                "keeps_closing": f"{name} keeps closing the connection. Check that the token is the right one."}[what]

    # ----- life cycle
    async def start(self) -> None:
        for name, svc in self.services.items():
            if has_token(name):
                svc.start()

    def connect(self, service: str, token) -> None:
        if service not in self.services:
            raise ValueError("Unknown service.")
        save_token(service, clean_token(token))
        self.services[service].account = ""
        self.services[service].start()

    def disconnect(self, service: str) -> None:
        if service not in self.services:
            raise ValueError("Unknown service.")
        self.services[service].stop()
        clear_token(service)
        self.services[service].set("none", "", "")

    async def stop(self) -> None:
        for svc in self.services.values():
            svc.stop()
        if self._session is not None:
            await self._session.close()

    # ----- helpers used by the connections
    async def deliver(self, dono: dict) -> None:
        key = (dono["service"], dono["id"])
        if dono["id"] and key in self._seen:
            return                                                  # the same donation, announced twice
        self._seen.append(key)
        try:
            await self.on_donation(dono)
        except Exception:
            log.exception("Could not handle a donation")

    async def se_channel(self, token: str) -> dict:
        """Who this StreamElements token belongs to ({'_id', 'username'}); raises Refused if the token is wrong."""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(SE_ME_URL, headers={"Authorization": f"Bearer {token}"}) as r:
                if r.status in (401, 403):
                    raise Refused(self.say("refused", "streamelements"))
                if r.status != 200:
                    raise RuntimeError(f"StreamElements answered {r.status}")
                data = await r.json()
        if not isinstance(data, dict) or not data.get("_id"):
            raise RuntimeError("StreamElements did not say which channel this is")
        return {"_id": data["_id"], "username": data.get("displayName") or data.get("username") or ""}

    def _aiohttp_connector(self, url: str, headers=None):
        return _WsContext(url, headers)


class _WsContext:
    """aiohttp's WebSocket client wrapped to the small interface above (text in, text out)."""

    def __init__(self, url, headers):
        self.url, self.headers = url, headers
        self.session = self.ws = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=20))
        try:
            self.ws = await self.session.ws_connect(self.url, headers=self.headers, heartbeat=None, max_msg_size=2**20)
        except Exception:
            await self.session.close()
            raise
        return self

    async def receive_str(self) -> str:
        while True:
            msg = await self.ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                return msg.data
            if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                raise ConnectionError("the service closed the connection")
            if msg.type == aiohttp.WSMsgType.ERROR:
                raise ConnectionError(str(self.ws.exception() or "connection error"))

    async def send_str(self, text: str) -> None:
        await self.ws.send_str(text)

    async def __aexit__(self, *exc):
        try:
            if self.ws is not None:
                await self.ws.close()
        finally:
            if self.session is not None:
                await self.session.close()
        return False
