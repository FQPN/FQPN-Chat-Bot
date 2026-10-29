"""1.14.0: Dashboard > Stream stats. Counted in memory as chat happens and saved at most once a minute (light on the PC):
messages, chatters, commands used, Twitch emotes (with their picture id), follows / subs / gifts / Bits / raids, and who writes
in the chat for the first time ever ("new chatters"). Per day (31 days kept) and for the current (or last) stream.

Stored in the "chat_stats" section: {"seen": {login: [first_time, name]}, "days": {"YYYY-MM-DD": bucket}, "stream": bucket}
bucket = {"msgs": n, "chatters": {login: [name, n]}, "cmds": {name: n}, "emotes": {id: [name, n, animated]},
          "ev": {"follow": n, "subs": n, "bits": n, "raids": n}, "id": stream id, "since": time}"""
import time
from datetime import datetime, timedelta

DAYS = 31
SEEN_MAX = 100_000          # names remembered for "new chatters" (oldest first out)
SAVE_EVERY = 60
TOP = 5
EMOTE_URL = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/{fmt}/dark/2.0"


def _bucket():
    return {"msgs": 0, "chatters": {}, "cmds": {}, "emotes": {}, "ev": {"follow": 0, "subs": 0, "bits": 0, "raids": 0}}


def _day(ts=None):
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d")


class Stats:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        d = store.get("chat_stats") or {}
        self.data = {"seen": dict(d.get("seen") or {}), "days": dict(d.get("days") or {}), "stream": d.get("stream") or None}
        self.dirty, self.saved_at = False, clock()
        if not d.get("seen_ready"):
            self._seed_seen()

    def _seed_seen(self):
        """The first time: everyone in the activity log (up to 30 days) counts as already known, so regulars aren't "new"."""
        try:
            for x in self.store.activity.items():
                if x.get("user"):
                    self.data["seen"].setdefault(str(x["user"]).lower(), [0, str(x["user"])])
        except Exception:
            pass
        self.data["seen_ready"] = True
        self.dirty = True

    def _buckets(self, stream_id=None, since=None):
        days = self.data["days"]
        b = days.setdefault(_day(self.clock()), _bucket())
        out = [b]
        if stream_id:
            s = self.data.get("stream")
            if not s or s.get("id") != stream_id:
                s = self.data["stream"] = dict(_bucket(), id=stream_id, since=since or self.clock())
            out.append(s)
        return out

    def chat(self, login, name, emotes=(), stream_id=None, since=None):
        """Counts one message. Returns True when this is the person's first message ever (Greetings > Welcome)."""
        login = str(login or "").lower()
        if not login:
            return False
        now = self.clock()
        seen = self.data["seen"]
        first = login not in seen
        if first:
            seen[login] = [now, str(name or login)]
            if len(seen) > SEEN_MAX:
                for k in sorted(seen, key=lambda k: seen[k][0])[:len(seen) - SEEN_MAX]:
                    seen.pop(k, None)
        for b in self._buckets(stream_id, since):
            b["msgs"] += 1
            c = b["chatters"].setdefault(login, [str(name or login), 0])
            c[0], c[1] = str(name or login), c[1] + 1
            for eid, ename, animated in emotes:
                e = b["emotes"].setdefault(str(eid), [str(ename), 0, bool(animated)])
                e[1] += 1
        self.dirty = True
        return first

    def command(self, name, stream_id=None, since=None):
        for b in self._buckets(stream_id, since):
            b["cmds"][str(name)] = b["cmds"].get(str(name), 0) + 1
        last = self.data.setdefault("last", {})          # 1.14.0: Commands page: when each was last used
        last[str(name)] = self.clock()
        if len(last) > 2000:
            for k in sorted(last, key=last.get)[:len(last) - 2000]:
                last.pop(k, None)
        self.dirty = True

    def event(self, key, value=0, stream_id=None, since=None):
        k = {"follow": "follow", "subscription": "subs", "gift_sub": "subs", "bits": "bits", "raid": "raids"}.get(key)
        if not k:
            return
        n = int(value or 0) if k in ("bits",) else (max(1, int(value or 0)) if key == "gift_sub" else 1)
        for b in self._buckets(stream_id, since):
            b["ev"][k] = b["ev"].get(k, 0) + n
        self.dirty = True

    def flush(self, force=False):
        """Save (at most once a minute; force at shutdown). Old days are dropped."""
        if not self.dirty or (not force and self.clock() - self.saved_at < SAVE_EVERY):
            return False
        cut = _day(self.clock() - DAYS * 86400)
        self.data["days"] = {d: b for d, b in self.data["days"].items() if d > cut}
        self.store.save("chat_stats", self.data, allow_empty=True)
        self.dirty, self.saved_at = False, self.clock()
        return True


def commands_usage(data, now=None):
    """1.14.0 Commands page: {name: [uses in the last 30 days, when last used (or 0)]}."""
    now = now or time.time()
    data = data or {}
    cut = _day(now - 29 * 86400)
    out = {}
    for d, b in (data.get("days") or {}).items():
        if d >= cut:
            for k, c in (b.get("cmds") or {}).items():
                out.setdefault(k, [0, 0])[0] += int(c or 0)
    for k, ts in (data.get("last") or {}).items():
        out.setdefault(k, [0, 0])[1] = ts
    return out


def view(data, rng="stream", now=None, live=False):
    """What the Dashboard shows for "stream" (this or the last stream), "7" or "30" days."""
    now = now or time.time()
    data = data or {}
    if rng == "stream":
        s = data.get("stream")
        parts, since = ([s] if s else []), (s or {}).get("since") or now
    else:
        n = 7 if str(rng) == "7" else 30
        cut = _day(now - (n - 1) * 86400)
        parts = [b for d, b in (data.get("days") or {}).items() if d >= cut]
        since = now - n * 86400
    tot = _bucket()
    for b in parts:
        tot["msgs"] += int(b.get("msgs") or 0)
        for k, (nm, c) in (b.get("chatters") or {}).items():
            t = tot["chatters"].setdefault(k, [nm, 0]); t[1] += c
        for k, c in (b.get("cmds") or {}).items():
            tot["cmds"][k] = tot["cmds"].get(k, 0) + c
        for k, v in (b.get("emotes") or {}).items():
            t = tot["emotes"].setdefault(k, [v[0], 0, bool(v[2] if len(v) > 2 else False)]); t[1] += v[1]
        for k, c in (b.get("ev") or {}).items():
            tot["ev"][k] = tot["ev"].get(k, 0) + int(c or 0)
    new = sorted(((v[0], v[1]) for k, v in (data.get("seen") or {}).items() if v[0] and v[0] >= since), reverse=True)
    top = lambda d: sorted(d.items(), key=lambda kv: -kv[1])[:TOP]
    return {"range": rng, "live": bool(live), "since": since if rng == "stream" and parts else None,
            "messages": tot["msgs"], "chatters": len(tot["chatters"]), "new_chatters": len(new),
            "commands": sum(tot["cmds"].values()), "follows": tot["ev"].get("follow", 0), "subs": tot["ev"].get("subs", 0),
            "bits": tot["ev"].get("bits", 0), "raids": tot["ev"].get("raids", 0),
            "top_commands": [{"name": k, "n": c} for k, c in top(tot["cmds"])],
            "top_chatters": [{"name": v[0], "n": v[1]} for k, v in sorted(tot["chatters"].items(), key=lambda kv: -kv[1][1])[:TOP]],
            "top_emotes": [{"id": k, "name": v[0], "n": v[1], "animated": v[2],
                            "img": EMOTE_URL.format(id=k, fmt="static"), "gif": EMOTE_URL.format(id=k, fmt="animated") if v[2] else ""}
                           for k, v in sorted(tot["emotes"].items(), key=lambda kv: -kv[1][1])[:TOP]],
            "new_list": [{"name": nm, "at": at} for at, nm in new[:TOP]]}
