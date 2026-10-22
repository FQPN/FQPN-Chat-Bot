"""The window's top bar in the app's own colors (1.13.0).

Windows draws the bar (so dragging, snapping, double-click to maximize and the three buttons all keep working); the app
only asks Windows to paint it: Windows 11 takes the exact background and text colors, Windows 10 (and older 11 builds)
only switch it to dark or light. The page sends its colors whenever the theme changes (POST /api/titlebar); the launcher
calls apply() for this program's own window. Nothing here can stop the app: a failure is logged and ignored."""

import logging
import re
import sys

log = logging.getLogger("titlebar")

HEX = re.compile(r"^#[0-9a-f]{6}$")
DARK_MODE = (20, 19)          # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 2004+ / 11; 19 on older Windows 10 builds)
BORDER, CAPTION, TEXT = 34, 35, 36    # DWMWA_BORDER_COLOR / DWMWA_CAPTION_COLOR / DWMWA_TEXT_COLOR (Windows 11)
last: dict = {}               # the colors last asked for (used again if the window is made again)


def colorref(hexcolor: str) -> int:
    """'#rrggbb' -> Windows' COLORREF (0x00bbggrr)."""
    r, g, b = int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16)
    return r | (g << 8) | (b << 16)


class _Dwm:
    def __init__(self):
        import ctypes
        from . import winpos
        self.ctypes = ctypes
        self.dwm = ctypes.windll.dwmapi
        self.win = winpos._win32()

    def find(self, title: str):
        return self.win.find(title) if self.win else None

    def set(self, hwnd, attr: int, value: int) -> int:
        v = self.ctypes.c_int(value)
        return self.dwm.DwmSetWindowAttribute(self.ctypes.c_void_p(hwnd), attr, self.ctypes.byref(v), self.ctypes.sizeof(v))


def apply(title: str, bg: str, fg: str, dark: bool, api=None) -> bool:
    """Paints the window's bar. True when Windows took at least the dark/light switch."""
    bg, fg = str(bg).lower(), str(fg).lower()
    if not (HEX.match(bg) and HEX.match(fg)):
        return False
    last.update(bg=bg, fg=fg, dark=bool(dark))
    try:
        if api is None:
            if sys.platform != "win32":
                return False
            api = _Dwm()
        hwnd = api.find(title)
        if not hwnd:
            return False
        ok = False
        for attr in DARK_MODE:
            if api.set(hwnd, attr, 1 if dark else 0) == 0:
                ok = True
                break
        for attr, value in ((CAPTION, colorref(bg)), (TEXT, colorref(fg)), (BORDER, colorref(bg))):
            api.set(hwnd, attr, value)        # Windows 10 says no to these: it just keeps the dark/light bar
        return ok
    except Exception:
        log.exception("Could not color the window's top bar")
        return False


def reapply(title: str, api=None) -> bool:
    return apply(title, last["bg"], last["fg"], last["dark"], api) if last else False
