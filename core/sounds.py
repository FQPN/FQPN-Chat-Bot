"""1.17.0: the little sounds of voice commands and hotkeys, made here (no sound files to ship).

Soft and short, about a fifth of full volume (the old Windows beep was a loud square tone):
  heard - a quick rising "bloop": it heard you and is working it out
  ok    - a two-note chime with a small sparkle on top: done
  fail  - a soft falling "bwomp": it didn't work
Each note is a sine with a couple of quiet overtones (a bell-like sound), a second voice slightly out of tune with it
(a soft chorus), a fast fade-in and a smooth fade-out, so nothing clicks.
"""
import io
import math
import struct
import wave

RATE = 22050
VOLUME = 0.2          # of full scale

# (start s, frequency Hz, length s, loudness, glide to Hz or None, overtones)
BELL = ((1, 1.0), (2, 0.22), (3, 0.06))
SOFT = ((1, 1.0), (2, 0.12))
SOUNDS = {
    "heard": [(0.0, 740, 0.11, 0.75, 1110, SOFT)],
    "ok": [(0.0, 1046.5, 0.28, 0.7, None, BELL), (0.075, 1568.0, 0.42, 0.8, None, BELL), (0.15, 2637.0, 0.26, 0.18, None, SOFT)],
    "fail": [(0.0, 392.0, 0.17, 0.8, 370, SOFT), (0.1, 293.7, 0.26, 0.85, 262, SOFT)],
}
_cache = {}


def _render(notes) -> list:
    end = max(s + d for s, _, d, *_ in notes) + 0.02
    out = [0.0] * int(end * RATE)
    for start, f0, dur, amp, f1, partials in notes:
        n0, n = int(start * RATE), int(dur * RATE)
        for voice, detune, vamp in ((0, 1.0, 1.0), (1, 1.0035, 0.45)):
            phase = 0.0
            for i in range(n):
                t = i / RATE
                f = (f0 + (f1 - f0) * min(1.0, t / (dur * 0.6))) if f1 else f0
                phase += 2 * math.pi * f * detune / RATE
                env = min(1.0, t / 0.006) * math.exp(-t / (dur * 0.32)) * min(1.0, (dur - t) / 0.03)
                v = sum(a * math.sin(phase * k) for k, a in partials)
                out[n0 + i] += v * env * amp * vamp
    peak = max(1e-9, max(abs(x) for x in out))
    return [x / peak * VOLUME for x in out]


def wav(kind: str) -> bytes:
    """The sound as a WAV file (made once, then kept)."""
    if kind not in SOUNDS:
        kind = "ok"
    if kind not in _cache:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x)) * 32767)) for x in _render(SOUNDS[kind])))
        _cache[kind] = buf.getvalue()
    return _cache[kind]


def play(kind: str) -> None:
    """Plays it on Windows (and waits until it ends: call it from its own thread). Elsewhere: nothing."""
    try:
        import winsound
    except ImportError:
        return
    try:
        winsound.PlaySound(wav(kind), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except Exception:
        pass
