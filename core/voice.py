"""1.17.0 (beta, owner): Voice commands. Hold a key, say what the bot should do, let go.

How it works (Windows only):
  - Settings > Voice switches it on. The first time, the speech engine (whisper.cpp, free and open source) and its
    speech model are downloaded into %APPDATA%\\TwitchChatBot\\voice. Nothing else is downloaded, ever.
  - Until the push-to-talk key is pressed, nothing runs except a check of that one key a few times a second. The
    microphone is closed and the speech engine isn't started.
  - Pressing the key opens the microphone, shows the mic in a corner of the screen, and starts the speech engine if it
    isn't running (the first time takes a second or two; it loads while you talk). Letting go turns what was said into
    text on this PC (nothing is sent anywhere), and core/voiceparse.py turns the text into an action.
  - The engine is stopped again after 5 minutes without use, and when the app closes or Voice is switched off.
  - Timeout and ban always ask first ("say yes / no", or 1 / 2 / 3 to pick the person); with "Ask before safe actions
    too" the others ask as well. The question also shows in the app, with buttons.
"""
import asyncio
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
import zipfile
from pathlib import Path

from . import voiceparse as VP
from .voiceoverlay import OVERLAY

log = logging.getLogger("voice")

WINDOWS = sys.platform == "win32"
ENGINE_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.1/whisper-bin-x64.zip"
ENGINE_SHA256 = "7d8be46ecd31828e1eb7a2ecdd0d6b314feafd82163038ab6092594b0a063539"     # whisper.cpp 1.9.1, CPU build
ENGINE_FILES = ("whisper-server.exe", "whisper.dll", "ggml.dll", "ggml-base.dll", "SDL2.dll")      # + every ggml-cpu-*.dll
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin"
MODEL_FILE = "ggml-small-q5_1.bin"
MODEL_MIN = 150_000_000          # a smaller file is a broken download
# Settings > Voice > Speech model: (file, minimum size, size for the progress bar, engine threads at most)
MODELS = {
    "small": ("ggml-small-q5_1.bin", 150_000_000, 190_000_000, 4),               # fast
    "turbo": ("ggml-large-v3-turbo-q5_0.bin", 450_000_000, 574_000_000, 6),     # accurate (much better Arabic), slower
    "best": ("ggml-large-v3-q5_0.bin", 1_000_000_000, 1_081_000_000, 8),        # 1.17.0: the full large-v3 (all 32 decoder layers): the most accurate, the slowest
}
MODEL_SHA256 = {"ggml-large-v3-q5_0.bin": "d75795ecff3f83b5faa89d1900604ad8c780abd5739fae406de19f23ecd98ad1"}   # checked after the download
# 1.17.0: speed. The engine tries a few readings and keeps the best (beam search): more on a graphics card, fewer on the
# processor for the big models (each one costs time there). It only looks at as much audio as was recorded (audio_ctx),
# instead of a full 30 seconds every time, which is most of the waiting on a processor.
BEAMS = {"small": 5, "turbo": 3, "best": 2}
GPU_BEAM = 5
# The graphics-card engine (NVIDIA, CUDA 11.8: any driver from the last few years): whisper.cpp 1.9.1's own build
GPU_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.1/whisper-cublas-11.8.0-bin-x64.zip"
GPU_SHA256 = "aecdce0e4d4bb758a7c72a31f3f9f19a7b6d861405fd2da743cd86398633c963"
GPU_SIZE = 278_557_654


def has_nvidia() -> bool:
    """An NVIDIA graphics card with its driver (the driver puts nvcuda.dll in System32)."""
    return WINDOWS and (Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "nvcuda.dll").is_file()
HF = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
ENGINE_SIZE = 8_000_000
MODEL_SIZE = 190_000_000         # (for the progress bar until the real size is known)
IDLE_STOP = 300                  # stop the engine after 5 minutes without use
MAX_RECORD = 15                  # seconds
ASK_SECONDS = 20                 # a question waits this long for yes / no
RATE = 16000
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # the engine on this PC: never through a proxy

ACTIONS = ("timeout", "ban", "reset", "game", "title", "say", "roles", "cmds", "ignore", "clear", "chatbox")     # the switches (1.18.0: + roles … chatbox)
ACTION_OF = {"timeout": "timeout", "ban": "ban", "unban": "ban", "reset": "reset", "game": "game", "title": "title", "setgame": "title", "say": "say",
             "vip": "roles", "unvip": "roles", "mod": "roles", "unmod": "roles",
             "count": "reset", "runcmd": "cmds", "ignore": "ignore", "unignore": "ignore", "clear": "clear",
             "hidechat": "chatbox", "showchat": "chatbox"}
ROLE_ACTS = ("vip", "unvip", "mod", "unmod")          # 1.18.0: VIP and moderator (the channel account's own Twitch login does it)
ALWAYS_ASK = ("timeout", "ban", "unban") + ROLE_ACTS + ("ignore", "unignore", "clear")
HISTORY = 20                                            # 1.18.0: the last voice commands shown on the Voice page
FIXES_MAX = 300                                         # 1.18.0: spelling fixes kept (yours + learned)
DEFAULTS = {"voice": False, "voice_key": "F9", "voice_mic": "", "voice_lang": "both",
            "voice_acts": ["timeout", "ban", "reset", "game", "say"], "voice_ask_all": False, "voice_beep": True,
            "voice_overlay": True, "voice_corner": "tr", "voice_style": "orb", "voice_model": "small",
            "hotkeys_on": False, "hotkeys": [], "hotkeys_sound": True, "voice_gpu": False}

# Hotkeys (1.17.0, owner): a key, anywhere (even in a game), does one thing. They don't need the speech engine.
HOT_ACTS = ("add", "sub", "say", "game")        # counter +1, counter -1, send a message / command, start a mini game
HOT_MAX = 12
MOD_VK = {"Ctrl": 0x11, "Alt": 0x12, "Shift": 0x10}


def hot_combo(combo):
    """"Ctrl+Shift+KeyD" / "Mouse4+KeyQ" / "F1+F2" -> (the modifiers, the other keys), or None when it can't be watched.
    Up to 4 keys together. Letters, numbers and ` need Ctrl, Alt or a key you don't type with (an F key, a mouse
    button…), so typing in chat or in the app doesn't set them off. A modifier key alone (like Right Ctrl) is fine."""
    parts = str(combo or "").split("+")
    mods = [x for x in parts if x in MOD_VK]
    keys = [x for x in parts if x not in MOD_VK]
    if not keys or len(parts) > 4 or len(set(parts)) != len(parts) or any(k not in VK for k in keys):
        return None
    if any(k.startswith(("Control", "Alt", "Shift")) for k in keys) and len(parts) > 1:
        return None
    if all(k.startswith(("Key", "Digit")) or k == "Backquote" for k in keys) and not {"Ctrl", "Alt"} & set(mods):
        return None
    return set(mods), tuple(keys)


# browser key names (what the Settings page records) -> Windows key codes
VK = {"Mouse4": 0x05, "Mouse5": 0x06, "Insert": 0x2D, "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
      "Pause": 0x13, "ScrollLock": 0x91, "CapsLock": 0x14, "ControlRight": 0xA3, "ControlLeft": 0xA2, "AltRight": 0xA5,
      "AltLeft": 0xA4, "ShiftRight": 0xA1, "ShiftLeft": 0xA0, "Backquote": 0xC0, "NumpadAdd": 0x6B, "NumpadSubtract": 0x6D,
      "NumpadMultiply": 0x6A, "NumpadDivide": 0x6F, "NumpadDecimal": 0x6E, "NumpadEnter": 0x0D}
VK.update({f"F{i}": 0x6F + i for i in range(1, 25)})
VK.update({f"Key{c}": ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"})
VK.update({f"Digit{i}": 0x30 + i for i in range(10)})
VK.update({f"Numpad{i}": 0x60 + i for i in range(10)})

TEXT = {   # what the corner overlay says (short)
    "en": {"listen": "Listening…", "think": "Working it out…", "nothing": "Didn't catch a command", "off": "{a} is off for voice",
           "ask_who": "{a} — who?", "ask": "{a}?", "say": "Hold {k}: yes / no", "say_pick": "Hold {k}: 1, 2 or 3 · no",
           "done": "Done", "cancel": "Cancelled", "timeout": "Timeout {m}", "ban": "Ban", "unban": "Unban", "vip": "VIP", "unvip": "Remove VIP", "mod": "Make mod", "unmod": "Remove mod", "ignore": "Ignore", "unignore": "Stop ignoring", "clear": "Clear chat", "nobody": "Nobody like “{w}” in chat",
           "fail": "Didn't work", "first": "Starting voice…"},
    "ar": {"listen": "أسمعك…", "think": "لحظة…", "nothing": "ما فهمت أمر", "off": "{a} مقفل للصوت",
           "ask_who": "{a} — مين؟", "ask": "{a}؟", "say": "اضغط {k}: نعم / لا", "say_pick": "اضغط {k}: 1 أو 2 أو 3 · لا",
           "done": "تم", "cancel": "انلغى", "timeout": "تايم اوت {m}", "ban": "بان", "unban": "فك البان", "vip": "في آي بي", "unvip": "شيل الفي آي بي", "mod": "مشرف", "unmod": "شيل الإشراف", "ignore": "تجاهل", "unignore": "فك التجاهل", "clear": "مسح الشات", "nobody": "ما فيه أحد مثل «{w}» في الشات",
           "fail": "ما زبط", "first": "تشغيل الصوت…"},
}


def _app_voice_dir() -> Path:
    from . import store
    return Path(store.DATA_DIR).parent / "voice"


def voice_dir() -> Path:
    """Where the speech engine and model go. The installed app: %APPDATA%\\TwitchChatBot\\voice. Running from the
    source (VS Code): %USERPROFILE%\\.fqpn-voice, because a Python from the Microsoft Store secretly moves everything it
    saves in AppData to a hidden folder, where the speech engine then can't find its own files."""
    if getattr(sys, "frozen", False):
        return _app_voice_dir()
    return Path(os.environ.get("USERPROFILE") or Path.home()) / ".fqpn-voice"


def _move_old_download() -> None:
    """A download made by an earlier test (into the AppData folder) is moved, so it isn't downloaded again."""
    new, old = voice_dir(), _app_voice_dir()
    if new == old or not old.is_dir() or (new / MODEL_FILE).is_file():
        return
    try:
        new.mkdir(parents=True, exist_ok=True)
        for f in old.rglob("*"):
            if f.is_file():
                t = new / f.relative_to(old)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
        shutil.rmtree(old, ignore_errors=True)
        log.info("Voice: moved the speech engine and model to %s", new)
    except OSError:
        log.exception("Voice: could not move the earlier download")


def prefs_of(prefs: dict) -> dict:
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        if k in (prefs or {}):
            out[k] = prefs[k]
    return out


def mins_text(secs: int, ar: bool) -> str:
    if secs % 3600 == 0:
        h = secs // 3600
        return (f"{h} ساعة" if ar else f"{h} h")
    if secs % 60 == 0:
        return (f"{secs // 60} دقيقة" if ar else f"{secs // 60} min")
    return (f"{secs} ثانية" if ar else f"{secs} s")


class Voice:
    """One per app. start(state, loop) from main.py; everything else happens on its own threads."""

    def __init__(self):
        self.state = None
        self.loop = None
        self.status = {"engine": "missing", "done": 0, "total": 0, "error": "", "server": "off", "last": None,
                       "pending": None, "heard_at": 0}
        self.lock = threading.Lock()
        self.dl_thread = None
        self.dl_cancel = threading.Event()
        self.key_thread = None
        self.key_stop = threading.Event()
        self.hot_thread = None
        self.hot_stop = threading.Event()
        self.proc = None
        self.port = None
        self.used = 0.0
        self.busy = False
        self.gpu_failed = False
        self.eng_size = ENGINE_SIZE
        self.check_engine()

    # ---------- setup ----------

    def start(self, state, loop) -> None:
        self.state, self.loop = state, loop
        _move_old_download()
        self.check_engine()
        self._kill_strays()
        threading.Thread(target=self._watch, name="voice-watch", daemon=True).start()

    def prefs(self) -> dict:
        try:
            st = self.state.rt().store if self.state is not None else None
            return prefs_of(st.get("prefs") if st is not None else {})
        except Exception:
            return dict(DEFAULTS)

    def lang(self) -> str:
        try:
            return "ar" if (self.state.rt().store.get("ui") or {}).get("language") == "ar" else "en"
        except Exception:
            return "en"

    def t(self, key: str, **kw) -> str:
        return TEXT[self.lang()][key].format(**kw)

    def model(self) -> tuple:
        """(key, file, minimum size, expected size, threads) of the speech model chosen in Settings."""
        key = self.prefs().get("voice_model")
        key = key if key in MODELS else "small"
        return (key,) + MODELS[key]

    def use_gpu(self) -> bool:
        return bool(self.prefs().get("voice_gpu")) and has_nvidia() and not self.gpu_failed

    def engine_dir(self) -> Path:
        return voice_dir() / ("engine-gpu" if self.use_gpu() else "engine")

    def check_engine(self) -> bool:
        d = voice_dir()
        _, mfile, mmin, _, _ = self.model()
        ok = (self.engine_dir() / "whisper-server.exe").is_file() and (d / mfile).is_file() \
            and (d / mfile).stat().st_size >= mmin
        if ok and self.status["engine"] in ("missing", "error"):
            self.status.update(engine="ready", error="")
        elif not ok and self.status["engine"] == "ready":
            self.status["engine"] = "missing"
        return ok

    def view(self) -> dict:
        p = self.status.get("pending")
        out = dict(self.status, windows=WINDOWS, size=self._size(), nvidia=has_nvidia(), gpu_failed=self.gpu_failed)
        out["pending"] = ({k: v for k, v in p.items() if k not in ("intent", "event")} if p else None)
        return out

    def _size(self) -> int:
        try:
            return sum(f.stat().st_size for f in voice_dir().rglob("*") if f.is_file())
        except OSError:
            return 0

    def _watch(self) -> None:
        """Once a second: follow the Voice switch (download when needed, start / stop the key check), stop an idle
        engine, and drop an unanswered question."""
        while True:
            try:
                p = self.prefs()
                on = bool(p["voice"]) and WINDOWS
                if on and not self.check_engine() and self.status["engine"] == "missing" and not self._downloading():
                    self.download()
                want = on and self.status["engine"] == "ready"
                if want and (self.key_thread is None or not self.key_thread.is_alive()):
                    self.key_stop.clear()
                    self.key_thread = threading.Thread(target=self._keys, name="voice-keys", daemon=True)
                    self.key_thread.start()
                elif not want and self.key_thread is not None:
                    self.key_stop.set()
                    self.key_thread = None
                    self.stop_engine()
                hot = bool(p.get("hotkeys_on")) and bool(p.get("hotkeys")) and WINDOWS     # hotkeys: on their own
                if hot and (self.hot_thread is None or not self.hot_thread.is_alive()):
                    self.hot_stop.clear()
                    self.hot_thread = threading.Thread(target=self._hotkeys, name="hotkeys", daemon=True)
                    self.hot_thread.start()
                elif not hot and self.hot_thread is not None:
                    self.hot_stop.set()
                    self.hot_thread = None
                if self.proc is not None and not self.busy and time.time() - self.used > IDLE_STOP:
                    log.info("Voice: the speech engine was idle for 5 minutes: stopped")
                    self.stop_engine()
                pend = self.status.get("pending")
                if pend and time.time() > pend["expires"]:
                    self.status["pending"] = None
                    self._show("fail", [self.t("cancel")], 2)
            except Exception:
                log.exception("Voice check failed")
            time.sleep(1)

    # ---------- download / remove ----------

    def _downloading(self) -> bool:
        return self.dl_thread is not None and self.dl_thread.is_alive()

    def download(self) -> None:
        if self._downloading():
            return
        self.dl_cancel.clear()
        self.eng_size = GPU_SIZE if self.use_gpu() else ENGINE_SIZE
        self.status.update(engine="downloading", done=0, total=self.eng_size + self.model()[3], error="")
        self.dl_thread = threading.Thread(target=self._download, name="voice-download", daemon=True)
        self.dl_thread.start()

    def cancel(self) -> None:
        self.dl_cancel.set()

    def _fetch(self, url: str, dest: Path, base: int, expected: int, is_model: bool = False) -> None:
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "FQPNsChatBot-voice"})
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
            size = int(r.headers.get("Content-Length") or 0) or expected
            if is_model:
                self.status["total"] = self.eng_size + size
            got = 0
            while True:
                if self.dl_cancel.is_set():
                    raise InterruptedError
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                self.status["done"] = base + got
        tmp.replace(dest)

    def _download(self) -> None:
        d = voice_dir()
        try:
            gpu = self.use_gpu()
            url, sha, esize, edir = (GPU_URL, GPU_SHA256, GPU_SIZE, d / "engine-gpu") if gpu else (ENGINE_URL, ENGINE_SHA256, ENGINE_SIZE, d / "engine")
            self.eng_size = esize
            edir.mkdir(parents=True, exist_ok=True)
            if not (edir / "whisper-server.exe").is_file():
                zpath = d / ("engine-gpu.zip" if gpu else "engine.zip")
                self._fetch(url, zpath, 0, esize)
                h = hashlib.sha256()
                with open(zpath, "rb") as f:
                    for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                        h.update(block)
                if h.hexdigest() != sha:
                    zpath.unlink(missing_ok=True)
                    raise ValueError("The speech engine download was damaged. Try again.")
                with zipfile.ZipFile(zpath) as z:
                    for info in z.infolist():
                        name = info.filename.rsplit("/", 1)[-1]
                        if gpu:      # the graphics-card build: the engine, its parts and NVIDIA's (64-bit) runtime
                            keep = (name.endswith(".dll") and name != "cudart32_110.dll") or name == "whisper-server.exe"
                        else:
                            keep = name in ENGINE_FILES or (name.startswith("ggml-cpu") and name.endswith(".dll"))
                        if keep:
                            with z.open(info) as src, open(edir / name, "wb") as dst:
                                shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
                zpath.unlink(missing_ok=True)
            if not gpu and (d / "engine-gpu").is_dir():       # the graphics card was switched off: its engine goes (about 700 MB)
                shutil.rmtree(d / "engine-gpu", ignore_errors=True)
            self.status["done"] = esize
            _, mfile, mmin, msize, _ = self.model()
            model = d / mfile
            if not model.is_file() or model.stat().st_size < mmin:
                self._fetch(HF + mfile, model, esize, msize, is_model=True)
                if model.stat().st_size < mmin:
                    model.unlink(missing_ok=True)
                    raise ValueError("The speech model download was cut off. Try again.")
                want = MODEL_SHA256.get(mfile)
                if want:
                    h = hashlib.sha256()
                    with open(model, "rb") as f:
                        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                            h.update(block)
                    if h.hexdigest() != want:
                        model.unlink(missing_ok=True)
                        raise ValueError("The speech model download was damaged. Try again.")
            for other, *_ in MODELS.values():                 # only one model is kept (the other one is deleted)
                if other != mfile:
                    try:
                        (d / other).unlink(missing_ok=True)
                    except OSError:
                        pass
            self.status.update(engine="ready", done=self.status["total"], error="")
            log.info("Voice: speech engine and model downloaded (%d MB)", self._size() // 1_000_000)
        except InterruptedError:
            self.status.update(engine="missing", done=0, error="")
            self._set_pref(voice=False)
            log.info("Voice: download cancelled")
        except Exception as e:
            log.exception("Voice: download failed")
            self.status.update(engine="error", error=str(e)[:200] if isinstance(e, ValueError) else
                               "The download didn't work. Check the internet connection and switch Voice on again.")
            self._set_pref(voice=False)

    def remove(self) -> None:
        self.cancel()
        self._set_pref(voice=False)
        self.key_stop.set()
        self.stop_engine()
        time.sleep(0.3)
        shutil.rmtree(voice_dir(), ignore_errors=True)
        self.status.update(engine="missing", done=0, total=0, error="")

    def _set_pref(self, **kw) -> None:
        try:
            st = self.state.rt().store
            prefs = dict(st.get("prefs"))
            prefs.update(kw)
            st.save("prefs", prefs)
        except Exception:
            log.exception("Voice: could not save the setting")

    # ---------- the speech engine ----------

    def _kill_strays(self) -> None:
        """A speech engine left running by an app that crashed is stopped."""
        try:
            import psutil
            mine = str(voice_dir() / "engine").lower()
            for p in psutil.process_iter(["exe"]):
                if (p.info.get("exe") or "").lower().startswith(mine):
                    p.kill()
        except Exception:
            pass

    @staticmethod
    def _runtime() -> None:
        """Microsoft's C++ runtime, which the speech engine needs: the installed app carries it (vcrt next to the
        program) and puts it next to the engine, so nobody has to install the "Visual C++ Redistributable"."""
        src = Path(sys.executable).parent / "vcrt"
        for dst in (voice_dir() / "engine", voice_dir() / "engine-gpu"):
            if not src.is_dir() or not dst.is_dir():
                continue
            for f in src.glob("*.dll"):
                t = dst / f.name
                try:
                    if not t.is_file() or t.stat().st_size != f.stat().st_size:
                        shutil.copy2(f, t)
                except OSError:
                    log.warning("Voice: could not copy %s next to the speech engine", f.name)

    def ensure_engine(self) -> bool:
        """Starts the speech engine if it isn't running. Returns True when it answers (waits up to 40 seconds)."""
        self._runtime()
        with self.lock:
            key, mfile, _, _, most = self.model()
            gpu = self.use_gpu()
            key = key + (":gpu" if gpu else "")
            if self.proc is not None and getattr(self, "proc_model", None) != key:
                self.lock.release()                            # another model was chosen: start the engine again
                try:
                    self.stop_engine()
                finally:
                    self.lock.acquire()
            if self.proc is not None and self.proc.poll() is None and self.status["server"] == "on":
                return True
            if self.proc is None or self.proc.poll() is not None:
                import socket
                with socket.socket() as s:
                    s.bind(("127.0.0.1", 0))
                    self.port = s.getsockname()[1]
                d = voice_dir()
                threads = max(2, min(most, (os.cpu_count() or 4) // 2))
                self.proc_model = key
                edir = self.engine_dir()
                cmd = [str(edir / "whisper-server.exe"), "-m", str(d / mfile), "--host", "127.0.0.1",
                       "--port", str(self.port), "-t", str(threads), "-l", "auto"]
                self._launch(cmd, edir)
            for _ in range(160):
                if self.proc.poll() is not None and gpu:
                    log.warning("Voice: the graphics-card engine stopped (code %s): %s", self.proc.returncode, self._tail())
                    self.gpu_failed = True                    # back to the processor engine (downloaded if it isn't there)
                    self.status["server"] = "off"
                    self.status["error"] = "The graphics card engine didn't start, so voice uses the processor again."
                    return False
                if self.proc.poll() is not None:
                    self.status["server"] = "off"
                    self.status["error"] = self._why(self.proc.returncode)
                    log.warning("Voice: the speech engine stopped (code %s): %s", self.proc.returncode, self._tail())
                    return False
                try:
                    with LOCAL.open(f"http://127.0.0.1:{self.port}/", timeout=1):
                        self.status["server"] = "on"
                        return True
                except Exception:
                    time.sleep(0.25)
            return False

    def _launch(self, cmd, edir) -> None:
        flags = 0x08000000 | 0x00004000 if WINDOWS else 0          # no window, below-normal priority (the game first)
        try:
            if getattr(self, "logf", None):
                self.logf.close()
        except OSError:
            pass
        self.logf = open(voice_dir() / "engine.log", "wb")    # what the engine says (to find out why it stopped)
        self.proc = subprocess.Popen(cmd, cwd=str(edir), stdout=self.logf, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, creationflags=flags)
        self.status["server"] = "loading"
        log.info("Voice: speech engine started")

    def _tail(self) -> str:
        try:
            lines = (voice_dir() / "engine.log").read_text("utf-8", "replace").strip().splitlines()
            return " | ".join(x.strip() for x in lines[-4:] if x.strip())[-400:]
        except OSError:
            return ""

    def _why(self, code) -> str:
        """Why the speech engine stopped, in words (the exact reason is also in voice\\engine.log)."""
        code = (code or 0) & 0xFFFFFFFF
        if code in (0xC0000135, 0xC0000139, 0xC000007B):        # a Windows part it needs is missing
            return ("The speech engine needs Microsoft's free “Visual C++ Redistributable (x64)”: "
                    "https://aka.ms/vs/17/release/vc_redist.x64.exe — install it, then press Test again.")
        if code == 0xC000001D:                                    # this processor lacks an instruction it uses
            return "The speech engine doesn't run on this processor."
        tail = self._tail()
        if "failed to load model" in tail.lower() or "invalid model" in tail.lower():
            return "The speech model file is damaged. Press “Remove the model”, then switch Voice on again."
        return "The speech engine stopped (code %X)%s" % (code, (": " + tail[-160:]) if tail else ".")

    def stop_engine(self) -> None:
        with self.lock:
            p, self.proc = self.proc, None
            self.status["server"] = "off"
        if p is not None and p.poll() is None:
            try:
                p.terminate()
                p.wait(5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        f, self.logf = getattr(self, "logf", None), None
        if f is not None:
            try:
                f.close()
            except Exception:
                pass

    def transcribe(self, wav: bytes, prompt: str = "", lang: str = "") -> str:
        lang = lang or {"ar": "ar", "en": "en"}.get(self.prefs()["voice_lang"], "auto")
        boundary = uuid.uuid4().hex
        secs = max(0.0, (len(wav) - 44) / (RATE * 2))
        ctx = min(1500, max(512, int((secs + 1.5) * 50)))        # 50 per second of audio (1500 = 30 s); at least ~10 s
        beam = GPU_BEAM if self.use_gpu() else BEAMS.get(self.model()[0], 3)
        fields = {"response_format": "json", "temperature": "0", "language": lang, "prompt": prompt[:600],
                  "beam_size": str(beam), "audio_ctx": str(ctx), "no_timestamps": "true"}
        body = io.BytesIO()
        for k, v in fields.items():
            body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="say.wav"\r\n'
                   f"Content-Type: audio/wav\r\n\r\n".encode() + wav + b"\r\n" + f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/inference", data=body.getvalue(),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with LOCAL.open(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8", "replace") or "{}")
        except urllib.error.URLError as e:
            if not isinstance(getattr(e, "reason", None), ConnectionRefusedError) and "10061" not in str(e):
                raise
            log.warning("Voice: the speech engine wasn't there: starting it again")   # stopped a moment before: once more
            self.used = time.time()
            self.stop_engine()
            if not self.ensure_engine():
                raise RuntimeError(self.status.get("error") or "The speech engine didn't start.")
            with LOCAL.open(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8", "replace") or "{}")
        text = str(data.get("text") or "").strip()
        return "" if text.startswith("[") and text.endswith("]") else text      # [BLANK_AUDIO], [Music]

    # ---------- microphone ----------

    @staticmethod
    def mics() -> list:
        try:
            import sounddevice as sd
            host = sd.default.hostapi if isinstance(sd.default.hostapi, int) else 0
            return sorted({d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0 and d["hostapi"] == host})
        except Exception:
            log.exception("Voice: could not list the microphones")
            return []

    def _device(self):
        name = self.prefs()["voice_mic"]
        if not name:
            return None
        try:
            import sounddevice as sd
            for i, d in enumerate(sd.query_devices()):
                if d["name"] == name and d["max_input_channels"] > 0:
                    return i
        except Exception:
            pass
        return None             # (unplugged: the Windows default instead)

    def record(self, until) -> bytes:
        """Records until `until()` is False (or MAX_RECORD). Returns a 16 kHz mono WAV."""
        import sounddevice as sd
        chunks = []
        with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", device=self._device(),
                               callback=lambda data, frames, t, s: chunks.append(bytes(data))):
            start = time.time()
            while until() and time.time() - start < MAX_RECORD:
                time.sleep(0.02)
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(chunks))
        return out.getvalue()

    def test(self, seconds: float = 3.0) -> dict:
        """Settings > Voice > Test: records a few seconds and shows what was heard (and the action it would be)."""
        if self.status["engine"] != "ready":
            return {"error": "Switch Voice commands on first."}
        if self.busy:
            return {"error": "Voice is busy right now. Try again in a second."}
        self.busy = True                   # in use: the 5-minute idle check leaves the engine alone (it used to stop it mid-test)
        self.used = time.time()
        try:
            starting = threading.Thread(target=self.ensure_engine, daemon=True)     # loads while you talk
            starting.start()
            end = time.time() + seconds
            try:
                wav = self.record(lambda: time.time() < end)
            except Exception as e:
                log.exception("Voice test: microphone")
                return {"error": f"The microphone couldn't be opened ({str(e)[:120]})."}
            starting.join(45)
            if not self.ensure_engine():
                return {"error": self.status.get("error") or "The speech engine didn't start."}
            self.used = time.time()
            text = self.transcribe(wav, self._prompt())
            return {"heard": text, "intent": VP.parse(text)}
        except Exception as e:
            log.exception("Voice test failed")
            return {"error": f"The test didn't work ({str(e)[:120]}). Try again."}
        finally:
            self.busy = False
            self.used = time.time()

    # ---------- push to talk ----------

    def _keys(self) -> None:
        import ctypes
        get = ctypes.windll.user32.GetAsyncKeyState
        down, vk, read_at = False, 0x78, 0.0
        while not self.key_stop.is_set():
            if time.monotonic() - read_at > 1:          # 1.18.0: the settings once a second, not 33 times (lighter on the PC)
                vk, read_at = VK.get(self.prefs()["voice_key"], 0x78), time.monotonic()
            pressed = bool(get(vk) & 0x8000)
            if pressed and not down and not self.busy:
                down = True
                threading.Thread(target=self._talk, args=(lambda: bool(get(vk) & 0x8000),), daemon=True).start()
            elif not pressed:
                down = False
            time.sleep(0.03)

    # ---------- hotkeys ----------

    def _hotkeys(self) -> None:
        import ctypes
        get = ctypes.windll.user32.GetAsyncKeyState
        held, combos, read_at = set(), [], 0.0
        while not self.hot_stop.is_set():
            if time.monotonic() - read_at > 1:          # 1.18.0: the settings once a second, not 40 times (lighter on the PC)
                read_at = time.monotonic()
                combos = []
                for i, hk in enumerate(self.prefs().get("hotkeys") or []):
                    c = hot_combo(hk.get("key")) if isinstance(hk, dict) else None
                    if c:
                        combos.append((i, hk, c))
            for i, hk, c in combos:
                mods, keys = c
                down = all(bool(get(VK[k]) & 0x8000) for k in keys) and all(
                    bool(get(MOD_VK[m]) & 0x8000) == (m in mods) for m in MOD_VK
                    if not any(k.startswith({"Ctrl": "Control"}.get(m, m)) for k in keys))
                tag = (i, hk.get("key"))
                if down and tag not in held:
                    held.add(tag)
                    threading.Thread(target=self._hot_run, args=(dict(hk),), daemon=True).start()
                elif not down:
                    held.discard(tag)
            time.sleep(0.025)

    def hot_name(self, combo: str) -> str:
        out = []
        for k in str(combo).split("+"):
            for a, b in (("Key", ""), ("Digit", ""), ("Numpad", "Num "), ("Mouse", "Mouse ")):
                if k.startswith(a) and len(k) > len(a):
                    k = b + k[len(a):]
                    break
            out.append(k)
        return "+".join(out)

    def _hot_run(self, hk: dict) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self._hot_do(hk), self.loop).result(30)
        except Exception:
            log.exception("Hotkey failed")

    async def _hot_do(self, hk: dict) -> None:
        a, arg = hk.get("act"), str(hk.get("arg") or "").strip()
        label = "⌨ " + self.hot_name(hk.get("key"))
        ar = self.lang() == "ar"
        if a in ("add", "sub"):
            from . import counters as C
            st = self.state.rt().store
            if not any(C.norm(c["name"]) == C.norm(arg) for c in C.view(st)):      # deleted or renamed since: say so (don't make a new one)
                self._finish(False, label, (f"No counter called {arg}", f"ما فيه عداد اسمه {arg}")[ar])
                return
            try:
                C.act(st, "add", {"name": arg, "by": 1 if a == "add" else -1})
            except C.CounterError as e:
                self._finish(False, label, str(e)[:80])
                return
            except Exception:
                log.exception("Hotkey counter")
                self._finish(False, label, self.t("fail"))
                return
            n = next((c["value"] for c in C.view(st) if C.norm(c["name"]) == C.norm(arg)), None)
            if n is None:
                self._finish(False, label, (f"No counter called {arg}", f"ما فيه عداد اسمه {arg}")[ar])
            else:
                self._finish(True, label, f"{arg}: {n}")
        elif a == "say" and arg:
            await self._do({"act": "say", "text": arg[:450]}, label, None)
        elif a == "game":
            from . import minigames
            g = arg if arg in minigames.GAME_KEYS else "random"
            await self._do({"act": "game", "game": g}, label, None)

    def _show(self, kind: str, lines, seconds=None) -> None:
        p = self.prefs()
        if p["voice_overlay"]:
            try:
                OVERLAY.show(kind, lines, p["voice_corner"], seconds, p.get("voice_style") or "orb")
            except Exception:
                log.exception("Voice overlay")

    def _beep(self, kind: str, hot: bool = False) -> None:
        """1.17.0: soft sounds made in core/sounds.py (it was a loud Windows beep). Hotkeys have their own switch."""
        p = self.prefs()
        if not (p.get("hotkeys_sound", True) if hot else p["voice_beep"]) or not WINDOWS:
            return
        from . import sounds
        threading.Thread(target=sounds.play, args=(kind,), daemon=True).start()

    def _talk(self, held) -> None:
        self.busy = True
        try:
            self.used = time.time()
            self._show("listen", [self.t("listen")])
            starting = threading.Thread(target=self.ensure_engine, daemon=True)     # loads while you talk
            starting.start()
            try:
                wav = self.record(held)
            except Exception as e:
                log.exception("Voice: microphone")
                self._finish(False, "", f"Microphone: {str(e)[:80]}")
                return
            if len(wav) < RATE * 2 * 0.3:                 # under 0.3 s: a tap, not speech
                OVERLAY.hide()
                return
            self._show("think", [self.t("think")])
            self._beep("heard")
            starting.join(45)
            if self.status["server"] != "on" and self.gpu_failed and self.check_engine():
                self.ensure_engine()                      # the graphics card didn't work: the processor engine, right away
            if self.status["server"] != "on":
                self._finish(False, "", self.status.get("error") or self.t("fail"))
                return
            prompt = self._prompt()
            t0 = time.time()
            text = self.transcribe(wav, prompt)
            took = time.time() - t0
            # 1.17.0: Arabic + English: when what it heard isn't a command, it listens to the same recording once more in
            # the other language (a mixed sentence is sometimes read in the wrong one) and keeps the reading that is
            if self.prefs()["voice_lang"] == "both" and text and took < 3 and not self.status.get("pending") and VP.parse(text) is None:
                other = "en" if any("\u0600" <= ch <= "\u06ff" for ch in text) else "ar"
                try:
                    again = self.transcribe(wav, prompt, other)
                    if again and VP.parse(again) is not None:
                        log.info("Voice: understood on the second listen (%s)", other)
                        text = again
                except Exception:
                    log.exception("Voice: second listen")
            self.used = time.time()
            self.status["heard_at"] = time.time()
            self.status["took"] = round(time.time() - t0, 1)              # how long it took to understand (shown in the app)
            log.info("Voice: understood in %.1f s (%s%s)", time.time() - t0, self.model()[0], ", graphics card" if self.use_gpu() else "")
            self._handle(text)
        except Exception:
            log.exception("Voice command failed")
            self._finish(False, "", self.t("fail"))
        finally:
            self.busy = False
            self.used = time.time()

    def _prompt(self) -> str:
        """Words the speech engine should expect (names in chat, your commands and counters): fewer mishearings."""
        try:
            rt = self.state.rt()
            bot = rt.state.get("bot")
            people = list(getattr(bot, "_chatters", {}).keys())[-25:] if bot else []
            cmds = [n.lstrip("!") for n in (rt.store.get("commands") or {})][:30]
            own = self._game_names(rt)
            fixes = self._fixes()
            VP.FIXES = fixes                                    # 1.18.0: your spelling fixes and the learned ones
            right = list(dict.fromkeys(str(f["to"]) for f in fixes))[:25]
            return ("تايم اوت، بان، فك البان، في آي بي، شيل الفي آي بي، مشرف، شيل الإشراف، صفّر، ابدأ، غيّر العنوان، غيّر اللعبة، "
                    "حروف، رتب، ايموجي، عكس، احسب، سلم، سؤال، لغز، ترجم، ضد، الدخيل، دقايق، ساعة، "
                    "timeout, ban, unban, VIP, unVIP, mod, unmod, reset, start, trivia, riddle, emoji, "
                    + ", ".join(dict.fromkeys(right + own + people + cmds)))
        except Exception:
            return "timeout, ban, reset, add command"

    # ---------- what was said -> what happens ----------

    def _remember(self, entry: dict) -> None:
        """1.18.0: the Voice page's history (the last 20, newest first; only while the app is open)."""
        hist = self.status.get("history") or []
        self.status["history"] = ([dict(entry)] + hist)[:HISTORY]

    def _finish(self, ok: bool, heard: str, result: str, beep: bool = True) -> None:
        self.status["last"] = {"heard": heard, "result": result, "ok": ok, "at": time.time()}
        self._remember(self.status["last"])
        self._show("ok" if ok else "fail", [result], 2.5 if ok else 3.5)
        if beep:
            self._beep("ok" if ok else "fail", hot=str(heard).startswith("⌨ "))
        try:
            self.state.rt().store.activity.add("manage", f"Voice: {heard} → {result}" if heard else f"Voice: {result}", "voice")
        except Exception:
            pass

    def _game_names(self, rt=None) -> list:
        """The streamer's own game commands (Mini games > a game's settings), so «ابدا خمن» works when «خمن» starts
        Emoji: handed to the voice parser, and to the speech engine as words to expect."""
        try:
            rt = rt or self.state.rt()
            games = rt.store.get("games") or {}
            own = {}
            for key in VP.GAME_WORDS:
                v = (games.get(key) or {}).get("start_cmd") or []
                for n in (v if isinstance(v, list) else [v]):
                    n = str(n).strip().strip("!؟?").strip()
                    if n:
                        own[n] = key
            VP.EXTRA_GAMES = own
            return [n for n in own if n not in VP.GAME_WORDS.get(own[n], [])][:15]
        except Exception:
            return []

    def _handle(self, text: str) -> None:
        VP.FIXES = self._fixes()
        intent = VP.parse(text)
        pend = self.status.get("pending")
        if pend and intent and intent["act"] == "undo":
            intent = {"act": "no"}
        if pend and intent and intent["act"] in ("yes", "no", "pick"):
            self.answer(pend["id"], intent)
            return
        if intent and intent["act"] == "undo":                 # «كنسل» / "cancel": take back the last voice command
            asyncio.run_coroutine_threadsafe(self._undo(text), self.loop).result(30)
            return
        if not intent or intent["act"] in ("yes", "no", "pick"):
            self.status["last"] = {"heard": text, "result": self.t("nothing"), "ok": False, "at": time.time()}
            self._remember(self.status["last"])
            self._show("fail", [self.t("nothing")] + ([f"“{text[:40]}”"] if text else []), 3)
            return
        act = ACTION_OF.get(intent["act"])
        p = self.prefs()
        if act not in p["voice_acts"]:
            self._finish(False, text, self.t("off", a=self._label(act)))
            return
        fut = asyncio.run_coroutine_threadsafe(self._prepare(intent, text), self.loop)
        fut.result(30)

    UNDO_FOR = 300            # «كنسل» works on what voice did in the last 5 minutes

    async def _undo(self, heard: str) -> None:
        """Takes back the last thing voice did: a timeout or ban is lifted, a reset counter gets its number back, a game
        that was started stops, the title or game goes back to what it was."""
        last, ar = getattr(self, "last_done", None), self.lang() == "ar"
        self.last_done = None
        if not last or time.time() - last["at"] > self.UNDO_FOR:
            self._finish(False, heard, ("Nothing to cancel", "ما فيه شي أكنسله")[ar])
            return
        rt = self.state.rt()
        bot, st, a = rt.state.get("bot"), rt.store, last["act"]
        try:
            if a == "say":
                raise RuntimeError(("A sent message can't be taken back", "الرسالة انرسلت وما تنسحب")[ar])
            if a == "clear":
                raise RuntimeError(("A cleared chat can't come back", "الشات الممسوح ما يرجع")[ar])
            if a == "chatbox":                                     # 1.18.0: the Chat box back as it was
                self._chatbox(st, last["was"], heard, undo=True)
                return
            if a in ("ignore", "unignore"):                        # 1.18.0
                self._ignore(st, last["login"], a == "unignore")
                self._finish(True, heard, (f"{last['name']}: cancelled", f"{last['name']}: انلغى")[ar])
                return
            if a in ROLE_ACTS:                                     # 1.18.0: the opposite (VIP ↔ no VIP, mod ↔ no mod)
                back = {"vip": "unvip", "unvip": "vip", "mod": "unmod", "unmod": "mod"}[a]
                ok, why = (await bot._set_role(back, last["uid"])) if bot is not None else (False, "bot")
                if not ok:
                    raise RuntimeError(self._role_problem(back, why, last["name"]))
                self._finish(True, heard, (f"{last['name']}: cancelled", f"{last['name']}: انلغى")[ar])
                return
            if a in ("timeout", "ban"):
                if bot is None or not await bot._mod_api("DELETE", "moderation/bans", {"user_id": last["uid"]}):
                    raise RuntimeError(("Twitch refused it", "تويتش رفض")[ar])
                self._finish(True, heard, (f"{last['name']}: {'timeout' if a == 'timeout' else 'ban'} cancelled",
                                           f"{last['name']}: انلغى {'التايم اوت' if a == 'timeout' else 'البان'}")[ar])
            elif a == "reset":
                from . import counters as C
                ctr = dict(st.get("counters") or {})
                ctr.update(last["before"])
                st.save("counters", ctr)
                for n in last["names"]:
                    if n != "#":
                        C.note(st, n, "set", "you (voice)")
                shown = ", ".join(f"{k.split(':', 1)[1]}: {v}" for k, v in last["before"].items())
                self._finish(True, heard, (f"Back: {shown}", f"رجع: {shown}")[ar])
            elif a == "game":
                r = last.get("round")
                if bot is None or r is None or bot.round is not r or r.over:
                    raise RuntimeError(("That round already ended", "الجولة خلصت أصلاً")[ar])
                r.done = True
                await bot._send("⛔ انلغت الجولة", why="game", user="")
                self._finish(True, heard, ("Round cancelled", "انلغت الجولة")[ar])
            elif a in ("title", "setgame"):
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                await (bot._set_title if a == "title" else bot._set_game)(last["before"], None)
                self._finish(True, heard, (f"Back to: {last['before'][:40]}", f"رجع: {last['before'][:40]}")[ar])
        except Exception as e:
            if not isinstance(e, RuntimeError):
                log.exception("Voice cancel failed")
            self._finish(False, heard, str(e)[:80] if isinstance(e, RuntimeError) else self.t("fail"))

    @staticmethod
    def _ignore(st, login: str, on: bool) -> None:
        """1.18.0: on the Blocklist for good (on), or off it (also a timed block)."""
        bl = dict(st.get("blocklist") or {})
        users = [u for u in (bl.get("users") or []) if str(u).lower() != login.lower()]
        timed = [x for x in (bl.get("timed") or []) if not (isinstance(x, dict) and str(x.get("user", "")).lower() == login.lower())]
        if on:
            users.append(login)
        bl.update(users=users, timed=timed)
        st.save("blocklist", bl)

    def _chatbox(self, st, hide: bool, heard: str, undo: bool = False) -> None:
        """1.18.0: «خبّي الشات» / «ورّ الشات»: the Chat box overlay hidden on stream, or shown again."""
        ar = self.lang() == "ar"
        cfg = dict(st.get("chatbox") or {})
        was = bool(cfg.get("hidden"))
        cfg["hidden"] = bool(hide)
        st.save("chatbox", cfg)
        if undo:
            self.last_done = None
            self._finish(True, heard, ("Chat box: cancelled", "صندوق الشات: انلغى")[ar])
            return
        self.last_done = {"act": "chatbox", "was": was, "at": time.time()}
        msg = (("Chat box hidden on stream", "انخفى صندوق الشات عن البث") if hide else ("Chat box shows on stream", "صندوق الشات رجع على البث"))[ar]
        if not cfg.get("on"):
            msg += (" (it's off: switch it on on the Overlays page)", " (هو طافي: شغّله من صفحة الأوفرلاي)")[ar]
        self._finish(True, heard, msg)

    def _role_problem(self, act: str, why: str, name: str) -> str:
        """1.18.0: Twitch's answer to a VIP / mod change, in words."""
        ar = self.lang() == "ar"
        return {
            "scopes": ("Log out and in again (Settings) so Twitch lets the app change VIPs and mods",
                       "سجّل خروج ودخول من جديد (الإعدادات) عشان تويتش يسمح للتطبيق يغيّر الفي آي بي والمشرفين"),
            "already": (f"{name} already is", f"{name} أصلاً كذا") if act in ("vip", "mod") else (f"{name} isn't one", f"{name} مو كذا أصلاً"),
            "is_mod": (f"{name} is a moderator: remove mod first", f"{name} مشرف: شيل الإشراف أول"),
            "is_vip": (f"{name} is a VIP: remove VIP first", f"{name} في آي بي: شيل الفي آي بي أول"),
            "full": ("No VIP spots left on your channel", "ما بقى أماكن في آي بي في قناتك"),
            "banned": (f"{name} is banned", f"{name} عليه بان"),
            "rate": ("Too many changes: try again in a bit", "تغييرات كثير: جرّب بعد شوي"),
        }.get(why, ("Twitch refused it", "تويتش رفض"))[ar]

    # ---------- 1.18.0: spelling fixes (yours, and the ones the app learns by itself) ----------

    def _fixes(self) -> list:
        try:
            items = (self.state.rt().store.get("voice_fixes") or {}).get("items") or []
            return [f for f in items if isinstance(f, dict) and f.get("heard") and f.get("to")]
        except Exception:
            return []

    def _learned(self, said: str) -> str:
        """A name you confirmed before for these same words (learned by itself), or ""."""
        key = VP.norm(said)
        for f in self._fixes():
            if f.get("kind") == "name" and VP.norm(f["heard"]) == key:
                return str(f["to"]).lower()
        return ""

    def _learn(self, heard: str, intent: dict, who) -> None:
        """You said yes (or picked 1 / 2 / 3) to a name the app had to guess: next time those words mean that person
        straight away. Nothing is learned when it was already spelled right."""
        try:
            said = str((intent or {}).get("who") or "").strip()
            login = str((who or {}).get("login") or "").lower()
            if not said or not login or VP.norm(said).replace(" ", "") in (login, login.replace("_", "")):
                return
            st = self.state.rt().store
            data = dict(st.get("voice_fixes") or {})
            items = [f for f in (data.get("items") or []) if isinstance(f, dict)]
            key = VP.norm(said)
            for f in items:
                if VP.norm(f.get("heard")) == key:
                    if f.get("auto") is False:
                        return                         # yours: never changed by itself
                    f.update(to=login, kind="name", n=int(f.get("n") or 0) + 1, at=int(time.time()))
                    break
            else:
                items.insert(0, {"heard": said, "to": login, "kind": "name", "auto": True, "n": 1, "at": int(time.time())})
            data["items"] = items[:FIXES_MAX]
            st.save("voice_fixes", data)
            VP.FIXES = data["items"]
        except Exception:
            log.exception("Voice: learning a name failed")

    def _label(self, act: str) -> str:
        ar = self.lang() == "ar"
        return {"timeout": ("Timeout", "التايم اوت"), "ban": ("Ban", "البان"), "reset": ("Reset", "التصفير"),
                "roles": ("VIP / mod", "الفي آي بي / الإشراف"), "cmds": ("Run a command", "تشغيل أمر"),
                "ignore": ("Ignore", "التجاهل"), "clear": ("Clear chat", "مسح الشات"), "chatbox": ("Chat box", "صندوق الشات"),
                "game": ("Mini games", "الألعاب"), "title": ("Title / game", "العنوان / اللعبة"),
                "say": ("Say in chat", "قول")}.get(act, (act, act))[ar]

    async def _prepare(self, intent: dict, heard: str) -> None:
        """Works out the details (who, which command), then asks or does it."""
        rt = self.state.rt()
        bot, st = rt.state.get("bot"), rt.store
        act, ar = intent["act"], self.lang() == "ar"
        key = self.prefs()["voice_key"].replace("Key", "").replace("Digit", "")
        if act in ("hidechat", "showchat"):   # 1.18.0: the Chat box overlay, hidden or shown on stream
            self._chatbox(st, act == "hidechat", heard)
            return
        if act == "clear":                    # 1.18.0: always asked first (nothing brings a cleared chat back)
            self._ask(intent, heard, self.t("clear"), [], key)
            return
        if act == "runcmd":                   # 1.18.0: the command's reply, as if you typed it
            from . import manage
            customs = {n: str(c.get("response") or "") for n, c in (st.get("commands") or {}).items() if c.get("enabled", True)}
            off = set((st.get("settings") or {}).get("disabled_builtins") or [])
            got = VP.match_command(intent["name"], customs, [k for k in VP.BUILTIN_SPOKEN if k not in off])
            if not got:
                self._finish(False, heard, (f"No command “{intent['name']}”", f"ما فيه أمر «{intent['name']}»")[ar])
                return
            if got[0] == "builtin":           # 1.18.0: «كوماندات» → !cmlist, «برنامج» → «برنامج؟»
                hit = ("برنامج؟" if ar else "app?") if got[1] == "app" else manage.BUILTIN_PREFIX + manage.BUILTIN_NAMES[got[1]]
            else:
                hit = got[1]
            intent = dict(intent, target=hit, builtin=got[0] == "builtin")
            if self.prefs()["voice_ask_all"]:
                self._ask(intent, heard, (f"Run {hit}", f"تشغيل {hit}")[ar], [], key)
                return
            await self._do(intent, heard, None)
            return
        if act == "count":                    # 1.18.0: + / − / set a counter
            from . import counters as C
            names = [c["name"] for c in C.view(st)]
            hit = VP.match_name(intent["what"], names)
            if not hit:
                self._finish(False, heard, (f"No counter “{intent['what']}”", f"ما فيه عداد «{intent['what']}»")[ar])
                return
            intent = dict(intent, target=hit)
            if self.prefs()["voice_ask_all"]:
                self._ask(intent, heard, self._describe(intent), [], key)
                return
            await self._do(intent, heard, None)
            return
        if act in ("timeout", "ban", "unban", "ignore", "unignore") + ROLE_ACTS:
            now = time.time()
            people = sorted(((login, v[1], now - v[0]) for login, v in (getattr(bot, "_chatters", {}) or {}).items()),
                            key=lambda x: x[2]) if bot else []
            found = VP.match_people(intent["who"], people)
            if act == "unignore":                         # 1.18.0: the people the bot ignores now come first
                bl = st.get("blocklist") or {}
                ign = [(u, u, 0) for u in (bl.get("users") or [])] + [(x["user"], x["user"], 0) for x in (bl.get("timed") or []) if isinstance(x, dict)]
                found = VP.match_people(intent["who"], [(str(a).lower(), b, c) for a, b, c in ign]) or found
            if not found and act in ROLE_ACTS + ("ignore", "unignore"):           # 1.18.0: also everyone who ever chatted (a VIP may not be here now)
                seen = ((st.get("chat_stats") or {}).get("seen") or {})
                old = [(login, (v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else login) or login, 1e9)
                       for login, v in list(seen.items())[-3000:]]
                found = VP.match_people(intent["who"], old)
            if not found and act in ("unban", "ignore", "unignore") + ROLE_ACTS:
                login = VP.latin(intent["who"]).replace(" ", "")
                found = [(login, login, 1.0)] if login else []
            if not found:
                self._finish(False, heard, self.t("nobody", w=intent["who"]))
                return
            title = self.t("timeout", m=mins_text(intent["secs"], ar)) if act == "timeout" else self.t(act)
            hit = self._learned(intent["who"])                 # 1.18.0: a name learned before goes first
            if hit:
                found = [f for f in found if f[0] == hit] or [(hit, hit, 1.0)]
            self._ask(intent, heard, title, [{"login": f[0], "name": f[1]} for f in found], key)
            return
        if act == "say":                    # your own words go to chat: always asked first (yes / 1 / 2 / 3 sends, no cancels)
            self._ask(intent, heard, ("Send in chat", "أرسله في الشات")[ar], [{"login": "", "name": intent["text"][:80]}], key)
            return
        if act == "reset":
            from . import counters as C
            names = [c["name"] for c in C.view(st)]
            cmds = {n: c for n, c in (st.get("commands") or {}).items() if "$(count" in str(c.get("response")) or "$(getcount" in str(c.get("response"))}
            hit = VP.match_name(intent["what"], names + list(cmds))
            if not hit:
                self._finish(False, heard, (f"No counter “{intent['what']}”" if not ar else f"ما فيه عداد «{intent['what']}»"))
                return
            intent = dict(intent, target=hit, is_cmd=hit in cmds)
        if self.prefs()["voice_ask_all"]:
            self._ask(intent, heard, self._describe(intent), [], key)
            return
        await self._do(intent, heard, None)

    def _describe(self, intent: dict) -> str:
        ar = self.lang() == "ar"
        a = intent["act"]
        if a == "reset":
            return (f"Reset {intent['target']}" if not ar else f"تصفير {intent['target']}")
        if a == "count":
            n = intent.get("n")
            sign = {"add": "+", "sub": "−", "set": "= "}[intent["op"]]
            return f"{intent['target']} {sign}{n if n is not None else 1}"
        if a == "game":
            return (f"Start {intent['game']}" if not ar else f"بدء {intent['game']}")
        return {"title": (f"Title: {intent.get('text', '')}", f"العنوان: {intent.get('text', '')}"),
                "setgame": (f"Game: {intent.get('text', '')}", f"اللعبة: {intent.get('text', '')}")}.get(a, (a, a))[ar]

    def _ask(self, intent, heard, title, people, key) -> None:
        pend = {"id": uuid.uuid4().hex[:8], "act": intent["act"], "title": title, "heard": heard, "people": people,
                "expires": time.time() + ASK_SECONDS, "intent": intent}
        self.status["pending"] = pend
        lines = [self.t("ask_who" if len(people) > 1 else "ask", a=title)]
        if len(people) > 1:
            lines += [f"{i + 1}. {p['name']}" for i, p in enumerate(people[:3])]
            lines[-1] += "    " + self.t("say_pick", k=key)
        elif people:
            lines += [people[0]["name"], self.t("say", k=key)]
        else:
            lines += [self.t("say", k=key)]
        self._show("ask", lines, ASK_SECONDS)
        self._beep("heard")

    def answer(self, pid: str, how: dict) -> dict:
        """yes / no / pick n, by voice or from the app's buttons."""
        pend = self.status.get("pending")
        if not pend or pend["id"] != pid:
            return {"error": "That question isn't open anymore."}
        if how.get("act") == "no":
            self.status["pending"] = None
            self._finish(False, pend["heard"], self.t("cancel"))
            return {"ok": True}
        who = None
        if pend["people"] and pend["act"] != "say":
            n = int(how.get("n") or 1) if how.get("act") == "pick" else (1 if len(pend["people"]) == 1 else 0)
            if how.get("login"):
                who = next((p for p in pend["people"] if p["login"] == how["login"]), None)
            elif 1 <= n <= len(pend["people"]):
                who = pend["people"][n - 1]
            if who is None:            # "yes" with several names: still waiting for 1 / 2 / 3
                self._show("ask", [self.t("ask_who", a=pend["title"])] + [f"{i + 1}. {p['name']}" for i, p in enumerate(pend["people"][:3])],
                           max(3, pend["expires"] - time.time()))
                return {"ok": False}
        self.status["pending"] = None
        fut = asyncio.run_coroutine_threadsafe(self._do(pend["intent"], pend["heard"], who), self.loop)
        if not self._in_loop():          # (from the app's buttons this already runs in that loop: never wait on it there)
            fut.result(30)
        return {"ok": True}

    def _in_loop(self) -> bool:
        try:
            return asyncio.get_running_loop() is self.loop
        except RuntimeError:
            return False

    async def _do(self, intent: dict, heard: str, who) -> None:
        rt = self.state.rt()
        bot, st = rt.state.get("bot"), rt.store
        a, ar = intent["act"], self.lang() == "ar"
        try:
            if a in ("timeout", "ban", "unban"):
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                uid = ((getattr(bot, "_chat_info", {}) or {}).get(who["login"]) or (None, None, ""))[2]
                if not uid:
                    users = await bot.fetch_users(logins=[who["login"]])
                    uid = str(users[0].id) if users else ""
                if not uid:
                    raise RuntimeError(f"{who['name']} wasn't found on Twitch")
                if a == "unban":
                    ok = await bot._mod_api("DELETE", "moderation/bans", {"user_id": uid})
                else:
                    data = {"user_id": uid, "reason": "Voice command"}
                    if a == "timeout":
                        data["duration"] = int(intent["secs"])
                    ok = await bot._mod_api("POST", "moderation/bans", {}, {"data": data})
                if not ok:
                    raise RuntimeError("Twitch refused it (is the bot a moderator?)")
                if a in ("timeout", "ban"):
                    self.last_done = {"act": a, "uid": uid, "name": who["name"], "at": time.time()}
                self._learn(heard, intent, who)
                if a == "timeout":
                    done = f"{who['name']}: " + (f"تايم اوت {mins_text(intent['secs'], True)}" if ar else f"timeout {mins_text(intent['secs'], False)}")
                else:
                    done = f"{who['name']}: " + {"ban": ("banned", "بان"), "unban": ("unbanned", "انفك البان")}[a][ar]
                self._finish(True, heard, done)
            elif a == "count":                                  # 1.18.0: + / − / set a counter
                from . import counters as C
                name = intent["target"]
                cur = int((st.get("counters") or {}).get("name:" + name, 0) or 0)
                n = intent.get("n")
                if intent["op"] == "set":
                    new = int(n or 0)
                else:
                    step = int(n) if n is not None else 1
                    new = cur + step if intent["op"] == "add" else cur - step
                new = max(0, min(C.MAX_VALUE, new))
                if intent["op"] == "sub" and cur == 0:
                    raise RuntimeError((f"{name} is already 0", f"{name} أصلاً صفر")[ar])
                C.act(st, "set", {"name": name, "value": new})
                C.note(st, name, "set", "you (voice)")
                self.last_done = {"act": "reset", "before": {"name:" + name: cur}, "names": [name], "at": time.time()}
                self._finish(True, heard, f"{name}: {new}")
            elif a == "runcmd":                                 # 1.18.0: as if you typed it (its reply is the bot's)
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                key = intent["target"]
                await bot.say_as_you(key if intent.get("builtin") or bot.is_command(key) else "!" + key.lstrip("!"))
                self.last_done = {"act": "say", "at": time.time()}
                self._finish(True, heard, (f"Ran {intent['target']}", f"اشتغل {intent['target']}")[ar])
            elif a in ("ignore", "unignore"):                   # 1.18.0: the Blocklist (the bot doesn't answer them)
                self._ignore(st, who["login"], a == "ignore")
                self.last_done = {"act": a, "login": who["login"], "name": who["name"], "at": time.time()}
                self._learn(heard, intent, who)
                self._finish(True, heard, (f"{who['name']}: ignored by the bot" if a == "ignore" else f"{who['name']}: not ignored anymore",
                                           f"{who['name']}: البوت يتجاهله" if a == "ignore" else f"{who['name']}: انفك التجاهل")[ar])
            elif a == "clear":                                  # 1.18.0: Twitch's own clear chat
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                if not await bot._mod_api("DELETE", "moderation/chat", {}):
                    raise RuntimeError(("Twitch refused it (is the bot a moderator?)", "تويتش رفض (البوت مشرف؟)")[ar])
                self.last_done = {"act": "clear", "at": time.time()}
                self._finish(True, heard, ("Chat cleared", "انمسح الشات")[ar])
            elif a in ROLE_ACTS:                                # 1.18.0: VIP / moderator
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                uid = ((getattr(bot, "_chat_info", {}) or {}).get(who["login"]) or (None, None, ""))[2]
                if not uid:
                    users = await bot.fetch_users(logins=[who["login"]])
                    uid = str(users[0].id) if users else ""
                if not uid:
                    raise RuntimeError((f"{who['name']} wasn't found on Twitch", f"{who['name']} مو موجود في تويتش")[ar])
                ok, why = await bot._set_role(a, uid)
                if not ok:
                    raise RuntimeError(self._role_problem(a, why, who["name"]))
                self.last_done = {"act": a, "uid": uid, "name": who["name"], "at": time.time()}
                self._learn(heard, intent, who)
                done = {"vip": ("is a VIP now", "صار في آي بي"), "unvip": ("isn't a VIP anymore", "انشال منه الفي آي بي"),
                        "mod": ("is a moderator now", "صار مشرف"), "unmod": ("isn't a moderator anymore", "انشال منه الإشراف")}[a][ar]
                self._finish(True, heard, f"{who['name']} {done}")
            elif a == "reset":
                from . import counters as C
                before = dict(st.get("counters") or {})
                if intent["is_cmd"]:
                    names = C.reset_from_chat(st, intent["target"], st.get("commands")[intent["target"]], "you (voice)")
                else:
                    C.act(st, "reset", {"name": intent["target"]})
                    names = [intent["target"]]
                keys = [("cmd:" + intent["target"]) if n == "#" else ("name:" + n) for n in names]
                self.last_done = {"act": "reset", "before": {k: before.get(k, 0) for k in keys}, "names": names, "at": time.time()}
                shown = ", ".join(n for n in names if n != "#") or intent["target"]
                self._finish(True, heard, (f"{shown}: 0", f"{shown}: صفر")[ar])
            elif a == "game":
                from . import minigames
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                game = intent["game"]
                on = [g for g in minigames.GAME_KEYS if bot._game_cfg(g).get("enabled")]
                if game == "random":
                    import random
                    if not on:
                        raise RuntimeError("No mini game is on")
                    game = random.choice(on)
                if game not in on:
                    raise RuntimeError((f"«{minigames.GAME_NAMES[game]}» is off (Mini games)", f"«{minigames.GAME_NAMES[game]}» مقفلة")[ar])
                if bot.round and not bot.round.over:
                    raise RuntimeError(("A round is already running", "في جولة شغالة")[ar])
                await bot._game_start(game, bot._game_cfg(game))
                self.last_done = {"act": "game", "round": bot.round, "game": game, "at": time.time()}
                self._finish(True, heard, f"«{minigames.GAME_NAMES[game]}» ▶")
            elif a == "say":
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                if bot.is_command(intent["text"]):      # «قول تعجب when» → !when: sent as you, so the command runs
                    await bot.say_as_you(intent["text"])
                else:
                    await bot._send(intent["text"], why="voice", user="")
                self.last_done = {"act": "say", "at": time.time()}
                self._finish(True, heard, ("Sent: ", "انرسلت: ")[ar] + intent["text"][:60])
            elif a in ("title", "setgame"):
                if bot is None:
                    raise RuntimeError("The bot isn't connected")
                try:
                    old = await (bot._title() if a == "title" else bot._game())
                except Exception:
                    old = None
                await (bot._set_title if a == "title" else bot._set_game)(intent["text"], None)
                if old and not old.startswith("("):
                    self.last_done = {"act": a, "before": old, "at": time.time()}
                self._finish(True, heard, (("Title changed", "Game changed")[a == "setgame"], ("تغيّر العنوان", "تغيّرت اللعبة")[a == "setgame"])[ar])
        except Exception as e:
            if not isinstance(e, RuntimeError):
                log.exception("Voice action failed")
            self._finish(False, heard, str(e)[:80] if isinstance(e, RuntimeError) else self.t("fail"))

    def preview(self) -> None:
        """Settings > Voice > Show it: the corner mic in the chosen style, through listen → think → done."""
        def run():
            self._show("listen", [self.t("listen")])
            time.sleep(1.8)
            self._show("think", [self.t("think")])
            time.sleep(1.2)
            self._show("ok", [self.t("done")], 2.5)
        threading.Thread(target=run, daemon=True).start()

    def shutdown(self) -> None:
        self.key_stop.set()
        self.stop_engine()
        OVERLAY.close()


VOICE = Voice()
