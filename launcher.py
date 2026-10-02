"""Starts the bot when it is installed with the installer (no Python needed).

The install folder is read-only, so everything the bot saves goes into the user's own folder instead:
    %APPDATA%\\TwitchChatBot\\data              commands, timers, greetings, events, settings
    %APPDATA%\\TwitchChatBot\\authentication    the Twitch login
    %APPDATA%\\TwitchChatBot\\bot.log           what the bot printed (useful when asking for help)
Reinstalling or updating never touches that folder.

The dashboard is shown in its own app window (pywebview). Closing the window stops the bot."""

import asyncio
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

# With console=False there is no console, so sys.stdout / sys.stderr are None.
# Give them a harmless target so print() can never crash the app.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

APP_NAME = "TwitchChatBot"


def user_home() -> Path:
    base = Path(os.environ.get("APPDATA") or (Path.home() / ".config"))
    home = base / APP_NAME
    home.mkdir(parents=True, exist_ok=True)
    return home


def resource_dir() -> Path:
    """Where the files bundled with the program are (the dashboard page)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def configure(home: Path, resources: Path) -> None:
    """Points the bot at the per-user folders and at the bundled dashboard page."""
    from core import auth, dashboard, store
    store.DATA_DIR = home / "data"
    auth.AUTH_DIR = home / "authentication"
    auth.TOKEN_FILE = auth.AUTH_DIR / "token.json"
    dashboard.PAGE = resources / "core" / "dashboard.html"


def wait_for_port(port: int, timeout: float = 20) -> bool:
    """Waits until the dashboard server is accepting connections."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def run() -> None:
    for stream in (sys.stdout, sys.stderr):          # Arabic names and emoji in the log
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    home = user_home()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(home / "bot.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"),
        ],
    )
    configure(home, resource_dir())
    log = logging.getLogger("launcher")
    log.info("Data folder: %s", home)

    import main
    from core import dashboard

    # The bot runs in a background thread because the app window must use the main thread.
    def bot_thread():
        try:
            asyncio.run(main.main(open_browser=False))
        except Exception:
            log.exception("The bot crashed")

    threading.Thread(target=bot_thread, daemon=True).start()

    if not wait_for_port(dashboard.PORT):
        log.error("The dashboard did not start")

    url = f"http://localhost:{dashboard.PORT}"
    try:
        import webview
        webview.create_window("FQPN's Chat Bot", url, width=1280, height=800, min_size=(900, 600))
        # private_mode=False + storage_path keeps the dashboard's theme/language between launches
        webview.start(private_mode=False, storage_path=str(home / "webview"))
        # Window closed -> this function ends and the daemon bot thread stops with the program.
    except Exception:
        log.exception("Could not open the app window, using the browser instead")
        webbrowser.open(url)
        while True:                    # keep the bot alive
            time.sleep(3600)


if __name__ == "__main__":
    run()
