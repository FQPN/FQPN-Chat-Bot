"""Twitch authentication using the Device Code flow (Public client, no secret)."""

import asyncio
import json
import time
import webbrowser
from pathlib import Path

import aiohttp

CLIENT_ID = "sk61bb5z9anwbymut5y6svq13q6q5c"  # Public client ID for the bot. No secret is needed for device flow."
SCOPES = [
    "user:read:chat",
    "user:write:chat",
    "moderator:manage:announcements",  # /announce
    "channel:manage:broadcast",        # !title and !game changes
    "moderator:read:followers",
    "channel:read:hype_train",
]
last_problem: str | None = None  # set to "permissions" when a reconnect is needed for new scopes

AUTH_DIR = Path(__file__).resolve().parent.parent / "authentication"
TOKEN_FILE = AUTH_DIR / "token.json"

DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"


class AuthError(Exception):
    pass


# ---------- local storage ----------

def load_token() -> dict | None:
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_token(data: dict) -> None:
    AUTH_DIR.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_token() -> None:
    TOKEN_FILE.unlink(missing_ok=True)


def _store_response(resp: dict) -> dict:
    data = {
        "access_token": resp["access_token"],
        "refresh_token": resp["refresh_token"],
        "expires_at": time.time() + int(resp.get("expires_in", 0)),
        "scopes": resp.get("scope", SCOPES),
    }
    save_token(data)
    return data


# ---------- Twitch calls ----------

async def validate(session: aiohttp.ClientSession, access_token: str) -> dict | None:
    """Returns {'login', 'user_id', ...} if the token is valid, else None."""
    async with session.get(
        VALIDATE_URL, headers={"Authorization": f"OAuth {access_token}"}
    ) as r:
        if r.status != 200:
            return None
        return await r.json()


async def refresh(session: aiohttp.ClientSession, refresh_token: str) -> dict:
    async with session.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    ) as r:
        resp = await r.json()
        if r.status != 200:
            raise AuthError(f"Refresh failed: {resp.get('message', r.status)}")
        return _store_response(resp)


async def device_login(on_code=None, open_browser: bool = True) -> dict:
    """
    Runs the Connect Twitch flow.
    on_code(user_code, verification_uri) is called so a UI can display the code.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            DEVICE_URL,
            data={"client_id": CLIENT_ID, "scopes": " ".join(SCOPES)},
        ) as r:
            dev = await r.json()
            if r.status != 200:
                raise AuthError(f"Could not start login: {dev.get('message', r.status)}")

        uri = dev["verification_uri"]
        code = dev["user_code"]
        if on_code:
            on_code(code, uri)
        else:
            print(f"\nGo to {uri} and enter code: {code}\n")
        if open_browser:
            webbrowser.open(uri)

        interval = int(dev.get("interval", 5))
        deadline = time.time() + int(dev.get("expires_in", 1800))

        while time.time() < deadline:
            await asyncio.sleep(interval)
            async with session.post(
                TOKEN_URL,
                data={
                    "client_id": CLIENT_ID,
                    "scopes": " ".join(SCOPES),
                    "device_code": dev["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            ) as r:
                resp = await r.json()
                if r.status == 200:
                    return _store_response(resp)
                if resp.get("message") == "authorization_pending":
                    continue
                raise AuthError(f"Login failed: {resp.get('message', r.status)}")

        raise AuthError("Login timed out. Click Connect Twitch to try again.")


# ---------- main entry point ----------

async def get_account() -> dict | None:
    """
    Returns {'access_token', 'refresh_token', 'login', 'user_id'} for the
    connected account, or None if nobody is connected (bot should not run).
    """
    data = load_token()
    if not data:
        return None

    async with aiohttp.ClientSession() as session:
        try:
            if data["expires_at"] - time.time() < 120:
                data = await refresh(session, data["refresh_token"])

            info = await validate(session, data["access_token"])
            if info is None:
                data = await refresh(session, data["refresh_token"])
                info = await validate(session, data["access_token"])
            if info is None:
                raise AuthError("Token invalid after refresh")
            global last_problem
            last_problem = None
            if set(SCOPES) - set(info.get("scopes", [])):
                # Saved before the bot needed these permissions: ask the user to reconnect.
                last_problem = "permissions"
                clear_token()
                return None
        except (AuthError, aiohttp.ClientError):
            clear_token()
            return None

    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "login": info["login"],
        "user_id": info["user_id"],
    }


def disconnect() -> None:
     clear_token()