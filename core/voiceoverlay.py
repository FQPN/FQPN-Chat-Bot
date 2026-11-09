"""1.17.0 (beta): the small mic in a corner of the screen while Voice commands listens (Windows only).

A tiny window that is always on top, never takes the focus and lets every click through to the game below it. Its
picture is drawn with Pillow (already part of the app) and handed to Windows as a see-through layered window.
It shows over games in borderless / windowed fullscreen; Windows lets nothing draw over "exclusive fullscreen".

Nothing here runs until Voice commands is used: the window (and its thread) is made the first time it's needed."""
import logging
import queue
import sys
import threading
import time

log = logging.getLogger("voice")

KINDS = ("listen", "think", "ok", "fail", "ask")
COLORS = {"listen": (229, 72, 77), "think": (210, 153, 34), "ok": (63, 185, 80), "fail": (139, 139, 149), "ask": (88, 166, 255)}
MARGIN = 24


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    for name in (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _raqm() -> bool:
    try:
        from PIL import features
        return bool(features.check("raqm"))
    except Exception:
        return False


def _shape(text: str) -> str:
    """Arabic letters joined and in the right order for drawing. Pillow does it by itself when it has its text layout
    library (raqm); otherwise (usual on Windows) the letters are joined here and the order turned around."""
    if not any("\u0600" <= c <= "\u06ff" for c in text) or _raqm():
        return text
    try:
        import arabic_reshaper
        shaped = arabic_reshaper.reshape(text)
    except Exception:
        shaped = text
    # right-to-left: reverse the order, but keep Latin words and numbers (names, 10) as they are
    import re
    parts = re.split(r"([A-Za-z0-9_@!.:\-]+)", shaped)
    return "".join(p if re.fullmatch(r"[A-Za-z0-9_@!.:\-]+", p or "-") and p else p[::-1] for p in reversed(parts))


def draw(kind: str, lines: list, frame: int = 0, scale: float = 1.0):
    """The picture: a round icon (mic / dots / tick / cross / ?) and up to 4 short lines of text. Returns a Pillow RGBA image."""
    from PIL import Image, ImageDraw
    s = scale
    icon = int(56 * s)
    pad = int(10 * s)
    f1, f2 = _font(int(17 * s), True), _font(int(14 * s))
    lines = [_shape(str(x)) for x in (lines or []) if x][:4]
    tw = 0
    if lines:
        probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        tw = max(probe.textlength(t, font=f1 if i == 0 else f2) for i, t in enumerate(lines)) + pad * 2
    th = (int(24 * s) + int(19 * s) * (len(lines) - 1)) if lines else 0
    w = icon + pad * 2 + int(tw)
    h = max(icon + pad * 2, th + pad * 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=int(18 * s), fill=(16, 16, 20, 225), outline=(255, 255, 255, 40), width=1)
    col = COLORS.get(kind, COLORS["fail"])
    cx, cy = pad + icon // 2, h // 2
    r = icon // 2
    if kind == "listen":                                       # pulsing ring
        ring = r + int((4 + 3 * (frame % 2)) * s)
        d.ellipse((cx - ring, cy - ring, cx + ring, cy + ring), outline=col + (150 - 60 * (frame % 2),), width=int(3 * s))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (255,))
    white = (255, 255, 255, 255)
    if kind == "listen":                                       # a microphone
        mw, mh = int(14 * s), int(22 * s)
        d.rounded_rectangle((cx - mw // 2, cy - int(16 * s), cx + mw // 2, cy - int(16 * s) + mh), radius=mw // 2, fill=white)
        d.arc((cx - int(12 * s), cy - int(10 * s), cx + int(12 * s), cy + int(12 * s)), 0, 180, fill=white, width=int(3 * s))
        d.line((cx, cy + int(12 * s), cx, cy + int(17 * s)), fill=white, width=int(3 * s))
    elif kind == "think":                                      # three dots
        for i in range(3):
            x = cx + (i - 1) * int(11 * s)
            rr = int((4 if (frame % 3) == i else 3) * s)
            d.ellipse((x - rr, cy - rr, x + rr, cy + rr), fill=white)
    elif kind == "ok":                                         # a tick
        d.line((cx - int(12 * s), cy, cx - int(3 * s), cy + int(9 * s), cx + int(13 * s), cy - int(9 * s)), fill=white, width=int(5 * s), joint="curve")
    elif kind == "fail":                                       # a cross
        k = int(10 * s)
        d.line((cx - k, cy - k, cx + k, cy + k), fill=white, width=int(5 * s))
        d.line((cx - k, cy + k, cx + k, cy - k), fill=white, width=int(5 * s))
    else:                                                      # a question mark
        d.text((cx, cy), "?", font=_font(int(30 * s), True), fill=white, anchor="mm")
    y = (h - th) // 2
    for i, t in enumerate(lines):
        d.text((icon + pad * 2, y), t, font=f1 if i == 0 else f2, fill=(241, 241, 243, 255) if i == 0 else (197, 197, 204, 255))
        y += int(24 * s) if i == 0 else int(19 * s)
    return img


class Overlay:
    """show(kind, lines, corner, seconds=None) / hide(). Thread-safe; the window lives in its own thread."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.thread = None

    def show(self, kind: str, lines=None, corner: str = "tr", seconds: float | None = None, style: str = "capsule"):
        self._ensure()
        self.q.put(("show", kind, list(lines or []), corner, seconds, style))

    def hide(self):
        if self.thread is not None:
            self.q.put(("hide",))

    def close(self):
        if self.thread is not None:
            self.q.put(("quit",))

    def _ensure(self):
        if sys.platform != "win32":
            return
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, name="voice-overlay", daemon=True)
            self.thread.start()

    # ---------- the window (Windows only) ----------

    def _run(self):
        try:
            self._win()
        except Exception:
            log.exception("The voice overlay stopped")

    def _win(self):
        import ctypes
        from ctypes import wintypes as W
        # private copies of the Windows libraries: the tray icon (pystray) and the app window set their own argument
        # types on the shared ctypes.windll ones, and the two settings must never fight
        u32, g32, k32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("gdi32"), ctypes.WinDLL("kernel32")
        try:
            u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))      # per-monitor aware: crisp, real pixels
        except Exception:
            pass
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        u32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        u32.DefWindowProcW.restype = ctypes.c_ssize_t
        proc = WNDPROC(lambda h, m, w, l: u32.DefWindowProcW(h, m, w, l))
        self._proc = proc                                # (kept alive as long as the window: Windows calls it)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", W.UINT), ("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON), ("hCursor", W.HANDLE),
                        ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR), ("hIconSm", W.HICON)]
        k32.GetModuleHandleW.restype = W.HMODULE
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSEXW(ctypes.sizeof(WNDCLASSEXW), 0, proc, 0, 0, hinst, None, None, None, None, "FQPNVoiceOverlay", None)
        u32.RegisterClassExW(ctypes.byref(wc))
        WS_EX = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000   # layered, click-through, topmost, toolwindow, no-activate
        u32.CreateWindowExW.restype = W.HWND
        u32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
        hwnd = u32.CreateWindowExW(WS_EX, "FQPNVoiceOverlay", "FQPN voice", 0x80000000, 0, 0, 10, 10, None, None, hinst, None)
        if not hwnd:
            log.warning("The voice overlay window could not be made (Windows error %s)", ctypes.get_last_error())
            return
        log.info("Voice overlay: window ready")

        class BLEND(ctypes.Structure):
            _fields_ = [("op", ctypes.c_byte), ("flags", ctypes.c_byte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_byte)]

        class BMIH(ctypes.Structure):
            _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                        ("biCompression", W.DWORD), ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                        ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]
        g32.CreateDIBSection.restype = W.HBITMAP
        g32.CreateDIBSection.argtypes = [W.HDC, ctypes.c_void_p, W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD]
        g32.CreateCompatibleDC.restype = W.HDC
        g32.CreateCompatibleDC.argtypes = [W.HDC]
        g32.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
        g32.SelectObject.restype = W.HGDIOBJ
        g32.DeleteObject.argtypes = [W.HGDIOBJ]
        g32.DeleteDC.argtypes = [W.HDC]
        u32.GetDC.restype = W.HDC
        u32.GetDC.argtypes = [W.HWND]
        u32.ReleaseDC.argtypes = [W.HWND, W.HDC]
        u32.UpdateLayeredWindow.argtypes = [W.HWND, W.HDC, ctypes.POINTER(W.POINT), ctypes.POINTER(W.SIZE), W.HDC,
                                            ctypes.POINTER(W.POINT), W.COLORREF, ctypes.POINTER(BLEND), W.DWORD]
        u32.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
        u32.ShowWindow.argtypes = [W.HWND, ctypes.c_int]
        u32.PeekMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
        u32.GetDpiForWindow.argtypes = [W.HWND]

        def paint(img, corner):
            from PIL import Image
            w, h = img.size
            sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)       # the main screen
            x = MARGIN if corner in ("tl", "bl") else sw - w - MARGIN
            y = MARGIN if corner in ("tl", "tr") else sh - h - MARGIN - 48   # (above the taskbar)
            r, g, b, a = img.convert("RGBa").split()                         # Windows wants pre-multiplied BGRA
            raw = Image.merge("RGBA", (b, g, r, a)).tobytes()
            screen = u32.GetDC(None)
            mem = g32.CreateCompatibleDC(screen)
            bmi = BMIH(ctypes.sizeof(BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            bits = ctypes.c_void_p()
            bmp = g32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            ctypes.memmove(bits, raw, len(raw))
            old = g32.SelectObject(mem, bmp)
            done = u32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(W.POINT(x, y)), ctypes.byref(W.SIZE(w, h)), mem,
                                           ctypes.byref(W.POINT(0, 0)), 0, ctypes.byref(BLEND(0, 0, 255, 1)), 2)
            if not done:
                log.warning("Voice overlay: Windows refused the picture (error %s)", ctypes.get_last_error())
            g32.SelectObject(mem, old)
            g32.DeleteObject(bmp)
            g32.DeleteDC(mem)
            u32.ReleaseDC(None, screen)
            u32.SetWindowPos(hwnd, W.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)   # topmost again, no move, no activate, show

        cur, frame, until, last = None, 0, None, 0.0
        msg = W.MSG()
        while True:
            while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
            try:
                item = self.q.get(timeout=0.04)
            except queue.Empty:
                item = None
            if item:
                if item[0] == "quit":
                    u32.DestroyWindow(hwnd)
                    return
                if item[0] == "hide":
                    cur = None
                    u32.ShowWindow(hwnd, 0)
                    continue
                _, kind, lines, corner, seconds, style = item
                cur, frame, last = (kind, lines, corner, style), 0, 0.0
                start = time.monotonic()
                until = (start + seconds) if seconds else None
            if cur is None:
                continue
            if until and time.monotonic() > until:
                cur = None
                u32.ShowWindow(hwnd, 0)
                continue
            asking = cur[0] == "ask" and until
            if time.monotonic() - last >= (0.18 if cur[0] in ("listen", "think") else 0.5 if asking else 5):
                try:
                    scale = max(1.0, (u32.GetDpiForWindow(hwnd) or 96) / 96)
                except Exception:
                    scale = 1.0
                left = max(0.0, (until - time.monotonic()) / (until - start)) if asking else None
                try:
                    from . import voicestyles
                    img = voicestyles.draw(cur[3], cur[0], cur[1], frame, scale, left)
                except Exception:
                    if frame == 0:
                        log.exception("Voice overlay: the %s style couldn't be drawn: the simple one is shown", cur[3])
                    img = draw(cur[0], cur[1], frame, scale)
                try:
                    paint(img, cur[2])
                    if frame == 0:
                        log.info("Voice overlay: shown (%s, %s)", cur[3], cur[0])
                except Exception:
                    log.exception("Voice overlay: couldn't be shown")
                    cur = None
                frame += 1
                last = time.monotonic()


OVERLAY = Overlay()
