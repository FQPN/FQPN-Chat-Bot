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
            "core/events.py", "core/version.py", "core/activity.py", "core/notify.py", "core/desktop.py", "core/updater.py", "core/botauth.py", "core/donations.py", "core/watchdog.py", "core/stream.py", "core/publiclist.py", "core/usage.py"]

# a phrase that only the NEW version of each file contains
NEW_IN = {
    "main.py": ["open_browser", "updater.loop", "apply_launch_defaults", "python launcher.py", "botauth", "donations", "watchdog", "publiclist.Syncer", "usage.Reporter"],
    "launcher.py": ["min_size=(1000, 650)", "class Shell", "ensure_single_instance", "fail_no_window", "edgechromium", "read_port", "fail_no_dashboard"],
    "core/store.py": ["ActivityLog", '"prefs"', "apply_launch_defaults", "disabled_builtins", "separate_bot", "donation", "tourDone", "gsDone", "stream_state", "public_hidden", "publist_state"],
    "core/bot.py": ["store.activity", "notify.event", "_log_chat", "disabled_builtins", "BY_TYPED", "bot_account", "send_test", "on_donation", "live_fail", "StreamSession", "event_stream_online", "_find_game", "SEARCH_URL", "developer_messages"],
    "core/donations.py": ["class DonationManager", "parse_streamelements", "CryptProtectData"],
    "core/events.py": ["DECIMAL", "donation"],
    "core/notify.py": ["donation"],
    "core/botauth.py": ["def is_moderator", "bot_token.json"],
    "core/stream.py": ["class StreamSession", "DEFAULT_TEXT", "STALE"],
    "core/watchdog.py": ["class Watchdog", "channel.chat.message", "MAX_RESTARTS"],
    "core/manage.py": ["BUILTIN_NAMES", "BY_TYPED", "ACTION_BY_TARGET", "def effective_permission"],
    "core/usage.py": ["class Reporter", "def payload"],
    "core/greetings.py": ["DEVELOPERS", "def developer_messages"],
    "core/updater.py": ["NUDGE_GAP", "If-None-Match", "def nudge"],
    "core/publiclist.py": ["class Syncer", "SITE =", "def build", "effective_permission"],
    "core/dashboard.py": ['"prefs"', "updater", "/api/update/check", "/api/show", "disabled_builtins", "bind_first_free", "/api/botaccount/connect", "restart_bot", "/api/donations/", "tourDone", "gsDone", "/api/restart", "health_info", "The stream messages are invalid", "publist_info", "/api/publist/sync", "unknown reply type", "/api/update/nudge"],
    "core/updater.py": ["def announce"],
    "core/desktop.py": ["quit_app", "show_window"],
    "core/dashboard.html": ["data-pref", "spane-app", "updbtn", "toggleBuiltin", "transform-origin:15px 7px", 'class="sep"', "BNAME", "upop_title", "bac-cards", "botBanner", "dcards", "navActive", "ngrp", "startTour", "tourBtn", "v-greetings", "v-botaccount", "v-donations", "renderAccountMenu", "healthBanner", "renderStream", "renderPublist", "plmodal", "st_msg_on", "applyType", "mtype", "nudgeUpdate", "tr20_t", "usenote", "stmaster"],
}

# a phrase that only the OLD version of a file contains (so it must NOT be there)
OLD_IN = {"core/dashboard.html": ["animation:tick", "transform-origin:0.75rem"],
          "launcher.py": ["webbrowser", "wait_for_port"], "main.py": ["webbrowser"]}   # the browser must not be used any more

# files that belong in the TwitchBot folder (next to main.py) and files that belong inside core
ROOT_FILES = ["launcher.py", "main.py", "check_install.py", "installer.iss", "requirements.txt", "README.md", "CHANGELOG.md",
              "RELEASING.md", "TwitchChatBot.spec", "icon.ico", "run.bat", "update.bat", "build.bat"]
CORE_FILES = ["auth.py", "bot.py", "dashboard.py", "dashboard.html", "store.py", "manage.py", "variables.py", "greetings.py",
              "events.py", "version.py", "activity.py", "notify.py", "desktop.py", "updater.py"]


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

# 3a. files put in the wrong folder (the usual cause of "No module named 'core'")
misplaced = [f"core/{n}  ->  should be in the TwitchBot folder, next to main.py" for n in ROOT_FILES if (ROOT / "core" / n).exists()]
misplaced += [f"{n}  ->  should be inside the core folder" for n in CORE_FILES if (ROOT / n).exists()]
if (ROOT / "core" / "core").exists():
    misplaced.append("core/core  ->  a folder inside a folder: its files belong one level up, inside core")
if misplaced:
    bad("Files in the wrong place:\n               " + "\n               ".join(misplaced),
        "Drag each one to where it belongs and choose Replace. Unzip updates into the TwitchBot folder itself, never into core.")
else:
    ok("no file is in the wrong folder")

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
        if not all(x in text for x in phrases) or any(x in text for x in OLD_IN.get(f, [])):
            old.append(f)
if old:
    bad("These files are still the OLD version: " + ", ".join(old),
        "Replace them with the ones from the update pack. The new files only work together.")
elif not missing:
    ok("main.py, launcher, store, bot, dashboard and the page are all the new version")

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
