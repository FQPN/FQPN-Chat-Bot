"""1.19.0: writes the Releases-page notes for one version from the app's own What's new (core/dashboard.html, var WN).

The page shows the English and Arabic lines for people; the app's update pop-up reads the hidden line at the end
(the same lines as JSON, in base64) so it can show What's new in the user's own language before they update.
Usage (the release workflow):  python tools/release_notes.py 1.19.0 > release_notes.md"""

import base64
import json
import re
import sys
from pathlib import Path


def entry(version: str, html: str) -> dict | None:
    m = re.search(r"^var WN=(\[.*?\]);\s*$", html, re.M)
    if not m:
        return None
    try:
        items = json.loads(m.group(1))
    except ValueError:
        return None
    for e in items:
        if str(e.get("v")) == version:
            return e
    return None


def _ar_md(x: str) -> str:
    """1.20.0: the Releases page has no <bdi>, so each !command or $(variable) in an Arabic line gets a left-to-right mark
    on both sides (otherwise the "!" jumps to the wrong end). The app's own pop-up reads the base64 line and does this itself."""
    x = re.sub(r"[\u2066-\u2069\u200e\u200f]", "", x)
    return re.sub(r"(\$\([^)]*\)|![^\s،,.()؛<«»]+)", "\u200e\\1\u200e", x)


def notes(version: str, html: str) -> str:
    e = entry(version, html)
    if not e:
        return f"FQPN's Chat Bot {version}\n"
    en, ar = [str(x) for x in e.get("en") or []], [str(x) for x in e.get("ar") or []]
    blob = base64.b64encode(json.dumps({"v": version, "en": en, "ar": ar}, ensure_ascii=False).encode("utf-8")).decode("ascii")
    out = [f"## What's new in {version}", ""] + [f"- {x}" for x in en] + ["", "## ما الجديد", ""] + [f"- {_ar_md(x)}" for x in ar]
    out += ["", f"<!-- fqpn-whatsnew:{blob} -->", ""]
    return "\n".join(out)


if __name__ == "__main__":
    ver = (sys.argv[1] if len(sys.argv) > 1 else "").lstrip("v")
    html = (Path(__file__).resolve().parent.parent / "core" / "dashboard.html").read_text(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(notes(ver, html))
