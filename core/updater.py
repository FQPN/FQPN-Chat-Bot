"""Checks GitHub for a newer release, downloads its installer in the background, and runs it silently.
Your commands, timers and Twitch login live outside the program folder, so an update never touches them.
Uses only the standard library, so it also works inside the installed app."""

import asyncio
import hashlib
import json
import logging
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import version as _version

log = logging.getLogger("updater")

REPO = "FQPN/FQPN-Chat-Bot"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ALLOWED_PREFIX = f"https://github.com/{REPO}/releases/download/"     # downloads must come from this project's releases
ASSET_RE = re.compile(r"^FQPN-Chat-Bot-Setup-.+\.exe$")
CHECK_EVERY = 6 * 3600
FIRST_CHECK_DELAY = 20               # seconds after start before the first look (so start-up stays quick)
UPDATES_DIR = Path("updates")        # the launcher points this at the user's data folder
HEADERS = {"User-Agent": "FQPNsChatBot-updater", "Accept": "application/vnd.github+json"}

U: dict = {}                          # the one shared update state (dashboard, main loop and launcher all read it)


def new_state() -> dict:
    return {"status": "idle", "current": current(), "latest": None, "notes": "", "progress": 0,
            "error": None, "path": None, "asset": None, "checked": None}


def current() -> str:
    return str(_version.VERSION)


def is_dev(v: str | None = None) -> bool:
    return (v or current()).startswith("0.0.0")


def parse(v) -> tuple | None:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(v))
    return tuple(int(x) for x in m.groups()) if m else None


def newer(latest, cur) -> bool:
    a, b = parse(latest), parse(cur)
    return bool(a and b and a > b)


def pick_asset(release: dict):
    """The installer attached to a release, or None."""
    for a in release.get("assets") or []:
        name, url = str(a.get("name", "")), str(a.get("browser_download_url", ""))
        if ASSET_RE.match(name) and url.startswith(ALLOWED_PREFIX):
            digest = str(a.get("digest") or "")
            sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
            return {"name": name, "url": url, "size": int(a.get("size") or 0), "sha256": sha}
    return None


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as r:
        return json.load(r)


def fetch_latest() -> dict:
    rel = _get_json(API_URL)
    return {"version": str(rel.get("tag_name", "")).lstrip("v"), "notes": str(rel.get("body") or "")[:2000],
            "asset": pick_asset(rel)}


def _nice(e: Exception) -> str:
    text = str(e)
    if "404" in text:
        return "No release was found. The project must be public on GitHub."
    if "403" in text or "429" in text:
        return "GitHub is limiting requests right now. Try again later."
    return text[:200] or e.__class__.__name__


async def check(u: dict) -> dict:
    """Asks GitHub whether a newer version exists."""
    if is_dev():
        u.update(status="dev")
        return u
    if u["status"] in ("downloading", "ready"):
        return u
    u.update(status="checking", error=None)
    try:
        info = await asyncio.to_thread(fetch_latest)
    except Exception as e:
        log.warning("Update check failed: %s", e)
        u.update(status="error", error=_nice(e))
        return u
    u["checked"] = time.time()
    if info["asset"] and newer(info["version"], current()):
        u.update(status="available", latest=info["version"], notes=info["notes"], asset=info["asset"])
    else:
        u.update(status="uptodate", latest=info["version"] or current(), asset=None)
    return u


def _download(u: dict) -> Path:
    asset = u["asset"]
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    target = UPDATES_DIR / asset["name"]
    part = target.with_suffix(".part")
    sha, done = hashlib.sha256(), 0
    with urllib.request.urlopen(urllib.request.Request(asset["url"], headers=HEADERS), timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or asset["size"] or 0)
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if total:
                u["progress"] = min(99, int(done * 100 / total))
    if asset["size"] and done != asset["size"]:
        part.unlink(missing_ok=True)
        raise ValueError("The download was incomplete. Try again.")
    if asset["sha256"] and sha.hexdigest() != asset["sha256"]:
        part.unlink(missing_ok=True)
        raise ValueError("The download didn't match its checksum, so it was thrown away.")
    part.replace(target)
    return target


async def download(u: dict) -> dict:
    """Downloads the installer found by check()."""
    if u["status"] not in ("available", "error") or not u.get("asset"):
        return u
    u.update(status="downloading", progress=0, error=None)
    try:
        path = await asyncio.to_thread(_download, u)
    except Exception as e:
        log.warning("Update download failed: %s", e)
        u.update(status="error", error=_nice(e))
        return u
    u.update(status="ready", progress=100, path=str(path))
    return u


def installer_command(path, relaunch: bool) -> list:
    cmd = [str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    if relaunch:
        cmd.append("/RELAUNCH=1")     # the installer starts the app again when it is done
    return cmd


def launch_installer(path, relaunch: bool) -> None:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(installer_command(path, relaunch), close_fds=True, creationflags=flags)


def ready_installer(u: dict):
    """The downloaded installer, if there is one waiting and it is where we put it."""
    p = u.get("path")
    if u.get("status") == "ready" and p:
        path = Path(p)
        if path.is_file() and path.parent.resolve() == UPDATES_DIR.resolve():
            return path
    return None


def install(u: dict, relaunch: bool = True) -> bool:
    """Starts the downloaded installer. The caller then closes the app so the installer can replace its files."""
    path = ready_installer(u)
    if not path:
        return False
    launch_installer(path, relaunch)
    u["status"] = "installing"        # so it is never started twice (for example again when the app closes)
    return True


def cleanup() -> None:
    """Removes half-finished downloads and installers of versions we already have."""
    try:
        for f in UPDATES_DIR.glob("*"):
            ver = re.search(r"(\d+\.\d+\.\d+)", f.name)
            if f.suffix == ".part" or (ver and not newer(ver.group(1), current())):
                f.unlink(missing_ok=True)
    except OSError:
        pass


async def loop(u: dict, store, wake: asyncio.Event) -> None:
    """Background task: look for updates now and then, and download them quietly when 'Check for updates automatically' is on."""
    await asyncio.sleep(FIRST_CHECK_DELAY)
    while True:
        try:
            if store.get("prefs").get("auto_update", True) and not is_dev() and u["status"] not in ("downloading", "ready"):
                await check(u)
                if u["status"] == "available":
                    await download(u)
        except Exception:
            log.exception("Update loop failed")
        wake.clear()
        try:
            await asyncio.wait_for(wake.wait(), CHECK_EVERY)    # woken early when the setting is switched on
        except asyncio.TimeoutError:
            pass


U.update(new_state())
