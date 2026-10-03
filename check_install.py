"""Checks that the update was copied in correctly and tells you, in plain words, what is wrong.

Run it inside your TwitchBot folder (the one that contains main.py and the core folder):
    python check_install.py
It only reads files; it changes nothing."""

import importlib
import py_compile
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
problems, notes = [], []

REQUIRED = ["main.py", "launcher.py", "core/__init__.py", "core/auth.py", "core/bot.py", "core/dashboard.py",
            "core/dashboard.html", "core/store.py", "core/manage.py", "core/variables.py", "core/greetings.py",
            "core/events.py", "core/version.py", "core/activity.py", "core/notify.py", "core/desktop.py", "core/updater.py"]

# a phrase that only the NEW version of each file contains
NEW_IN = {
    "main.py": ["open_browser", "updater.loop", "apply_launch_defaults"],
    "core/store.py": ["ActivityLog", '"prefs"', "apply_launch_defaults"],
    "core/bot.py": ["store.activity", "notify.event", "_log_chat"],
    "core/dashboard.py": ['"prefs"', "updater", "/api/update/check"],
    "core/dashboard.html": ["data-pref", "spane-app", "updbtn"],
}


def ok(text):
    print("  OK       " + text)


def bad(text, fix):
    problems.append((text, fix))
    print("  PROBLEM  " + text)


print(f"Checking: {ROOT}\n")

# 1. the right folder?
if not (ROOT / "core" / "auth.py").exists():
    bad("This folder has no core/auth.py, so it is not your TwitchBot project (it may be the unzipped update pack).",
        "Run this file from your real TwitchBot folder, and copy the pack's files INTO that folder.")

# 2. every file present
missing = [f for f in REQUIRED if not (ROOT / f).exists()]
if missing:
    bad("Missing files: " + ", ".join(missing), "Copy them from the update pack into the same place in TwitchBot.")
else:
    ok("all the program files are there")

# 3. no typos or half-pasted code
broken = []
for f in REQUIRED:
    p = ROOT / f
    if p.suffix == ".py" and p.exists():
        try:
            py_compile.compile(str(p), cfile=str(Path(tempfile.gettempdir()) / "check_install.pyc"), doraise=True)
        except py_compile.PyCompileError as e:
            broken.append(f"{f}: {str(e).strip().splitlines()[-1]}")
if broken:
    bad("Code errors: " + " | ".join(broken), "Copy that file again from the update pack instead of pasting parts of it.")
elif not missing:
    ok("every Python file is readable")

# 4. old and new files mixed together
old = []
for f, phrases in NEW_IN.items():
    p = ROOT / f
    if p.exists():
        text = p.read_text(encoding="utf-8", errors="replace")
        if not all(x in text for x in phrases):
            old.append(f)
if old:
    bad("These files are still the OLD version: " + ", ".join(old),
        "Replace them with the ones from the update pack. The new files only work together.")
elif not missing:
    ok("main.py, store, bot, dashboard and the page are all the new version")
launcher = ROOT / "launcher.py"
if launcher.exists() and "class Shell" not in launcher.read_text(encoding="utf-8", errors="replace"):
    notes.append("launcher.py is the old one. The bot still runs, but the tray icon and close-to-tray need the new launcher.py.")

# 5. libraries
for name, needed, pip in [("aiohttp", True, "aiohttp"), ("twitchio", True, "twitchio"),
                          ("webview", False, "pywebview"), ("pystray", False, "pystray"), ("PIL", False, "Pillow")]:
    try:
        importlib.import_module(name)
        ok(f"library {pip} is installed")
    except Exception:
        if needed:
            bad(f"The library {pip} is not installed in this Python.", "Run:  pip install -r requirements.txt   (with your venv active)")
        else:
            notes.append(f"{pip} is not installed. Only needed for the app window and tray icon: pip install -r requirements.txt")

# 6. can the program actually load?
if not problems:
    sys.path.insert(0, str(ROOT))
    for mod in ["core.version", "core.activity", "core.notify", "core.desktop", "core.updater", "core.store",
                "core.auth", "core.events", "core.bot", "core.dashboard"]:
        try:
            importlib.import_module(mod)
        except Exception as e:
            bad(f"{mod} could not load: {e.__class__.__name__}: {e}", "Send me this line.")
            break
    else:
        ok("the program loads")

print()
for n in notes:
    print("  note     " + n)
if problems:
    print("\nWhat to do:")
    for i, (_, fix) in enumerate(problems, 1):
        print(f"  {i}. {fix}")
    print("\nIf it still fails, copy everything this program printed and send it to me.")
else:
    try:
        from core import version
        print(f"All good. App version {version.VERSION}. Start it with:  python main.py")
    except Exception:
        print("All good. Start it with:  python main.py")
