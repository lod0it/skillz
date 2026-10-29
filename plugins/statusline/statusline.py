#!/usr/bin/env python3
"""Claude Code status line command: prints one short line and saves the limits.

Claude Code runs it after each answer and pipes a JSON document on stdin. When
`rate_limits` is there, the latest values are written (atomically) to
<CLAUDE_CONFIG_DIR or ~/.claude>/statusline/rate_limits.json. Never raises.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path


def config_dir():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def limits_path():
    return config_dir() / "statusline" / "rate_limits.json"


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_window(w):
    """-> {"used_percentage": n, "resets_at": n} or None."""
    if not isinstance(w, dict) or not _num(w.get("used_percentage")) \
            or not _num(w.get("resets_at")):
        return None
    return {"used_percentage": w["used_percentage"], "resets_at": w["resets_at"]}


def parse_limits(doc):
    """-> (five_hour, seven_day) windows, either may be None."""
    rl = doc.get("rate_limits") if isinstance(doc, dict) else None
    if not isinstance(rl, dict):
        return None, None
    return parse_window(rl.get("five_hour")), parse_window(rl.get("seven_day"))


def parse_context(doc):
    """-> the used share of the context window in percent, or None."""
    cw = doc.get("context_window") if isinstance(doc, dict) else None
    if not isinstance(cw, dict):
        return None
    if _num(cw.get("used_percentage")):
        return cw["used_percentage"]
    usage, size = cw.get("current_usage"), cw.get("context_window_size")
    if not isinstance(usage, dict) or not _num(size) or size <= 0:
        return None
    used = sum(usage[k] for k in ("input_tokens", "cache_creation_input_tokens",
                                  "cache_read_input_tokens") if _num(usage.get(k)))
    return used * 100 / size


def color(pct):
    """-> the SGR prefix for the rounded percentage ("" under NO_COLOR)."""
    if os.environ.get("NO_COLOR"):
        return ""
    n = round(pct)
    return "[1;32m" if n < 60 else "[1;33m" if n <= 85 else "[1;31m"


def paint(pct):
    """-> "N%" with the traffic-light color on it."""
    c = color(pct)
    return f"{c}{round(pct)}%[0m" if c else f"{round(pct)}%"


def countdown(resets_at, now):
    """-> time left to resets_at: "Nm", "Hh Mm" or "Dd Hh"."""
    minutes = int(max(0, resets_at - now) // 60)
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 24 * 60:
        return f"{minutes // 60}h {minutes % 60}m"
    return f"{minutes // 1440}d {minutes % 1440 // 60}h"


def _segment(label, w, now):
    try:
        left = countdown(w["resets_at"], now)
    except (OverflowError, ValueError):
        left = "?"
    return f"{label} {paint(w['used_percentage'])} ⟳ {left}"


def _text(v):
    return v if isinstance(v, str) else ""


def format_line(doc, now=None):
    now = time.time() if now is None else now
    doc = doc if isinstance(doc, dict) else {}
    model = doc.get("model")
    name = _text(model.get("display_name")) if isinstance(model, dict) else _text(model)
    ws = doc.get("workspace")
    cwd = _text(ws.get("current_dir")) if isinstance(ws, dict) else ""
    cwd = cwd or _text(doc.get("cwd"))
    folder = os.path.basename(cwd.replace("\\", "/").rstrip("/"))
    head = " · ".join(x for x in (name, folder) if x)
    five, seven = parse_limits(doc)
    ctx = parse_context(doc)
    parts = [head] if head else []
    if ctx is not None:
        parts.append(f"ctx {paint(ctx)}")
    if five:
        parts.append(_segment("session", five, now))
    if seven:
        parts.append(_segment("week", seven, now))
    return " │ ".join(parts) or "claude"


def write_limits(doc, five, seven, now=None):
    sid = doc.get("session_id")
    data = {"schema": 1, "updated_at": int(now if now is not None else time.time()),
            "session_id": sid if isinstance(sid, str) else None,
            "five_hour": five, "seven_day": seven}
    path = limits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".rate_limits-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run(raw):
    """-> the line to print; saves the limits when both windows are present."""
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError):
        return "claude"
    if not isinstance(doc, dict):
        return "claude"
    try:
        five, seven = parse_limits(doc)
        if five and seven:
            write_limits(doc, five, seven)
    except Exception:
        pass
    try:
        return format_line(doc)
    except Exception:
        return "claude"


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        line = run(raw)
    except Exception:
        line = "claude"
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
