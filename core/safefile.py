"""Safe JSON files (1.12.0). Used for every data file, so a crash, a full disk or a damaged file can never cost data.

- read():  "ok" + data | "missing" | "corrupt" (an empty or unreadable file is CORRUPT, never "nothing saved").
- write(): atomic. The new content goes to <name>.tmp, is flushed to disk, and only then replaces the file, so a crash
           halfway leaves the old file intact. The last good version is kept as <name>.bak before it is replaced.
- quarantine(): a corrupt file is COPIED aside (<name>.corrupt-<time>.json) before anything else happens to it.
- restore_backup(): a corrupt file is replaced by its last good <name>.bak, if that one reads fine (the corrupt one was
           quarantined first)."""

import json
import logging
import os
import shutil
import time
from pathlib import Path

log = logging.getLogger("twitchbot.safefile")


def read(path):
    """(status, data): ("ok", data) | ("missing", None) | ("corrupt", None) | ("error", None) (could not be opened)."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "error", None
    if not raw.strip():
        return "corrupt", None              # an empty file is a crash in the middle of a save, not "no data"
    try:
        return "ok", json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return "corrupt", None


def bak_path(path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".bak")


def write(path, data, backup: bool = True) -> None:
    """Writes JSON atomically. Keeps the previous good version as <file>.bak (only when it reads fine)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    if backup and path.exists() and read(path)[0] == "ok":
        try:
            shutil.copy2(path, bak_path(path))
        except OSError:
            log.warning("Could not keep a backup of %s", path.name)
    os.replace(tmp, path)


def quarantine(path):
    """Copies a damaged file aside (never moves or deletes it). Returns the copy's path, or None."""
    path = Path(path)
    if not path.exists():
        return None
    dest = path.with_name(f"{path.stem}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}")
    n = 1
    while dest.exists():
        dest = path.with_name(f"{path.stem}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}-{n}{path.suffix}")
        n += 1
    try:
        shutil.copy2(path, dest)
        return dest
    except OSError:
        log.exception("Could not copy the damaged file %s aside", path.name)
        return None


def restore_backup(path):
    """If <file>.bak is good, puts it back as <file> (after the damaged file was quarantined). Returns the data or None."""
    path = Path(path)
    status, data = read(bak_path(path))
    if status != "ok":
        return None
    try:
        tmp = path.with_name(path.name + ".tmp")
        shutil.copy2(bak_path(path), tmp)
        os.replace(tmp, path)
    except OSError:
        log.exception("Could not restore %s from its backup", path.name)
        return None
    return data
