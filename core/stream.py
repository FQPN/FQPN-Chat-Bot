"""Stream messages: the bot says something in chat when your stream starts, when it comes back after a drop, and when it ends,
plus how many new followers you got since the last stream. Everything is off until you switch it on (Events > Stream).

The live check (every minute or so) feeds this. It keeps a small "session" so that a dropped connection is not announced as
the end of the stream, a stream that comes back soon continues the same session (the uptime keeps adding up), and an app that
is opened in the middle of a stream does not announce a start that happened hours ago."""

import asyncio
import json
import logging
import time

log = logging.getLogger("stream")

KINDS = ("start", "followers", "resume", "end")
FRESH = 300            # a stream that went live less than this many seconds ago is announced; an older one is just tracked
STALE = 600            # a session left over from an app that was closed longer ago than this is forgotten silently
GAP = 2                # seconds between two messages sent one after the other

DEFAULT_TEXT = {
    "en": {
        "start": "\u2705 LIVE ONLINE under the category $(category), the uptime begins.",
        "followers": "\u270c\ufe0f Total of follows since last session: $(newfollowers) new followers.",
        "resume": "\u2705 LIVE is BACK, the uptime of the session continues.",
        "end": "\u274c LIVE OFFLINE, uptime of the session is $(uptime).",
    },
    "ar": {
        "start": "\u2705 \u0628\u062f\u0623 \u0627\u0644\u0628\u062b \u0627\u0644\u0622\u0646 \u0641\u064a \u0641\u0626\u0629 $(category)\u060c \u0648\u0627\u0644\u0645\u062f\u0629 \u062a\u0628\u062f\u0623.",
        "followers": "\u270c\ufe0f \u0639\u062f\u062f \u0627\u0644\u0645\u062a\u0627\u0628\u0639\u064a\u0646 \u0627\u0644\u062c\u062f\u062f \u0645\u0646\u0630 \u0622\u062e\u0631 \u0628\u062b: $(newfollowers).",
        "resume": "\u2705 \u0639\u0627\u062f \u0627\u0644\u0628\u062b\u060c \u0648\u0627\u0644\u0645\u062f\u0629 \u062a\u0633\u062a\u0645\u0631.",
        "end": "\u274c \u0627\u0646\u062a\u0647\u0649 \u0627\u0644\u0628\u062b\u060c \u0645\u062f\u0629 \u0627\u0644\u0628\u062b $(uptime).",
    },
}
VARIABLES = ("channel", "category", "title", "uptime", "newfollowers")

STATE_DEFAULT = {"state": "idle", "seg_start": None, "live_seconds": 0.0, "offline_since": None, "ended_at": None,
                 "last_seen": 0.0, "end_total": None, "title": "", "category": ""}


def duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s" if m else f"{s}s"


def language(store) -> str:
    lang = (store.get("ui") or {}).get("language", "en")
    return lang if lang in DEFAULT_TEXT else "en"


def text_for(store, kind: str) -> str:
    """The message to send: your own text, or the default in the app's language when the box was left on its default."""
    mine = str(((store.get("stream") or {}).get(kind) or {}).get("text") or "").strip()
    return mine or DEFAULT_TEXT[language(store)][kind]


def render(text: str, ctx: dict) -> str:
    for name in VARIABLES:
        text = text.replace(f"$({name})", str(ctx.get(name, "")))
    return text


class StreamSession:
    def __init__(self, store, send, followers, channel: str, paused, log_event=None, clock=time.time, sleep=asyncio.sleep):
        self.store, self.send, self.followers, self.channel, self.paused = store, send, followers, channel, paused
        self.log_event, self.clock, self.sleep = log_event, clock, sleep
        saved = store.get("stream_state") or {}
        self.s = {**STATE_DEFAULT, **{k: saved[k] for k in STATE_DEFAULT if k in saved}}
        self._first = True

    # ------------------------------------------------------------------ the one entry point
    async def step(self, live: bool, info: dict | None = None) -> None:
        """Called after every live check. info: started_at (epoch seconds), title, category."""
        info, now, s = info or {}, self.clock(), self.s
        cfg = self.store.get("stream") or {}
        end_after = max(1, int(cfg.get("end_after_minutes", 2))) * 60
        resume_within = max(1, int(cfg.get("resume_within_minutes", 15))) * 60
        if self._first:
            self._first = False
            if s["state"] in ("live", "gap") and now - float(s["last_seen"] or 0) > STALE:
                self._reset()          # the app was closed for a long time: that session is over, and nothing is announced late
        s["last_seen"] = now
        if live:
            s["title"] = info.get("title") or s["title"]
            s["category"] = info.get("category") or s["category"]
        state = s["state"]
        if state == "idle":
            if live:
                await self._begin(info, now)
        elif state == "live":
            if not live:
                s["state"], s["offline_since"] = "gap", now
        elif state == "gap":
            if live:
                s["state"], s["offline_since"] = "live", None            # a short drop is not the end of the stream
            elif now - float(s["offline_since"]) >= end_after:
                await self._finish()
        elif state == "ended":
            if live:
                if now - float(s["ended_at"]) <= resume_within:
                    await self._resume(info, now)
                else:
                    self._reset()
                    await self._begin(info, now)
        self._save()

    # ------------------------------------------------------------------ the three moments
    async def _begin(self, info: dict, now: float) -> None:
        s = self.s
        started = float(info.get("started_at") or now)
        interval = int((self.store.get("settings") or {}).get("live_check_seconds", 60))
        fresh = (now - started) <= max(FRESH, interval * 2)
        s.update(state="live", seg_start=started, live_seconds=0.0, offline_since=None, ended_at=None)
        if not fresh:
            return                      # the app was opened in the middle of a stream: track it, announce nothing
        total = await self._total()
        await self._say("start", info)
        previous = s.get("end_total")
        if total is not None and previous is not None and total - previous > 0:
            await self.sleep(GAP)
            await self._say("followers", info, newfollowers=total - previous)

    async def _finish(self) -> None:
        s = self.s
        s["live_seconds"] = float(s["live_seconds"]) + max(0.0, float(s["offline_since"]) - float(s["seg_start"] or s["offline_since"]))
        s["ended_at"], s["state"] = float(s["offline_since"]), "ended"
        await self._say("end", {}, uptime=duration(s["live_seconds"]))
        s["end_total"] = await self._total()

    async def _resume(self, info: dict, now: float) -> None:
        s = self.s
        s.update(state="live", seg_start=float(info.get("started_at") or now), offline_since=None)
        await self._say("resume", info)

    # ------------------------------------------------------------------ helpers
    def _reset(self) -> None:
        keep = self.s.get("end_total")
        self.s.update({**STATE_DEFAULT, "end_total": keep})

    def _save(self) -> None:
        try:
            self.store.save("stream_state", self.s)
        except Exception:
            log.exception("Could not save the stream session")

    async def _total(self):
        try:
            total = await self.followers()
            return int(total) if total is not None else None
        except Exception:
            log.exception("Could not read your follower total")
            return None

    async def _say(self, kind: str, info: dict, **extra) -> None:
        if self.paused():
            return                      # the bot is paused: it says nothing (the session is still tracked)
        cfg = self.store.get("stream") or {}
        if cfg.get("enabled", True) is False:
            return                      # all stream messages switched off (the session is still tracked, so uptime stays right)
        c = cfg.get(kind) or {}
        if not c.get("enabled"):
            return
        ctx = {"channel": self.channel, "category": info.get("category") or self.s["category"] or "-",
               "title": info.get("title") or self.s["title"] or "", "uptime": duration(self.s["live_seconds"]), **extra}
        try:
            await self.send(render(text_for(self.store, kind), ctx))
            if self.log_event:
                self.log_event(kind)
        except Exception:
            log.exception("Could not send the %s stream message", kind)
