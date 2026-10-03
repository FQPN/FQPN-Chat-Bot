"""What this copy of the app can do on this computer (start with Windows, tray icon, pop-ups), and the Windows
start-up entry. The launcher fills in the parts that need the app window."""

import logging
import sys

log = logging.getLogger("desktop")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "FQPNsChatBot"
FROZEN = bool(getattr(sys, "frozen", False))
WINDOWS = sys.platform == "win32"

# What the Settings page may offer. "tray" and "notify" are switched on by the launcher once the tray icon exists.
caps = {"installed": FROZEN, "startup": WINDOWS and FROZEN, "tray": False, "notify": False, "sound": WINDOWS}

quit_app = None   # set by the launcher: closes the app window for real (used to install an update)
show_window = None   # set by the launcher: brings the app window to the front (a second launch asks for this)


def startup_command(minimized: bool, exe: str | None = None) -> str:
    return f'"{exe or sys.executable}"' + (" --minimized" if minimized else "")


def set_startup(enabled: bool, minimized: bool) -> None:
    """Adds or removes the 'start with Windows' entry for the current user (no administrator rights needed)."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command(minimized))
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def apply_prefs(prefs: dict) -> None:
    """Makes Windows match the settings. Does nothing when running from source."""
    if caps["startup"]:
        set_startup(bool(prefs.get("startup", False)), bool(prefs.get("start_minimized", False)))
