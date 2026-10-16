"""Bot accounts shared by several channels (1.12.0).

A bot account only SENDS: replies, announcements and moderation actions for the channels that chose it. Each channel's own
bot reads its own chat with the channel's own login, so a bot account needs no connection per channel: there is ONE
BotSender per bot account, whatever the number of channels it serves. It is also the only thing that renews that bot's
Twitch login (two connections renewing the same login invalidate each other's renewal key: the bot would go silent).

Sending uses Twitch's "Send Chat Message" API with the bot's user login (scope user:write:chat). Twitch rules:
- not a moderator in a channel: that channel's chat modes still apply (followers-only, slow mode, verified accounts) and
  the send limit is lower; announcements and moderation need the bot to be a MODERATOR in that channel.
- send limits: 20 messages / 30 s as a normal user, 100 / 30 s as a moderator. Whether Twitch counts them per channel or
  account-wide is not documented clearly, so this counts them ACCOUNT-WIDE (the safe choice): one shared limit across all
  the channels the bot serves (needs testing with real accounts)."""

import asyncio
import logging
import time
from collections import deque

import aiohttp

from . import accounts, auth, safefile

log = logging.getLogger("twitchbot.botsender")
HELIX = "https://api.twitch.tv/helix/"
WINDOW = 30.0
LIMIT_USER, LIMIT_MOD = 20, 100
MAX_WAIT = 15.0            # wait at most this long for a free send slot, then give up (never pile up minutes of replies)
MOD_TTL = 120.0            # how long "is the bot a moderator there?" is trusted


class SendError(Exception):
    """code: login (expired / rejected) | scopes (a permission is missing) | notmod (needs moderator) | banned |
    dropped (Twitch refused this message: chat mode, ...) | limit | offline | twitch"""
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code, self.detail = code, detail


class BotSender:
    def __init__(self, bot_id: str, login: str = "", clock=time.time, http=None):
        self.bot_id, self.login = str(bot_id), login
        self.clock = clock
        self._lock = asyncio.Lock()
        self._sent: deque = deque()            # send times, shared by every channel this bot serves
        self._mods: dict = {}                  # channel id -> (is moderator, when checked)
        self._http = http                      # (tests: a fake) -> await http(method, url, params, json, token) -> (status, body)
        self.problem = ""                      # login | scopes | "" (shown on the Bot accounts page)

    # ---------- the bot's login (only this object renews it) ----------
    def token_path(self):
        return accounts.bot_token_file(self.bot_id)

    def load(self):
        status, data = safefile.read(self.token_path())
        return data if status == "ok" and isinstance(data, dict) else None

    async def token(self, force_refresh: bool = False) -> str:
        async with self._lock:
            data = self.load()
            if not data:
                self.problem = "login"
                raise SendError("login", "This bot account's Twitch login is missing.")
            if force_refresh or float(data.get("expires_at", 0)) - self.clock() < 120:
                status, resp = await self._call("POST", auth.TOKEN_URL, form={"client_id": auth.CLIENT_ID, "grant_type": "refresh_token",
                                                                              "refresh_token": data.get("refresh_token", "")})
                if status != 200 or not resp.get("access_token"):
                    self.problem = "login"
                    raise SendError("login", "This bot account's Twitch login expired. Reconnect it on the Bot accounts page.")
                data = {"access_token": resp["access_token"], "refresh_token": resp.get("refresh_token", data.get("refresh_token")),
                        "expires_at": self.clock() + int(resp.get("expires_in", 0)), "scopes": resp.get("scope", data.get("scopes", []))}
                safefile.write(self.token_path(), data)
            return data["access_token"]

    # ---------- talking to Twitch ----------
    async def _call(self, method, url, params=None, json=None, token=None, form=None):
        if self._http is not None:
            return await self._http(method, url, params, json if form is None else form, token)
        headers = {"Client-Id": auth.CLIENT_ID}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.request(method, url, params=params, json=json, data=form, headers=headers) as r:
                    try:
                        body = await r.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        body = {}
                    return r.status, body if isinstance(body, dict) else {}
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return 0, {}

    async def helix(self, method: str, path: str, params=None, body=None):
        """(status, body) of a Helix call as the bot; a rejected login is renewed once and retried."""
        status, data = await self._call(method, HELIX + path, params, body, await self.token())
        if status == 401:
            status, data = await self._call(method, HELIX + path, params, body, await self.token(force_refresh=True))
        if status == 401:
            self.problem = "login"
        elif status in (200, 204):
            self.problem = ""
        return status, data

    # ---------- the shared send limit ----------
    async def _slot(self, channel_id: str) -> None:
        limit = LIMIT_MOD if self._mods.get(str(channel_id), (False, 0))[0] else LIMIT_USER
        waited = 0.0
        while True:
            now = self.clock()
            while self._sent and now - self._sent[0] > WINDOW:
                self._sent.popleft()
            if len(self._sent) < limit:
                self._sent.append(now)
                return
            if waited >= MAX_WAIT:
                raise SendError("limit", "Too many messages: Twitch's send limit for this bot account was reached.")
            await asyncio.sleep(0.5)
            waited += 0.5

    # ---------- what the channels use ----------
    async def send(self, channel_id, text: str, reply_to: str | None = None) -> str:
        await self._slot(channel_id)
        body = {"broadcaster_id": str(channel_id), "sender_id": self.bot_id, "message": text[:500]}
        if reply_to:
            body["reply_parent_message_id"] = str(reply_to)
        status, data = await self.helix("POST", "chat/messages", body=body)
        if status == 200:
            row = (data.get("data") or [{}])[0]
            if row.get("is_sent", True):
                return str(row.get("message_id") or "")
            raise SendError("dropped", str((row.get("drop_reason") or {}).get("message") or "Twitch did not post the message."))
        raise self._error(status, data)

    async def announce(self, channel_id, text: str, color: str = "primary") -> None:
        await self._slot(channel_id)
        status, data = await self.helix("POST", "chat/announcements", {"broadcaster_id": str(channel_id), "moderator_id": self.bot_id},
                                        {"message": text[:500], "color": color})
        if status not in (200, 204):
            raise self._error(status, data, needs_mod=True)

    async def moderate(self, method: str, path: str, channel_id, params: dict, body=None) -> bool:
        q = dict(params, broadcaster_id=str(channel_id), moderator_id=self.bot_id)
        status, _ = await self.helix(method, path, q, body)
        return status in (200, 204)

    def _error(self, status, data, needs_mod=False) -> SendError:
        msg = str((data or {}).get("message") or "")
        if status == 0:
            return SendError("offline", "Twitch can't be reached.")
        if status == 401:
            return SendError("login", msg)
        if status == 403:
            return SendError("notmod" if needs_mod or "moderator" in msg.lower() else "scopes", msg)
        if status == 429:
            return SendError("limit", msg)
        return SendError("twitch", f"Twitch answered {status}: {msg}")

    # ---------- the status the app shows for each channel ----------
    async def is_mod(self, channel_id) -> bool | None:
        """Is the bot a moderator (or the broadcaster) in that channel? None = can't tell right now."""
        cid = str(channel_id)
        if cid == self.bot_id:
            return True
        hit = self._mods.get(cid)
        if hit and self.clock() - hit[1] < MOD_TTL:
            return hit[0]
        found, cursor = False, None
        for _ in range(10):
            params = {"user_id": self.bot_id, "first": "100"}
            if cursor:
                params["after"] = cursor
            status, data = await self.helix("GET", "moderation/channels", params)
            if status != 200:
                return None
            if any(str(r.get("broadcaster_id")) == cid for r in data.get("data") or []):
                found = True
                break
            cursor = (data.get("pagination") or {}).get("cursor")
            if not cursor:
                break
        self._mods[cid] = (found, self.clock())
        return found

    async def status(self, channel_id) -> dict:
        """{state: ready | notmod | login | scopes | offline, ...} for one channel this bot serves."""
        try:
            await self.token()
        except SendError as e:
            return {"state": e.code}
        mod = await self.is_mod(channel_id)
        if mod is None:
            return {"state": self.problem or "offline"}
        return {"state": "ready" if mod else "notmod"}


SENDERS: dict = {}


def get(bot_id, login: str = "") -> BotSender:
    """THE sender of a bot account (one per account, shared by every channel that uses it)."""
    s = SENDERS.get(str(bot_id))
    if s is None:
        s = SENDERS[str(bot_id)] = BotSender(str(bot_id), login)
    elif login:
        s.login = login
    return s


def forget(bot_id) -> None:
    SENDERS.pop(str(bot_id), None)
