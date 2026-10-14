"""Keeps the app window on a screen (1.9.0).

Windows parks a minimized window at -32000,-32000. If the window is then hidden to the tray, or a monitor is unplugged /
the resolution changes, it can come back somewhere nobody can see or grab it. This checks the window's title bar and,
if not enough of it is on a screen, moves the window back (as close as possible to where it was, or centred when it was
nowhere near a screen). A minimized, hidden or maximized window, or one being dragged right now, is never touched.

Only Windows has this problem; everywhere else every function here does nothing."""

import ctypes
import logging
import os
import sys
import threading
import time

log = logging.getLogger("twitchbot.window")

TITLE_BAR = 40          # height of the strip that must stay reachable (the title bar), in pixels
MIN_GRAB = 120          # at least this much of that strip must be on a screen, so the window can still be dragged
WATCH_EVERY = 3.0       # seconds between checks while the app runs


# ---------- the maths (plain rectangles: (left, top, right, bottom)) ----------

def _overlap(a, b) -> tuple:
    """(width, height) of the overlap of two rectangles (0 when they don't touch)."""
    return max(0, min(a[2], b[2]) - max(a[0], b[0])), max(0, min(a[3], b[3]) - max(a[1], b[1]))


def reachable(rect, work_areas) -> bool:
    """Can the user still see and grab this window? True when enough of its title bar is on one screen's work area."""
    bar = (rect[0], rect[1], rect[2], rect[1] + TITLE_BAR)
    for area in work_areas:
        w, h = _overlap(bar, area)
        if w >= min(MIN_GRAB, rect[2] - rect[0]) and h >= min(20, TITLE_BAR):
            return True
    return False


def rescued(rect, work_areas) -> tuple:
    """Where to put a window that isn't reachable: on the screen it overlaps most (clamped inside it, as near as possible
    to where it was), or centred on the first screen (the main one) when it overlaps none. Never bigger than the screen."""
    if not work_areas:
        return tuple(rect)
    best, best_size = None, 0
    for area in work_areas:
        w, h = _overlap(rect, area)
        if w * h > best_size:
            best, best_size = area, w * h
    area = best or work_areas[0]
    aw, ah = area[2] - area[0], area[3] - area[1]
    w, h = min(rect[2] - rect[0], aw), min(rect[3] - rect[1], ah)
    if best is None:      # nowhere near a screen (e.g. the -32000 "minimized" spot, or an unplugged monitor): centre it
        x, y = area[0] + (aw - w) // 2, area[1] + (ah - h) // 2
    else:
        x = min(max(rect[0], area[0]), area[2] - w)
        y = min(max(rect[1], area[1]), area[3] - h)
    return (x, y, x + w, y + h)


# ---------- Windows ----------

class _Win32:
    """The few Windows calls needed (ctypes, nothing to install)."""

    def __init__(self):
        from ctypes import wintypes
        self.w = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        u = self.user32
        self.RECT = wintypes.RECT

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        class WINDOWPLACEMENT(ctypes.Structure):
            _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT), ("showCmd", wintypes.UINT), ("ptMinPosition", wintypes.POINT),
                        ("ptMaxPosition", wintypes.POINT), ("rcNormalPosition", wintypes.RECT)]

        self.MONITORINFO, self.WINDOWPLACEMENT = MONITORINFO, WINDOWPLACEMENT
        self.EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.MonProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        u.EnumWindows.argtypes = [self.EnumProc, wintypes.LPARAM]
        u.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, self.MonProc, wintypes.LPARAM]
        u.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.IsWindow.argtypes = [wintypes.HWND]
        for f in (u.IsWindowVisible, u.IsIconic, u.IsZoomed):
            f.argtypes = [wintypes.HWND]
        u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u.GetAsyncKeyState.restype = ctypes.c_short

    def find(self, title: str):
        """This program's own top-level window with that title (another program's window is never touched)."""
        found, me = [], os.getpid()

        def each(hwnd, _):
            pid = self.w.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == me:
                buf = ctypes.create_unicode_buffer(256)
                self.user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value == title:
                    found.append(hwnd)
                    return False
            return True

        self.user32.EnumWindows(self.EnumProc(each), 0)
        return found[0] if found else None

    def alive(self, hwnd) -> bool:
        """The window found before still exists (so it doesn't have to be searched for among all windows again)."""
        return bool(self.user32.IsWindow(hwnd))

    def work_areas(self) -> list:
        """Every screen's usable area (without the taskbar); the main screen first."""
        areas = []

        def each(hmon, hdc, rect, _):
            info = self.MONITORINFO()
            info.cbSize = ctypes.sizeof(self.MONITORINFO)
            if self.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcWork
                (areas.insert(0, (r.left, r.top, r.right, r.bottom)) if info.dwFlags & 1 else areas.append((r.left, r.top, r.right, r.bottom)))
            return True

        self.user32.EnumDisplayMonitors(None, None, self.MonProc(each), 0)
        return areas

    def state(self, hwnd):
        """(rect, ok_to_move): never move a hidden, minimized or maximized window, or one the user is dragging."""
        u = self.user32
        place = self.WINDOWPLACEMENT()
        place.length = ctypes.sizeof(self.WINDOWPLACEMENT)
        u.GetWindowPlacement(hwnd, ctypes.byref(place))
        dragging = bool(u.GetAsyncKeyState(0x01) & 0x8000)          # left mouse button held
        movable = bool(u.IsWindowVisible(hwnd)) and not u.IsIconic(hwnd) and not u.IsZoomed(hwnd) and place.showCmd not in (2, 3, 6, 7) and not dragging
        r = self.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        return (r.left, r.top, r.right, r.bottom), movable

    def move(self, hwnd, rect) -> None:
        SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
        self.user32.SetWindowPos(hwnd, None, rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1], SWP_NOZORDER | SWP_NOACTIVATE)


_api = None
_found = {}           # title -> window handle, remembered between checks


def _win32():
    global _api
    if _api is None and sys.platform == "win32":
        try:
            _api = _Win32()
        except Exception:
            log.exception("Window position checks are not available")
            _api = False
    return _api or None


def keep_on_screen(title: str, api=None) -> bool:
    """Moves the window back onto a screen if it can't be reached. True when it was moved."""
    api = api or _win32()
    if api is None:
        return False
    try:
        hwnd = _found.get(title)
        if hwnd and not (hasattr(api, "alive") and api.alive(hwnd)):
            hwnd = None
        if not hwnd:
            hwnd = api.find(title)                 # looks through every window: done once, then remembered
            if hwnd and hasattr(api, "alive"):
                _found[title] = hwnd
        if not hwnd:
            return False
        rect, movable = api.state(hwnd)
        areas = api.work_areas()
        if not movable or not areas or reachable(rect, areas):
            return False
        target = rescued(rect, areas)
        api.move(hwnd, target)
        log.info("The window was off the screen at %s: moved back to %s", rect, target)
        return True
    except Exception:
        log.exception("Could not check the window position")
        return False


def watch(title: str, stop=None, api=None, every: float = WATCH_EVERY, sleep=time.sleep) -> None:
    """Checks every few seconds while the app runs (also catches a monitor being unplugged or the resolution changing).
    Runs on its own background thread; stop() returning True ends it."""
    api = api or _win32()
    if api is None:
        return
    while not (stop and stop()):
        keep_on_screen(title, api)
        sleep(every)


def start_watching(title: str, stop=None) -> threading.Thread | None:
    if _win32() is None:
        return None
    t = threading.Thread(target=watch, args=(title, stop), daemon=True, name="window-position")
    t.start()
    return t
