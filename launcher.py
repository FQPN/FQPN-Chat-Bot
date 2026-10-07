"""Starts the bot when it is installed with the installer (no Python needed).

The install folder is read-only, so everything the bot saves goes into the user's own folder instead:
    %APPDATA%\\TwitchChatBot\\data              commands, timers, greetings, events, settings
    %APPDATA%\\TwitchChatBot\\authentication    the Twitch login
    %APPDATA%\\TwitchChatBot\\bot.log           what the bot printed (useful when asking for help)
    %APPDATA%\\TwitchChatBot\\updates           a downloaded update, waiting to be installed
Reinstalling or updating never touches that folder.

The dashboard is shown in its own app window (pywebview). Depending on Settings > App, closing the window
either stops the bot or keeps it running in the system tray (pystray)."""

import asyncio
import json
import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

# With console=False there is no console, so sys.stdout / sys.stderr are None.
# Give them a harmless target so print() can never crash the app.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

APP_NAME = "TwitchChatBot"
log = logging.getLogger("launcher")

PREF_DEFAULTS = {"startup": False, "start_minimized": False, "on_close": "quit", "auto_reconnect": True,
                 "auto_update": True, "notify": True, "notify_sound": False, "log_days": 30, "log_chat": False}


MUTEX_NAME = "Local\\FQPNsChatBot"        # one per Windows user
ERROR_ALREADY_EXISTS = 183


class WinMutex:
    """A Windows "named mutex". Only one copy of the app can own it, so a second launch knows another copy is running.
    On other systems it never blocks."""

    def __init__(self, name: str = MUTEX_NAME):
        self.name = name
        self.handle = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = ctypes.c_void_p
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = k.CreateMutexW(None, False, self.name)
        if not handle:
            return True                       # could not tell: never stop the app from starting
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            k.CloseHandle(handle)
            return False
        self.handle = handle                  # kept for as long as the program runs
        return True


def read_port(home: Path):
    """The port the running copy's dashboard uses (it writes it to a file when it starts), or None."""
    try:
        port = int((home / "dashboard.port").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return port if 1024 <= port <= 65535 else None


def clear_port(home: Path) -> None:
    try:
        (home / "dashboard.port").unlink()
    except OSError:
        pass


def wake_existing(port, timeout: float = 3.0) -> str:
    """Asks the copy that is already running to show its window.
    Returns "shown", "nowindow" (it has no window yet) or "" (could not reach it)."""
    if not port:
        return ""
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/show", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "shown" if json.load(r).get("shown") else "nowindow"
    except Exception:
        return ""


def _allow_foreground() -> None:
    """Lets the copy that is already running come to the front when asked (Windows normally forbids that)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass


def _message_box(text: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, "FQPN's Chat Bot", 0x40)
            return
        except Exception:
            pass
    print(text)


def ensure_single_instance(get_port, mutex=None, wake=wake_existing, sleep=time.sleep, wait: float = 20.0,
                           step: float = 0.5, quiet: bool = False, say=_message_box) -> bool:
    """True: this is the only copy, carry on. False: another copy is running (it was asked to show its window, or the
    user was told), so this one must exit. Two copies would both answer in chat.
    The dashboard is only ever shown in the app window, never in a browser: if the other copy has no window yet
    (it is still starting), this waits and asks again."""
    mutex = mutex or WinMutex()
    end = time.time() + wait
    while True:
        if mutex.acquire():
            return True
        if quiet:                             # started by Windows with --minimized while a copy runs: stay silent
            return False
        _allow_foreground()
        if wake(get_port()) == "shown":       # "nowindow" or "" means the other copy is still starting up
            return False
        if time.time() >= end:                # still nothing: it may be stuck
            say("FQPN's Chat Bot is already running, but its window isn't ready. Wait a few seconds and try again, "
                "look for its icon in the system tray, or close it in Task Manager and start it again.")
            return False
        sleep(step)                           # it may also just be closing (for example during an update): try again


WINDOW_HELP = ("FQPN's Chat Bot couldn't open its window.\n\n"
               "It needs the free Microsoft Edge WebView2 Runtime. Install it from:\n"
               "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
               "Then start the app again. More details are in bot.log inside %APPDATA%\\TwitchChatBot.")


def fail_no_window(say=_message_box, leave=os._exit) -> None:
    """The app window could not open. The dashboard is never shown in a browser, so tell the user what to do and stop
    (a bot running with no window at all would be impossible to control)."""
    log.error("The app window could not open")
    say(WINDOW_HELP)
    leave(1)


def fail_no_dashboard(error, say=_message_box, leave=os._exit) -> None:
    """The dashboard could not start (no free local port). Say so plainly and stop."""
    log.error("The dashboard could not start: %s", error)
    say("FQPN's Chat Bot couldn't start its dashboard" + (f" ({error})" if error else "") + ".\n\n"
        "Another program is using the local network ports it needs. Close other programs that run a local web server "
        "(for example a Flask or Node app), or restart the computer, then start the app again.")
    leave(1)


def user_home() -> Path:
    base = Path(os.environ.get("APPDATA") or (Path.home() / ".config"))
    home = base / APP_NAME
    home.mkdir(parents=True, exist_ok=True)
    return home


def resource_dir() -> Path:
    """Where the files bundled with the program are (the dashboard page, the icon)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def configure(home: Path, resources: Path) -> None:
    """Points the bot at the per-user folders and at the bundled dashboard page."""
    from core import auth, dashboard, store, updater
    store.DATA_DIR = home / "data"
    auth.AUTH_DIR = home / "authentication"
    auth.TOKEN_FILE = auth.AUTH_DIR / "token.json"
    dashboard.PAGE = resources / "core" / "dashboard.html"
    dashboard.PORT_FILE = home / "dashboard.port"
    updater.UPDATES_DIR = home / "updates"


def read_prefs(home: Path) -> dict:
    """The app settings (Settings > App ...), read fresh each time so a change takes effect without a restart."""
    prefs = dict(PREF_DEFAULTS)
    try:
        data = json.loads((home / "data" / "prefs.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            prefs.update({k: v for k, v in data.items() if k in PREF_DEFAULTS})
    except (OSError, ValueError):
        pass
    return prefs


def tray_importable() -> bool:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


def tray_image(resources: Path):
    from PIL import Image
    try:
        return Image.open(resources / "icon.ico").convert("RGBA")
    except Exception:
        return Image.new("RGBA", (64, 64), (154, 17, 24, 255))     # a plain red square if the icon is missing


class Shell:
    """The app window plus its tray icon. Everything about the tray is optional: if it cannot start, the app simply
    behaves as it did before (closing the window stops the bot)."""

    def __init__(self, home: Path, resources: Path):
        self.home, self.resources = home, resources
        self.window = None
        self.icon = None
        self.quitting = False

    def closing(self):
        """Called just before the window closes. Returning False keeps it alive in the tray instead."""
        if self.quitting or self.icon is None or read_prefs(self.home).get("on_close") != "tray":
            return True
        threading.Thread(target=self.hide, daemon=True).start()
        return False

    def hide(self):
        try:
            self.window.hide()
        except Exception:
            log.exception("Could not hide the window")

    def show(self):
        try:
            self.window.show()
            if hasattr(self.window, "restore"):
                self.window.restore()
        except Exception:
            log.exception("Could not show the window")

    def quit(self):
        """Really closes the app (the tray's Quit, and installing an update)."""
        self.quitting = True
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass
        try:
            self.window.destroy()
        except Exception:
            log.exception("Could not close the window")

    def start_tray(self, started_hidden: bool = False):
        """Runs on a helper thread once the window exists."""
        from core import desktop, notify
        try:
            import pystray
            image = tray_image(self.resources)
            menu = pystray.Menu(
                pystray.MenuItem("Open FQPN's Chat Bot", lambda icon, item: self.show(), default=True),
                pystray.MenuItem("Quit", lambda icon, item: self.quit()),
            )
            icon = pystray.Icon("FQPNsChatBot", image, "FQPN's Chat Bot", menu)
            icon.run_detached()
            self.icon = icon
            notify.register(lambda title, message: icon.notify(message, title))
            desktop.caps["tray"] = True
            desktop.caps["notify"] = True
            desktop.quit_app = self.quit
        except ImportError:
            self.icon = None
            log.warning("No tray icon: pystray or Pillow is not installed (pip install -r requirements.txt)")
            if started_hidden:
                self.show()
        except Exception:
            self.icon = None
            log.exception("The tray icon could not start; the app works without it")
            if started_hidden:
                self.show()      # never leave the user with a window nobody can open

    def shutdown(self):
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass


def install_pending_update(home: Path) -> None:
    """If an update was downloaded and 'Check for updates automatically' is on, install it now that the app closes."""
    try:
        from core import updater
        if read_prefs(home).get("auto_update", True):
            path = updater.ready_installer(updater.U)
            if path:
                log.info("Installing the downloaded update %s", path.name)
                updater.launch_installer(path, relaunch=False)
                updater.U["status"] = "installing"
    except Exception:
        log.exception("Could not start the update installer")


def run() -> None:
    home = user_home()
    if not ensure_single_instance(lambda: read_port(home), quiet="--minimized" in sys.argv):
        os._exit(0)                                   # another copy is running: it has been asked to show its window
    for stream in (sys.stdout, sys.stderr):          # Arabic names and emoji in the log
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(home / "bot.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"),
        ],
    )
    configure(home, resource_dir())
    log.info("Data folder: %s", home)

    import main
    from core import dashboard, desktop

    # The bot runs in a background thread because the app window must use the main thread.
    def bot_thread():
        try:
            asyncio.run(main.main())
        except Exception:
            log.exception("The bot crashed")

    threading.Thread(target=bot_thread, daemon=True).start()

    # Wait until OUR dashboard is listening (not just until "something" answers on port 5000: another program may use it).
    if not dashboard.ready.wait(30) or dashboard.start_error:
        fail_no_dashboard(dashboard.start_error)
    url = f"http://127.0.0.1:{dashboard.PORT}"        # the port really in use; 127.0.0.1 can never be mistaken for another address
    try:
        import webview
        # Started by Windows with "Start minimized" on: go straight to the tray (only if a tray icon is possible)
        hidden = "--minimized" in sys.argv and tray_importable()
        shell = Shell(home, resource_dir())
        shell.window = webview.create_window("FQPN's Chat Bot", url, width=1280, height=800, min_size=(1000, 650), hidden=hidden)
        shell.window.events.closing += shell.closing
        desktop.show_window = shell.show              # a second launch asks this copy to show its window
        # private_mode=False + storage_path keeps the dashboard's theme/language between launches
        # On Windows the window must be the Edge (WebView2) one: the old built-in engine cannot show this dashboard properly.
        webview.start(shell.start_tray, (hidden,), private_mode=False, storage_path=str(home / "webview"),
                      gui="edgechromium" if sys.platform == "win32" else None)
        # Window closed for real -> stop the tray, install a waiting update, and end the program.
        shell.shutdown()
        clear_port(home)
        install_pending_update(home)
        logging.shutdown()
        os._exit(0)
    except Exception:
        log.exception("Could not open the app window")
        fail_no_window()


if __name__ == "__main__":
    run()
