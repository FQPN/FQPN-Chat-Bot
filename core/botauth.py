"""A second Twitch login, for the bot account ("Use a separate bot account" in Settings > Bot).

It uses the same Device Code flow as auth.py, but the login is saved in its own file (bot_token.json) and asks only for the
permissions a chat bot needs. Your channel account's login (auth.py) is never touched. It never opens a browser by itself:
that browser is usually logged in as YOU, so Twitch would simply connect your own account again."""

import asyncio
import json
import time
from pathlib import Path

import aiohttp

from . import auth

SCOPES = [
    "user:read:chat",
    "user:write:chat",
    "moderator:manage:announcements",   # /announce (the bot must be a moderator)
    "user:read:moderated_channels",     # to check whether the bot is a moderator of your channel
    "moderator:manage:chat_messages",    # Moderation: delete messages that break a filter (1.5.0)
    "moderator:manage:banned_users",     # Moderation: time people out (1.5.0)
]
last_problem: str | None = None         # "permissions" when the saved login lacks a permission and must be redone

MODERATED_URL = "https://api.twitch.tv/helix/moderation/channels"


def token_file() -> Path:
    return Path(auth.AUTH_DIR) / "bot_token.json"      # next to token.json; AUTH_DIR is set by the launcher


def load_token() -> dict | None:
    try:
        return json.loads(token_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_token(data: dict) -> None:
    Path(auth.AUTH_DIR).mkdir(parents=True, exist_ok=True)
    token_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_token() -> None:
    token_file().unlink(missing_ok=True)


def disconnect() -> None:
    clear_token()


def _store(resp: dict) -> dict:
    data = {
        "access_token": resp["access_token"],
        "refresh_token": resp["refresh_token"],
        "expires_at": time.time() + int(resp.get("expires_in", 0)),
        "scopes": resp.get("scope", SCOPES),
    }
    save_token(data)
    return data


def missing_scopes(granted) -> list:
    return sorted(set(SCOPES) - set(granted or []))


async def refresh(session: aiohttp.ClientSession, refresh_token: str) -> dict:
    async with session.post(
        auth.TOKEN_URL,
        data={"client_id": auth.CLIENT_ID, "grant_type": "refresh_token", "refresh_token": refresh_token},
    ) as r:
        resp = await r.json()
        if r.status != 200:
            raise auth.AuthError(f"Refresh failed: {resp.get('message', r.status)}")
        return _store(resp)


async def device_login(on_code=None) -> dict:
    """The Connect flow for the bot account. on_code(user_code, verification_uri) shows the code in the dashboard."""
    async with aiohttp.ClientSession() as session:
        async with session.post(auth.DEVICE_URL, data={"client_id": auth.CLIENT_ID, "scopes": " ".join(SCOPES)}) as r:
            dev = await r.json()
            if r.status != 200:
                raise auth.AuthError(f"Could not start login: {dev.get('message', r.status)}")
        if on_code:
            on_code(dev["user_code"], dev["verification_uri"])
        interval = int(dev.get("interval", 5))
        deadline = time.time() + int(dev.get("expires_in", 1800))
        while time.time() < deadline:
            await asyncio.sleep(interval)
            async with session.post(
                auth.TOKEN_URL,
                data={
                    "client_id": auth.CLIENT_ID,
                    "scopes": " ".join(SCOPES),
                    "device_code": dev["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            ) as r:
                resp = await r.json()
                if r.status == 200:
                    return _store(resp)
                if resp.get("message") == "authorization_pending":
                    continue
                raise auth.AuthError(f"Login failed: {resp.get('message', r.status)}")
        raise auth.AuthError("Login timed out. Press Connect to try again.")


async def get_account() -> dict | None:
    """{'access_token', 'refresh_token', 'login', 'user_id'} of the connected bot account, or None."""
    global last_problem
    data = load_token()
    if not data:
        return None
    async with aiohttp.ClientSession() as session:
        try:
            if data["expires_at"] - time.time() < 120:
                data = await refresh(session, data["refresh_token"])
            info = await auth.validate(session, data["access_token"])
            if info is None:
                data = await refresh(session, data["refresh_token"])
                info = await auth.validate(session, data["access_token"])
            if info is None:
                raise auth.AuthError("Token invalid after refresh")
            last_problem = None
            if missing_scopes(info.get("scopes", [])):
                last_problem = "permissions"      # saved before a permission was added: connect the bot account again
                clear_token()
                return None
        except (auth.AuthError, aiohttp.ClientError, KeyError):
            clear_token()
            return None
    return {"access_token": data["access_token"], "refresh_token": data["refresh_token"],
            "login": info["login"], "user_id": info["user_id"]}


async def is_moderator(owner_id: str) -> bool | None:
    """True/False: is the bot account a moderator of the channel with this id? None if it could not be checked."""
    account = await get_account()
    if account is None:
        return None
    headers = {"Authorization": f"Bearer {account['access_token']}", "Client-Id": auth.CLIENT_ID}
    try:
        async with aiohttp.ClientSession() as session:
            cursor = None
            for _ in range(30):                   # at most 3000 channels
                params = {"user_id": account["user_id"], "first": "100"}
                if cursor:
                    params["after"] = cursor
                async with session.get(MODERATED_URL, params=params, headers=headers) as r:
                    if r.status != 200:
                        return None
                    page = await r.json()
                if any(str(c.get("broadcaster_id")) == str(owner_id) for c in page.get("data", [])):
                    return True
                cursor = (page.get("pagination") or {}).get("cursor")
                if not cursor:
                    return False
    except (aiohttp.ClientError, ValueError):
        return None
    return False
