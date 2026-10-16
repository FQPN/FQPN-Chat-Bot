"""Several Twitch channels in one app (1.12.0): the list of accounts, where each one's files are, and the one-time move
from the old layout (everything in data/ and one token.json) to one folder per channel.

    data/accounts.json                    the channels, the bot accounts, which channel the app shows, the migration record
    data/ui.json, data/prefs.json         shared by every channel (language, theme, window, start-up, notifications)
    data/channels/<user id>/...           one channel's commands, timers, greetings, moderation, games, logs, settings
    authentication/channels/<user id>/token.json      that channel's Twitch login
    data/backups/backup-before-1.12.0-<time>.zip     everything as it was, made BEFORE the first copy

The migration COPIES (never moves or deletes): the old files stay where they were, as a second backup. Every copy is
checked byte for byte; accounts.json is written last, only when all of it went fine. If anything fails, the app keeps
using the old files exactly as before, and tries again at the next start."""

import contextvars
import filecmp
import logging
import shutil
import time
import zipfile
from pathlib import Path

from . import safefile
from . import store as storemod

log = logging.getLogger("twitchbot.accounts")

VERSION = 1
# Which channel the running code works for. Each channel's bot and background tasks run with this set (it follows
# asyncio tasks), so a login or a file is always that channel's. ACTIVE is the one the app shows when nothing is set.
CURRENT = contextvars.ContextVar("fqpn_channel", default=None)
ACTIVE = {"id": None}
APP_FILES = {"accounts.json", "running.json"} | {f"{n}.json" for n in storemod.SHARED}


def current_channel():
    return CURRENT.get() or ACTIVE["id"]


def _auth_dir() -> Path:
    from . import auth
    return Path(getattr(auth, "AUTH_DIR", None) or Path(__file__).resolve().parent.parent / "authentication")


def registry_path() -> Path:
    return storemod.DATA_DIR / "accounts.json"


def channel_dir(cid) -> Path:
    return storemod.DATA_DIR / "channels" / str(cid)


def channel_token_file(cid) -> Path:
    return _auth_dir() / "channels" / str(cid) / "token.json"


def channel_auth_file(cid, name: str) -> Path:
    """Another of a channel's own login files: donations.json (Streamlabs / StreamElements), bot_token.json (its separate
    bot account, until 1.12.0's shared bot list takes over)."""
    return _auth_dir() / "channels" / str(cid) / name


def auth_file(name: str) -> Path:
    """donations.json / bot_token.json for the channel the running code works for (the old single file before the move)."""
    cid = current_channel()
    return channel_auth_file(cid, name) if cid else _auth_dir() / name


def bot_token_file(bid) -> Path:
    return _auth_dir() / "bots" / str(bid) / "token.json"


def load():
    """The registry, or None (the old layout: not migrated yet, or accounts.json unusable -> keep using the old files)."""
    status, data = safefile.read(registry_path())
    if status == "corrupt":
        safefile.quarantine(registry_path())
        data = safefile.restore_backup(registry_path())
        status = "ok" if data is not None else "corrupt"
        log.error("accounts.json was damaged: %s", "restored its backup" if data is not None else "using the old layout")
    if status != "ok" or not isinstance(data, dict) or not isinstance(data.get("channels"), list) or not data["channels"]:
        return None
    data.setdefault("bots", [])
    if data.get("active") not in [c.get("id") for c in data["channels"]]:
        data["active"] = data["channels"][0].get("id")
    return data


def save(reg: dict) -> None:
    if not reg.get("channels"):
        raise ValueError("Refusing to save an account list without any channel")      # never an empty list over real data
    safefile.write(registry_path(), reg)


def legacy_files() -> list:
    """The pre-1.12.0 channel files in data/ (every *.json / *.jsonl except the shared and app files and safety copies)."""
    out = []
    for p in sorted(storemod.DATA_DIR.glob("*")):
        if not p.is_file() or p.name in APP_FILES:
            continue
        if p.suffix not in (".json", ".jsonl") or ".corrupt-" in p.name:
            continue
        out.append(p)
    return out


def backup_zip(reason: str = "before-1.12.0") -> Path:
    """Zips data/ (files only) and the logins, then checks the zip can be read back. Raises if anything is wrong."""
    folder = storemod.DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"backup-{reason}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    names = []
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(storemod.DATA_DIR.glob("*")):
            if p.is_file() and p.suffix in (".json", ".jsonl", ".bak"):
                z.write(p, "data/" + p.name)
                names.append("data/" + p.name)
        auth_dir = _auth_dir()
        if auth_dir.exists():
            for p in sorted(auth_dir.glob("*")):
                if p.is_file():
                    z.write(p, "authentication/" + p.name)
                    names.append("authentication/" + p.name)
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None or sorted(z.namelist()) != sorted(names):
            raise OSError("The backup zip could not be read back")
    return dest


def _copy_checked(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if not filecmp.cmp(src, dst, shallow=False):
        raise OSError(f"The copy of {src.name} is not identical")


def migrate_legacy(account: dict, token_file=None):
    """Copies the old layout into data/channels/<id>/ for this (first) channel. Returns the channel id, or None when
    something failed (then nothing changes: the app keeps using the old files)."""
    if load() is not None:
        return None
    cid = str(account.get("user_id") or "")
    if not cid.isdigit():
        return None
    try:
        zipped = backup_zip()
        for src in legacy_files():
            _copy_checked(src, channel_dir(cid) / src.name)
        for src in legacy_files():                # the checked copies must also read as valid JSON when the original did
            if src.suffix == ".json" and safefile.read(src)[0] == "ok" and safefile.read(channel_dir(cid) / src.name)[0] != "ok":
                raise OSError(f"The copy of {src.name} can't be read")
        from . import auth
        tok = Path(token_file or auth.TOKEN_FILE)
        if tok.exists():
            _copy_checked(tok, channel_token_file(cid))
        for name in ("donations.json", "bot_token.json"):      # the channel's other logins
            src = _auth_dir() / name
            if src.exists():
                _copy_checked(src, channel_auth_file(cid, name))
        reg = {"version": VERSION, "active": cid,
               "channels": [{"id": cid, "login": str(account.get("login") or ""), "added": int(time.time()), "sender": "own"}],
               "bots": [],
               "migrated": {"at": int(time.time()), "backup": zipped.name, "files": [p.name for p in legacy_files()]}}
        save(reg)                                  # last: only now does the app switch to the new layout
        log.info("Moved to one folder per channel (copied %d files; the old ones stay as they were; backup %s)",
                 len(reg["migrated"]["files"]), zipped.name)
        return cid
    except Exception:
        log.exception("The move to one folder per channel failed: the app keeps using the old files and tries again later")
        return None
