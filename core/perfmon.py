"""1.14.0: a light health log, to find what makes a PC slow. Once a minute one line in perf.log (the data folder, in AppData):
CPU and memory of the app and of its window (the WebView2 / Edge processes it starts), thread count, background tasks, and how
long the bot's event loop takes to answer (a high number = something blocks it). About 1 MB at most (2 old files kept).

    2026-10-28 21:04:00 app cpu 1.2% ram 118 MB threads 19 | window cpu 0.4% ram 310 MB (6 processes) | tasks 31 | loop 2 ms

Uses psutil when it is installed; without it, threads, tasks and the loop delay are still logged."""
import asyncio
import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler

EVERY = 60
LOOP = None                 # set by main.main(): the bot's event loop (for the tasks count and the delay)
_log = logging.getLogger("fqpn.perf")


def _loop_info():
    loop = LOOP
    if loop is None or loop.is_closed():
        return "tasks - | loop -"
    done = threading.Event()
    t0 = time.perf_counter()
    try:
        loop.call_soon_threadsafe(done.set)
    except RuntimeError:
        return "tasks - | loop -"
    answered = done.wait(10)
    delay = (time.perf_counter() - t0) * 1000
    try:
        n = len(asyncio.all_tasks(loop))
    except RuntimeError:
        n = "?"
    return f"tasks {n} | loop {delay:.0f} ms" if answered else f"tasks {n} | loop BLOCKED over 10 s"


def _line(me, psutil):
    if psutil is None:
        return f"app threads {threading.active_count()} (psutil not installed: no CPU / RAM) | {_loop_info()}"
    kids = []
    try:
        kids = me.children(recursive=True)
    except Exception:
        pass
    def cpu_ram(procs):
        cpu = ram = 0.0
        alive = 0
        for p in procs:
            try:
                cpu += p.cpu_percent(None)
                ram += p.memory_info().rss
                alive += 1
            except Exception:
                pass
        return cpu / max(1, psutil.cpu_count() or 1), ram / 1048576, alive
    c, r, _ = cpu_ram([me])
    kc, kr, kn = cpu_ram(kids)
    try:
        th = me.num_threads()
    except Exception:
        th = threading.active_count()
    return (f"app cpu {c:.1f}% ram {r:.0f} MB threads {th} | window cpu {kc:.1f}% ram {kr:.0f} MB ({kn} processes) | "
            f"{_loop_info()}")


def _run(home):
    try:
        import psutil
    except Exception:
        psutil = None
    me = psutil.Process(os.getpid()) if psutil else None
    if me is not None:                       # the first cpu_percent() call only starts the count
        try:
            me.cpu_percent(None)
            for p in me.children(recursive=True):
                p.cpu_percent(None)
        except Exception:
            pass
    while True:
        time.sleep(EVERY)
        try:
            if me is not None:
                for p in me.children(recursive=True):     # new window processes: start their count (next minute shows them)
                    try:
                        p.cpu_percent(None)
                    except Exception:
                        pass
            _log.info(_line(me, psutil))
        except Exception as e:                # never let the health log disturb the app
            _log.info("could not measure: %s", str(e)[:200])


def start(home) -> None:
    """Start the once-a-minute health log (a background thread that sleeps between lines)."""
    if _log.handlers:
        return
    try:
        h = RotatingFileHandler(os.path.join(str(home), "perf.log"), maxBytes=400_000, backupCount=2, encoding="utf-8")
    except OSError:
        return
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    _log.addHandler(h)
    _log.setLevel(logging.INFO)
    _log.propagate = False                   # not in bot.log
    _log.info("started (one line a minute)")
    threading.Thread(target=_run, args=(home,), daemon=True, name="perf-log").start()
