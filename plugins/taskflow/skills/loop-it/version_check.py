#!/usr/bin/env python3
"""Compare the taskflow version a Loop loaded with the installed one.

Usage: version_check.py <skill dir>
Prints `ok <v>`, `restart <loaded> <installed>` or `unknown`. Always exits 0.
"""
import json
import re
import sys
from pathlib import Path


def loaded_version(skill_dir):
    parts = Path(str(skill_dir).replace("\\", "/")).parts
    for i, p in enumerate(parts[:-1]):
        if p == "taskflow" and re.fullmatch(r"\d+(\.\d+)*", parts[i + 1]):
            return parts[i + 1]
    return None


def installed_version():
    try:
        path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        v = data["plugins"]["taskflow@skillz"][0]["version"]
        return v if re.fullmatch(r"\d+(\.\d+)*", str(v)) else None
    except Exception:
        return None


def key(v):
    return tuple(int(x) for x in v.split("."))


def check(skill_dir):
    loaded = loaded_version(skill_dir)
    installed = installed_version()
    if loaded is None or installed is None:
        return "unknown"
    if key(installed) > key(loaded):
        return "restart %s %s" % (loaded, installed)
    return "ok %s" % loaded


if __name__ == "__main__":
    try:
        print(check(sys.argv[1] if len(sys.argv) > 1 else ""))
    except Exception:
        print("unknown")
    sys.exit(0)
