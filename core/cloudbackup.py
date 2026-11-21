"""1.20.0: Cloud backup (Settings > App > Cloud backup).

The same backup file as "Save a backup" (core/backup.py: the whole setup, never any login or key), made by itself and
kept somewhere safe:
  - "drive":  the streamer's own Google Drive, folder "FQPN's Chat Bot backups". Google's sign-in needs a secret key that
              must never be inside the app, so fqpnbot.com does those steps (web/worker.js, /gdrive/...), exactly like
              Sign in with Nightbot. The permission is drive.file: the app only ever sees the files it made itself.
              The long-term key is kept with Windows' own protection (DPAPI: only this Windows user on this PC can
              read it), in the channel's authentication folder (never in a backup).
  - "folder": any folder on this PC (OneDrive, a USB drive, ...). No sign-in.
Automatic: a backup once the setup hasn't changed for 5 minutes after a change, never while the stream is live (it
waits for the stream to end). Manual: only "Back up now". The last 10 backups of each channel are kept, older ones
are deleted by themselves. A missing folder or a lost Google sign-in never deletes anything: the page says so and the
app tries again."""
import base64
import hashlib
import json
import logging
import re
import secrets
import time
from datetime import datetime
from pathlib import Path

import aiohttp

from .publiclist import SITE

log = logging.getLogger(__name__)

SECTION = "cloud_backup"
DEFAULT = {"target": "", "mode": "auto", "folder": "", "email": "", "asked": False, "last": None, "error": "",
           "error_detail": "", "drive_folder": ""}
KEEP = 10                       # backups kept per channel
QUIET = 300                     # seconds without changes before an automatic backup
TICK = 60                       # how often the automatic check runs
PREFIX = "FQPN-Chat-Bot-backup-"
DRIVE_FOLDER = "FQPN's Chat Bot backups"
DRIVE = "https://www.googleapis.com/drive/v3/"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,size,createdTime"
REASONS = ("auto", "now", "before")
_NAME = re.compile(r"^" + re.escape(PREFIX) + r"(?P<login>[a-z0-9_]{1,25})-(?P<d>\d{4}-\d{2}-\d{2}-\d{6})-(?P<r>auto|now|before)\.fqpn$")


class CloudError(Exception):
    """code: missing (folder gone), not_setup (website), revoked (Google sign-in lost), denied, net, google, empty, ..."""
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code, self.detail = code, detail


# ---------- settings ----------

def settings(store) -> dict:
    s = dict(DEFAULT)
    got = store.get(SECTION)
    if isinstance(got, dict):
        s.update({k: got[k] for k in DEFAULT if k in got})
    if s["target"] not in ("", "drive", "folder"):
        s["target"] = ""
    if s["mode"] not in ("auto", "manual"):
        s["mode"] = "auto"
    return s


def save_settings(store, **changes) -> dict:
    s = settings(store)
    s.update({k: v for k, v in changes.items() if k in DEFAULT})
    store.save(SECTION, s)
    return s


def clean_login(login) -> str:
    t = re.sub(r"[^a-z0-9_]", "", str(login or "").lower())[:25]
    return t or "channel"


def file_name(login, reason: str, when: float = None) -> str:
    d = datetime.fromtimestamp(when or time.time())
    return f"{PREFIX}{clean_login(login)}-{d:%Y-%m-%d-%H%M%S}-{reason if reason in REASONS else 'now'}.fqpn"


def parse_name(name: str):
    """(login, when, reason) from a backup's file name, or None for any other file."""
    m = _NAME.match(str(name or ""))
    if not m:
        return None
    try:
        when = datetime.strptime(m.group("d"), "%Y-%m-%d-%H%M%S").timestamp()
    except ValueError:
        return None
    return m.group("login"), when, m.group("r")


def digest(b: dict) -> str:
    """What the automatic backup compares: the setup itself (not when the file was made)."""
    return hashlib.sha256(json.dumps(b.get("parts") or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------- the Google key (kept protected on this PC) ----------

def _token_path() -> Path:
    from . import accounts
    return accounts.auth_file("gdrive.json")


def save_refresh(token: str) -> None:
    from . import donations
    raw = token.encode("utf-8")
    if donations.can_encrypt():
        blob, enc = donations._dpapi(raw, True), True
    else:                                   # (running from source on another system)
        blob, enc = raw, False
    p = _token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"token": base64.b64encode(blob).decode("ascii"), "encrypted": enc}), encoding="utf-8")


def load_refresh():
    from . import donations
    try:
        entry = json.loads(_token_path().read_text(encoding="utf-8"))
        blob = base64.b64decode(entry["token"])
        raw = donations._dpapi(blob, False) if entry.get("encrypted") else blob
        return raw.decode("utf-8") or None
    except (OSError, ValueError, KeyError, TypeError):
        return None                         # none, or copied from another PC: connect again


def clear_refresh() -> None:
    try:
        _token_path().unlink(missing_ok=True)
    except OSError:
        pass
    ACCESS.clear()


ACCESS: dict = {}                           # the 1-hour key in memory only: {"token", "until"}


async def _http(method, url, **kw):
    timeout = aiohttp.ClientTimeout(total=kw.pop("timeout", 30))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.request(method, url, **kw) as r:
                body = await r.read()
                return r.status, body
    except (aiohttp.ClientError, TimeoutError, OSError) as e:
        raise CloudError("net", str(e)[:120])


async def access_token() -> str:
    if ACCESS.get("token") and ACCESS.get("until", 0) > time.time() + 60:
        return ACCESS["token"]
    rt = load_refresh()
    if not rt:
        raise CloudError("revoked")
    status, body = await _http("POST", SITE.rstrip("/") + "/api/gdrive/refresh", json={"refresh_token": rt}, timeout=20)
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        data = {}
    if status == 200 and data.get("access_token"):
        ACCESS.update(token=data["access_token"], until=time.time() + int(data.get("expires_in") or 3600))
        return ACCESS["token"]
    if data.get("error") == "revoked":
        clear_refresh()
        raise CloudError("revoked")
    if data.get("error") == "not_setup":
        raise CloudError("not_setup")
    raise CloudError("google", f"website {status}")


async def _drive(method, url, **kw):
    """A Drive call with a fresh key. Returns (status, body)."""
    tok = await access_token()
    headers = dict(kw.pop("headers", {}) or {})
    headers["Authorization"] = "Bearer " + tok
    status, body = await _http(method, url, headers=headers, **kw)
    if status == 401:                       # the 1-hour key ended early: once more with a new one
        ACCESS.clear()
        headers["Authorization"] = "Bearer " + await access_token()
        status, body = await _http(method, url, headers=headers, **kw)
    if status >= 400 and status != 404:
        why = ""
        try:
            err = (json.loads(body or b"{}").get("error") or {})
            why = str(err.get("message") or "")[:140] if isinstance(err, dict) else str(err)[:140]
        except ValueError:
            pass
        raise CloudError("google", f"drive {status}" + (f": {why}" if why else ""))
    return status, body


# ---------- sign in with Google (through fqpnbot.com) ----------

PENDING: dict = {}


def start_signin() -> str:
    PENDING.clear()
    PENDING.update(state=secrets.token_urlsafe(32), started=time.time())
    return SITE.rstrip("/") + "/gdrive/start?state=" + PENDING["state"]


async def check_signin():
    """None = still waiting; True = connected (the key is saved). CloudError otherwise."""
    state = PENDING.get("state")
    if not state:
        raise CloudError("denied")
    if time.time() - PENDING.get("started", 0) > 600:
        PENDING.clear()
        raise CloudError("timeout")
    try:
        status, body = await _http("GET", SITE.rstrip("/") + "/api/gdrive/token", params={"state": state}, timeout=10)
        data = json.loads(body or b"{}") if status == 200 else {"status": "error", "error": f"website {status}"}
    except (CloudError, ValueError):
        return None                         # (asked again in 2 seconds)
    if data.get("status") == "waiting":
        return None
    PENDING.clear()
    if data.get("status") != "ok" or not data.get("refresh_token"):
        err = data.get("error")
        raise CloudError(err if err in ("not_setup", "denied") else "google", str(err or "")[:80])
    save_refresh(data["refresh_token"])
    ACCESS.update(token=data.get("access_token") or "", until=time.time() + int(data.get("expires_in") or 3600))
    if not ACCESS["token"]:
        ACCESS.clear()
    return True


async def drive_email() -> str:
    try:
        status, body = await _drive("GET", DRIVE + "about", params={"fields": "user(emailAddress)"})
        return str((json.loads(body or b"{}").get("user") or {}).get("emailAddress") or "")[:120] if status == 200 else ""
    except (CloudError, ValueError):
        return ""


async def disconnect() -> None:
    rt = load_refresh()
    clear_refresh()
    if rt:                                  # tell Google too (needs no secret); a failure here changes nothing
        try:
            await _http("POST", "https://oauth2.googleapis.com/revoke", data={"token": rt}, timeout=10)
        except CloudError:
            pass


# ---------- where the backups go ----------

class FolderTarget:
    def __init__(self, folder: str):
        self.dir = Path(folder) if folder else None

    def _check(self):
        if not self.dir or not self.dir.is_dir():
            raise CloudError("missing", str(self.dir or ""))

    async def list(self, login: str) -> list:
        self._check()
        out = []
        for p in self.dir.glob(PREFIX + "*.fqpn"):
            got = parse_name(p.name)
            if got and got[0] == clean_login(login):
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                out.append({"id": p.name, "when": got[1], "reason": got[2], "size": size})
        return sorted(out, key=lambda x: -x["when"])

    async def write(self, name: str, text: str) -> None:
        self._check()
        tmp = self.dir / (name + ".part")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self.dir / name)
        except OSError as e:
            raise CloudError("write", str(e)[:120])

    async def read(self, fid: str) -> str:
        self._check()
        if not parse_name(fid):
            raise CloudError("not_found")
        try:
            return (self.dir / fid).read_text(encoding="utf-8")
        except OSError:
            raise CloudError("not_found")

    async def delete(self, fid: str) -> None:
        if parse_name(fid):                 # only ever one of our own backup files
            try:
                (self.dir / fid).unlink(missing_ok=True)
            except OSError:
                pass


class DriveTarget:
    def __init__(self, store):
        self.store = store

    async def _folder(self) -> str:
        s = settings(self.store)
        fid = s.get("drive_folder") or ""
        if fid:
            status, body = await _drive("GET", DRIVE + "files/" + fid, params={"fields": "id,trashed"})
            if status == 200 and not json.loads(body or b"{}").get("trashed"):
                return fid
        name = DRIVE_FOLDER.replace("\\", "\\\\").replace("'", "\\'")     # (Drive's search needs ' and \\ escaped: "FQPN\\'s")
        q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        status, body = await _drive("GET", DRIVE + "files", params={"q": q, "fields": "files(id)", "pageSize": "5"})
        files = json.loads(body or b"{}").get("files") or []
        if files:
            fid = files[0]["id"]
        else:
            status, body = await _drive("POST", DRIVE + "files", params={"fields": "id"},
                                        json={"name": DRIVE_FOLDER, "mimeType": "application/vnd.google-apps.folder"})
            fid = json.loads(body or b"{}").get("id") or ""
            if not fid:
                raise CloudError("google", "folder")
        save_settings(self.store, drive_folder=fid)
        return fid

    async def list(self, login: str) -> list:
        folder = await self._folder()
        q = f"'{folder}' in parents and trashed = false"
        status, body = await _drive("GET", DRIVE + "files", params={"q": q, "pageSize": "200", "orderBy": "createdTime desc",
                                                                    "fields": "files(id,name,size)"})
        out = []
        for f in json.loads(body or b"{}").get("files") or []:
            got = parse_name(f.get("name"))
            if got and got[0] == clean_login(login):
                out.append({"id": f["id"], "when": got[1], "reason": got[2], "size": int(f.get("size") or 0)})
        return sorted(out, key=lambda x: -x["when"])

    async def write(self, name: str, text: str) -> None:
        folder = await self._folder()
        boundary = "fqpn" + secrets.token_hex(12)
        meta = json.dumps({"name": name, "parents": [folder], "mimeType": "application/json",
                           "appProperties": {"fqpnbot": "1"}})
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                f"--{boundary}\r\nContent-Type: application/json\r\n\r\n").encode("utf-8") + text.encode("utf-8") + \
               f"\r\n--{boundary}--".encode("utf-8")
        await _drive("POST", UPLOAD, data=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"}, timeout=120)

    async def read(self, fid: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", str(fid or "")):
            raise CloudError("not_found")
        status, body = await _drive("GET", DRIVE + "files/" + fid, params={"alt": "media"}, timeout=120)
        if status != 200:
            raise CloudError("not_found")
        return body.decode("utf-8-sig", errors="replace")

    async def delete(self, fid: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{10,200}", str(fid or "")):
            try:
                await _drive("DELETE", DRIVE + "files/" + fid)
            except CloudError:
                pass


def target(store):
    s = settings(store)
    if s["target"] == "drive":
        return DriveTarget(store)
    if s["target"] == "folder":
        return FolderTarget(s["folder"])
    return None


# ---------- backing up ----------

async def back_up(store, b: dict, login: str, reason: str = "now") -> dict:
    """Write one backup (the dict from backup.make), then keep only the newest KEEP. Returns the new "last"."""
    from . import backup
    t = target(store)
    if t is None:
        raise CloudError("off")
    name = file_name(login, reason)
    try:
        await t.write(name, backup.dumps(b))
        olds = await t.list(login)
        for old in olds[KEEP:]:
            await t.delete(old["id"])
    except CloudError as e:
        log.warning("Cloud backup didn't work (%s %s)", e.code, e.detail)
        save_settings(store, error=e.code, error_detail=str(e.detail or "")[:160])
        raise
    last = {"at": int(time.time()), "reason": reason, "digest": digest(b), "files": len(b.get("parts") or {})}
    save_settings(store, last=last, error="", error_detail="")
    log.info("Cloud backup: saved %s (%s)", name, settings(store)["target"])
    return last


async def history(store, login: str) -> list:
    t = target(store)
    if t is None:
        return []
    try:
        got = await t.list(login)
    except CloudError as e:
        save_settings(store, error=e.code, error_detail=str(e.detail or "")[:160])
        raise
    if settings(store).get("error") in ("missing", "net", "google"):
        save_settings(store, error="", error_detail="")
    return got[:KEEP]


async def fetch(store, fid: str) -> str:
    t = target(store)
    if t is None:
        raise CloudError("off")
    return await t.read(fid)


class Auto:
    """The automatic backup: call tick() every minute. It backs up once the setup has stayed the same for QUIET seconds
    after a change, never while live (that waits for the stream to end), and never twice for the same setup."""
    def __init__(self):
        self.seen = None            # the digest at the last check
        self.since = None           # when it last changed
        self.busy = False

    async def tick(self, store, make, login: str, live: bool, now: float = None) -> bool:
        now = now or time.time()
        s = settings(store)
        if s["target"] == "" or s["mode"] != "auto" or self.busy:
            return False
        if s["target"] == "drive" and not load_refresh():
            if s.get("error") != "revoked":
                save_settings(store, error="revoked")
            return False
        b = make()
        d = digest(b)
        if d != self.seen:
            self.seen, self.since = d, now
        if d == ((s.get("last") or {}).get("digest")):
            return False                    # already backed up exactly this
        if live or now - (self.since or now) < QUIET:
            return False
        self.busy = True
        try:
            await back_up(store, b, login, "auto")
            return True
        except CloudError as e:
            log.warning("Cloud backup: automatic backup didn't work (%s %s)", e.code, e.detail)
            return False
        finally:
            self.busy = False


AUTO = Auto()
