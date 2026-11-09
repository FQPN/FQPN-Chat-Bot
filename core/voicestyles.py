"""1.17.0 (beta): the four looks of the corner mic (Settings > Voice > Style). Drawn with Pillow at 3x and scaled
down, so the edges are smooth. Each style draws the same five moments: listen, think, ok, fail, ask.

draw(style, kind, lines, frame, scale, left) -> RGBA image
  lines: [title, more lines...]   frame: animation step   left: 0..1 time left on a question (or None)"""
import math
import random
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

STYLES = ("capsule", "orb", "wave", "card")
SS = 3                                                    # drawn this many times bigger, then scaled down (smooth edges)
COL = {"listen": (229, 72, 77), "think": (232, 170, 40), "ok": (63, 185, 80), "fail": (150, 150, 160), "ask": (88, 166, 255)}
RED = (154, 17, 24)
INK = (241, 241, 243)
SOFT = (190, 190, 200)
BG = (14, 14, 18)

_FONTS: dict = {}


def font(size: int, bold: bool = False):
    key = (size, bold)
    if key not in _FONTS:
        f = None
        for name in (("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold
                     else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")):
            try:
                f = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        _FONTS[key] = f or ImageFont.load_default()
    return _FONTS[key]


def _raqm() -> bool:
    try:
        from PIL import features
        return bool(features.check("raqm"))
    except Exception:
        return False


def shape(text: str) -> str:
    """Arabic joined and right-to-left when Pillow can't do it itself (usual on Windows)."""
    text = str(text)
    if not any("؀" <= c <= "ۿ" for c in text) or _raqm():
        return text
    try:
        import arabic_reshaper
        text = arabic_reshaper.reshape(text)
    except Exception:
        pass
    parts = re.split(r"([A-Za-z0-9_@!.:\-]+)", text)
    return "".join(p if re.fullmatch(r"[A-Za-z0-9_@!.:\-]+", p or "-") and p else p[::-1] for p in reversed(parts))


def _tw(d, text, f):
    return d.textlength(text, font=f) if text else 0


# ---------- the five little pictures (drawn white on a colored circle, or in a color) ----------

def glyph(d, kind, cx, cy, r, color=(255, 255, 255), frame=0):
    w = max(2, int(r * 0.17))
    if kind == "listen":                                   # a microphone
        mw, mh = r * 0.52, r * 0.86
        d.rounded_rectangle((cx - mw / 2, cy - r * 0.62, cx + mw / 2, cy - r * 0.62 + mh), radius=mw / 2, fill=color)
        d.arc((cx - r * 0.5, cy - r * 0.42, cx + r * 0.5, cy + r * 0.48), 0, 180, fill=color, width=w)
        d.line((cx, cy + r * 0.48, cx, cy + r * 0.7), fill=color, width=w)
        d.line((cx - r * 0.25, cy + r * 0.7, cx + r * 0.25, cy + r * 0.7), fill=color, width=w)
    elif kind == "think":                                  # three dots, one bigger each step
        for i in range(3):
            x = cx + (i - 1) * r * 0.45
            rr = r * (0.17 if frame % 3 == i else 0.11)
            d.ellipse((x - rr, cy - rr, x + rr, cy + rr), fill=color)
    elif kind == "ok":                                     # a tick
        d.line((cx - r * 0.45, cy + r * 0.02, cx - r * 0.12, cy + r * 0.34, cx + r * 0.48, cy - r * 0.32), fill=color, width=int(w * 1.3), joint="curve")
    elif kind == "fail":                                   # a cross
        k = r * 0.36
        d.line((cx - k, cy - k, cx + k, cy + k), fill=color, width=int(w * 1.2))
        d.line((cx - k, cy + k, cx + k, cy - k), fill=color, width=int(w * 1.2))
    else:                                                  # a question mark
        d.text((cx, cy + r * 0.04), "?", font=font(int(r * 1.15), True), fill=color, anchor="mm")


def _glow(img, box, color, radius, strength=150):
    """A soft colored glow behind a round shape."""
    g = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse(box, fill=color + (strength,))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(radius)))


def _down(img, scale_note=None):
    w, h = img.size
    return img.resize((max(1, w // SS), max(1, h // SS)), Image.LANCZOS)


def _wave(d, x0, y0, w, h, color, frame, bars=14, level=None):
    """Sound bars that move while you talk."""
    rnd = random.Random(frame * 7919)
    gap = w / bars
    for i in range(bars):
        base = 0.35 + 0.65 * abs(math.sin(frame * 0.9 + i * 0.7))
        v = max(0.12, min(1.0, base * (0.6 + 0.4 * rnd.random()) * (level if level is not None else 1)))
        bh = h * v
        x = x0 + i * gap + gap * 0.2
        d.rounded_rectangle((x, y0 + (h - bh) / 2, x + gap * 0.6, y0 + (h + bh) / 2), radius=gap * 0.3, fill=color + (255,))


def _timebar(d, x0, y, w, left, color, th):
    if left is None:
        return
    d.rounded_rectangle((x0, y, x0 + w, y + th), radius=th / 2, fill=(255, 255, 255, 30))
    d.rounded_rectangle((x0, y, x0 + max(th, w * max(0.0, min(1.0, left))), y + th), radius=th / 2, fill=color + (230,))


# ---------- 1. Capsule: a dark rounded pill, colored icon on the left, text on the right ----------

def capsule(kind, lines, frame, s, left):
    S = s * SS
    col = COL[kind]
    f1, f2 = font(int(17 * S), True), font(int(14 * S))
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    lines = [shape(x) for x in lines if x][:4]
    tw = max([_tw(probe, t, f1 if i == 0 else f2) for i, t in enumerate(lines)] + [0])
    ic, pad = 44 * S, 12 * S
    th = (24 * S + 20 * S * (len(lines) - 1)) if lines else 0
    w = int(pad + ic + (pad * 1.2 + tw if lines else 0) + pad * 1.4)
    h = int(max(ic + pad * 2, th + pad * 2 + (8 * S if left is not None else 0)))
    img = Image.new("RGBA", (w + int(24 * S), h + int(24 * S)), (0, 0, 0, 0))
    o = 12 * S
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))                     # soft shadow
    ImageDraw.Draw(sh).rounded_rectangle((o, o + 4 * S, o + w, o + h + 4 * S), radius=h / 2, fill=(0, 0, 0, 120))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8 * S)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((o, o, o + w, o + h), radius=min(h / 2, 30 * S), fill=BG + (232,), outline=(255, 255, 255, 34), width=int(1.2 * S))
    cx, cy, r = o + pad + ic / 2, o + h / 2, ic / 2
    if kind == "listen":
        rr = r + (5 + 3 * (frame % 2)) * S
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=col + (110 - 50 * (frame % 2),), width=int(2.5 * S))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (255,))
    glyph(d, kind, cx, cy, r * 0.82, frame=frame)
    x, y = o + pad + ic + pad * 1.2, o + (h - th - (8 * S if left is not None else 0)) / 2
    for i, t in enumerate(lines):
        d.text((x, y), t, font=f1 if i == 0 else f2, fill=INK if i == 0 else SOFT)
        y += 24 * S if i == 0 else 20 * S
    if left is not None:
        _timebar(d, x, o + h - pad - 4 * S, w - (x - o) - pad * 1.4, left, col, 4 * S)
    return _down(img)


# ---------- 2. Orb: only a glowing circle; a small label under it for questions and results ----------

def orb(kind, lines, frame, s, left):
    S = s * SS
    col = COL[kind]
    r = 30 * S
    lines = [shape(x) for x in lines if x][:4] if kind != "listen" else []
    f1, f2 = font(int(15 * S), True), font(int(13 * S))
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    tw = max([_tw(probe, t, f1 if i == 0 else f2) for i, t in enumerate(lines)] + [0])
    lw = tw + 24 * S if lines else 0
    lh = (22 * S + 19 * S * (len(lines) - 1) + 16 * S) if lines else 0
    w = int(max(r * 2 + 48 * S, lw + 16 * S))
    h = int(r * 2 + 48 * S + (lh + 8 * S if lines else 0))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cx, cy = w / 2, 24 * S + r
    pulse = (frame % 2) if kind in ("listen", "think") else 0
    _glow(img, (cx - r - 6 * S, cy - r - 6 * S, cx + r + 6 * S, cy + r + 6 * S), col, 12 * S, 170 + 50 * pulse)
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(18, 18, 22, 245), outline=col + (255,), width=int(3 * S))
    if kind == "listen":                                              # a ring that breathes
        rr = r + (8 + 4 * pulse) * S
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=col + (150 - 70 * pulse,), width=int(2 * S))
    glyph(d, kind, cx, cy, r * 0.8, color=col, frame=frame)
    if left is not None:                                              # time left on a question: an arc around the orb
        rr = r + 6 * S
        d.arc((cx - rr, cy - rr, cx + rr, cy + rr), -90, -90 + 360 * max(0.0, min(1.0, left)), fill=col + (255,), width=int(3 * S))
    if lines:
        x0, y0 = (w - lw) / 2, cy + r + 18 * S
        d.rounded_rectangle((x0, y0, x0 + lw, y0 + lh), radius=10 * S, fill=BG + (225,), outline=(255, 255, 255, 30), width=int(1 * S))
        y = y0 + 8 * S
        for i, t in enumerate(lines):
            f = f1 if i == 0 else f2
            d.text((w / 2, y), t, font=f, fill=INK if i == 0 else SOFT, anchor="ma")
            y += 22 * S if i == 0 else 19 * S
    return _down(img)


# ---------- 3. Wave: a slim bar with moving sound bars, like a voice chat app ----------

def wave(kind, lines, frame, s, left):
    S = s * SS
    col = COL[kind]
    lines = [shape(x) for x in lines if x][:4]
    f1, f2 = font(int(15 * S), True), font(int(13 * S))
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    title = lines[0] if lines else ""
    more = lines[1:]
    tw = max([_tw(probe, title, f1)] + [_tw(probe, t, f2) for t in more] + [0])
    bar_h = 46 * S
    wv = 96 * S if kind == "listen" else 0
    w = int(max(260 * S, 16 * S + 26 * S + 12 * S + tw + (wv + 14 * S if wv else 0) + 18 * S))
    h = int(bar_h + (len(more) * 20 * S + 10 * S if more else 0) + (6 * S if left is not None else 0))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=12 * S, fill=(10, 10, 13, 236), outline=(255, 255, 255, 26), width=int(1 * S))
    d.rounded_rectangle((0, 0, 5 * S, h - 1), radius=3 * S, fill=col + (255,))          # the colored edge
    cx, cy = 16 * S + 13 * S, bar_h / 2
    glyph(d, kind, cx, cy, 13 * S, color=col, frame=frame)
    tx = cx + 13 * S + 12 * S
    d.text((tx, cy), title, font=f1, fill=INK, anchor="lm")
    if wv:
        _wave(d, w - 18 * S - wv, cy - 13 * S, wv, 26 * S, col, frame, bars=12)
    y = bar_h - 4 * S
    for t in more:
        d.text((tx, y), t, font=f2, fill=SOFT)
        y += 20 * S
    if left is not None:
        _timebar(d, 10 * S, h - 7 * S, w - 20 * S, left, col, 3 * S)
    return _down(img)


# ---------- 4. Card: the FQPN look, a bigger card with a red header and numbered choices ----------

def card(kind, lines, frame, s, left):
    S = s * SS
    col = COL[kind]
    lines = [shape(x) for x in lines if x][:4]
    title, more = (lines[0] if lines else ""), lines[1:]
    f0, f1, f2, fn = font(int(11 * S), True), font(int(17 * S), True), font(int(14 * S)), font(int(14 * S), True)
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    tw = max([_tw(probe, title, f1)] + [_tw(probe, t, f2) + 30 * S for t in more] + [140 * S])
    head = 26 * S
    w = int(max(300 * S, 20 * S + 40 * S + 14 * S + tw + 20 * S))
    body = 64 * S + len(more) * 30 * S + (10 * S if left is not None else 0)
    h = int(head + body)
    img = Image.new("RGBA", (w + int(20 * S), h + int(20 * S)), (0, 0, 0, 0))
    o = 10 * S
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((o, o + 3 * S, o + w, o + h + 3 * S), radius=14 * S, fill=(0, 0, 0, 140))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7 * S)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((o, o, o + w, o + h), radius=14 * S, fill=(17, 17, 21, 242), outline=RED + (255,), width=int(1.5 * S))
    d.rounded_rectangle((o, o, o + w, o + head), radius=14 * S, fill=RED + (255,))
    d.rectangle((o, o + head - 14 * S, o + w, o + head), fill=RED + (255,))
    d.text((o + 14 * S, o + head / 2), "FQPN · VOICE", font=f0, fill=(255, 255, 255, 235), anchor="lm")
    dot = 4 * S                                                        # a live dot in the header
    if kind == "listen" and frame % 2 == 0:
        d.ellipse((o + w - 18 * S - dot, o + head / 2 - dot, o + w - 18 * S + dot, o + head / 2 + dot), fill=(255, 255, 255, 255))
    cx, cy, r = o + 20 * S + 20 * S, o + head + 32 * S, 20 * S
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (255,))
    glyph(d, kind, cx, cy, r * 0.82, frame=frame)
    tx = cx + r + 14 * S
    d.text((tx, cy), title, font=f1, fill=INK, anchor="lm")
    if kind == "listen":
        _wave(d, o + w - 20 * S - 70 * S, cy - 10 * S, 70 * S, 20 * S, col, frame, bars=9)
    y = o + head + 62 * S
    for t in more:
        m = re.match(r"^(\d)\.\s*(.*)$", t)
        if m:                                                          # a numbered choice: a chip with the number
            d.rounded_rectangle((tx, y, tx + 22 * S, y + 22 * S), radius=6 * S, fill=col + (255,))
            d.text((tx + 11 * S, y + 11 * S), m.group(1), font=fn, fill=(255, 255, 255, 255), anchor="mm")
            d.text((tx + 30 * S, y + 11 * S), m.group(2), font=f2, fill=INK, anchor="lm")
        else:
            d.text((tx, y + 11 * S), t, font=f2, fill=SOFT, anchor="lm")
        y += 30 * S
    if left is not None:
        _timebar(d, o + 14 * S, o + h - 12 * S, w - 28 * S, left, col, 4 * S)
    return _down(img)


def draw(style: str, kind: str, lines, frame: int = 0, scale: float = 1.0, left=None):
    fn = {"capsule": capsule, "orb": orb, "wave": wave, "card": card}.get(style, capsule)
    return fn(kind if kind in COL else "fail", list(lines or []), frame, scale, left)
