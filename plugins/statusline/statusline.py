#!/usr/bin/env python3
"""Claude Code status line command, with 24 switchable styles.

Without arguments: Claude Code pipes a JSON document on stdin; this prints the
status line (one or more lines) and saves the latest limits (atomically) to
<CLAUDE_CONFIG_DIR or ~/.claude>/statusline/rate_limits.json. Never raises.

With arguments: `statusline style ...` lists, previews and switches the style.
"""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import statusline_config as cfg
import statusline_styles as styles

WINDOW = {"ses": 5 * 3600, "wk": 7 * 86400}
HISTORY_LEN = 8


def config_dir():
    return cfg.config_dir()


def limits_path():
    return config_dir() / "statusline" / "rate_limits.json"


def history_path():
    return config_dir() / "statusline" / "history.json"


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
    return "\x1b[1;32m" if n < 60 else "\x1b[1;33m" if n <= 85 else "\x1b[1;31m"


def paint(pct):
    """-> "N%" with the traffic-light color on it."""
    c = color(pct)
    return f"{c}{round(pct)}%\x1b[0m" if c else f"{round(pct)}%"


def countdown(resets_at, now):
    """-> time left to resets_at: "Nm", "Hh Mm" or "Dd Hh"."""
    minutes = int(max(0, resets_at - now) // 60)
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 24 * 60:
        return f"{minutes // 60}h {minutes % 60}m"
    return f"{minutes // 1440}d {minutes % 1440 // 60}h"


def _text(v):
    return v if isinstance(v, str) else ""


def get_paint(cwd=None, mode=None):
    mode = mode or cfg.color_mode(cwd)
    tc = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
    return styles.Paint(mode != "off", tc, mode == "gray")


def git_branch(cwd):
    """-> the current branch (or short hash when detached) of cwd, or ""."""
    if not cwd:
        return ""
    for args in (["symbolic-ref", "--short", "HEAD"], ["rev-parse", "--short", "HEAD"]):
        try:
            r = subprocess.run(["git", "-C", cwd, "--no-optional-locks", *args],
                               capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.SubprocessError):
            return ""
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return ""


def read_history():
    try:
        doc = json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def update_history(doc, values):
    """Append the rounded readings (ctx, ses, wk) that changed; ctx restarts per session."""
    sid = doc.get("session_id") if isinstance(doc.get("session_id"), str) else None
    hist = read_history()
    if hist.get("session_id") != sid:
        hist["ctx"] = []
    hist["session_id"] = sid
    for key, v in values.items():
        arr = hist.get(key) if isinstance(hist.get(key), list) else []
        v = round(v)
        if not arr or arr[-1] != v:
            arr.append(v)
        hist[key] = arr[-HISTORY_LEN:]
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".history-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(hist, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return hist


def build_data(doc, now, hist=None):
    """-> styles.Data from the Claude Code JSON document."""
    hist = hist or {}
    ws = doc.get("workspace")
    cwd = _text(ws.get("current_dir")) if isinstance(ws, dict) else ""
    cwd = cwd or _text(doc.get("cwd"))
    five, seven = parse_limits(doc)
    ctx = parse_context(doc)
    data = styles.Data(branch=git_branch(cwd))

    def h(key):
        v = hist.get(key)
        return [x for x in v if _num(x)] if isinstance(v, list) else []
    if ctx is not None:
        data.metrics.append(styles.Metric("ctx", "CTX", ctx, hist=h("ctx")))
    for key, label, w in (("ses", "Session", five), ("wk", "Weekly", seven)):
        if w:
            el = 1 - max(0, w["resets_at"] - now) / WINDOW[key]
            try:
                left = countdown(w["resets_at"], now)
            except (OverflowError, ValueError):
                left = "?"
            data.metrics.append(styles.Metric(key, label, w["used_percentage"], left,
                                              max(0.0, min(1.0, el)), h(key)))
    return data, cwd


def format_line(doc, now=None, hist=None, cols=None):
    now = time.time() if now is None else now
    doc = doc if isinstance(doc, dict) else {}
    data, cwd = build_data(doc, now, hist)
    P = get_paint(cwd)
    if cols is None:
        cols = cfg.terminal_columns(cwd)
    name, _ = cfg.choose(data, P, cwd, cols)
    return styles.render(name, data, P) or "claude"


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
    hist = None
    try:
        five, seven = parse_limits(doc)
        if five and seven:
            write_limits(doc, five, seven)
        values = {}
        ctx = parse_context(doc)
        if ctx is not None:
            values["ctx"] = ctx
        if five:
            values["ses"] = five["used_percentage"]
        if seven:
            values["wk"] = seven["used_percentage"]
        if values:
            hist = update_history(doc, values)
    except Exception:
        pass
    try:
        return format_line(doc, hist=hist if hist is not None else read_history())
    except Exception:
        return "claude"


# ---------- command line: statusline style ... ----------

USAGE = """usage: statusline style <command>
  list                     all styles; * marks the one in use
  preview [name|all]       draw a style (default: the one in use) on sample data
  set <name> [--project]   save the style (user config, or this project's file)
  next | prev | random     step through the styles [--project]
  show                     which layer wins, and why
  fit <a,b,...|off>        fallback styles when the line is wider than the terminal
  alert <at> <name>|off    switch to <name> when any value reaches <at> percent
  color on|gray|off        colors, grayscale (no hue) or none [--project]
preview takes --gray or --off to try a mode without saving it.
NO_COLOR (any value) and STATUSLINE_COLOR=on|gray|off override the setting."""


def sample_data():
    return styles.Data("main", [
        styles.Metric("ctx", "CTX", 37, hist=[8, 15, 22, 28, 31, 34, 36, 37]),
        styles.Metric("ses", "Session", 65, "1h 40m", 0.67, [20, 28, 35, 44, 52, 58, 62, 65]),
        styles.Metric("wk", "Weekly", 14, "4d 16h", 0.33, [2, 4, 6, 8, 10, 11, 13, 14])])


def _target(args):
    """-> (path, label) of the file a set-like command writes."""
    if "--project" in args:
        return cfg.project_path(os.getcwd()), "project file"
    return cfg.user_path(), "user config"


def cli(argv, out=print):
    """-> exit code."""
    args = [a for a in argv if a]
    if not args or args[0] != "style" or len(args) < 2 or args[1] in ("-h", "--help", "help"):
        out(USAGE)
        return 0 if args and args[-1] in ("-h", "--help", "help") else 2
    cmd = args[1]
    flags = [a for a in args[2:] if a.startswith("--")]
    rest = [a for a in args[2:] if not a.startswith("--")]
    cwd = os.getcwd()
    cur, source = cfg.requested(cwd)
    names = styles.NAMES
    P = get_paint(cwd, "gray" if "--gray" in flags else "off" if "--off" in flags else None)
    if cmd == "list":
        for n in names:
            out(f"{'*' if n == cur else ' '} {n:<10} {styles.describe(n)}")
        return 0
    if cmd == "preview":
        todo = names if rest[:1] == ["all"] else [rest[0] if rest else cur]
        for n in todo:
            if n not in styles.REG:
                out(f"error: unknown style '{n}'. Try: {', '.join(names)}")
                return 1
            out(f"{n}  {styles.describe(n)}")
            out(styles.render(n, sample_data(), P))
            out("")
        return 0
    if cmd in ("set", "next", "prev", "random"):
        path, label = _target(args)
        base = cfg.read(path).get("style")
        base = base if base in styles.REG else styles.DEFAULT
        if cmd == "set":
            if not rest or rest[0] not in styles.REG:
                out(f"error: unknown style '{rest[0] if rest else ''}'. Try: {', '.join(names)}")
                return 1
            new = rest[0]
        elif cmd == "random":
            new = random.choice([n for n in names if n != base])
        else:
            new = names[(names.index(base) + (1 if cmd == "next" else -1)) % len(names)]
        cfg.write(path, {"style": new})
        out(f"style = {new}  ({label}: {path})")
        eff, src = cfg.requested(cwd)
        if eff != new:
            out(f"note: {eff} still wins, from {src}")
        return 0
    if cmd == "show":
        for src, name in cfg.layers(cwd):
            out(f"{src:<22} {name or '-'}")
        out(f"{'color mode':<22} {cfg.color_mode(cwd)}")
        data = sample_data()
        name, trace = cfg.choose(data, P, cwd, cfg.terminal_columns(cwd))
        for t in trace:
            out("  " + t)
        out(f"shown: {name} (judged on sample data)")
        return 0
    if cmd == "fit":
        path, label = _target(args)
        if not rest:
            out(USAGE)
            return 2
        if rest[0] == "off":
            cfg.write(path, {"fit": None})
            out(f"fit off  ({label})")
            return 0
        lst = [x for x in rest[0].split(",") if x]
        bad = [x for x in lst if x not in styles.REG]
        if bad:
            out(f"error: unknown style '{bad[0]}'")
            return 1
        cfg.write(path, {"fit": lst})
        out(f"fit = {', '.join(lst)}  ({label})")
        return 0
    if cmd == "alert":
        path, label = _target(args)
        if rest[:1] == ["off"]:
            cfg.write(path, {"alert": None})
            out(f"alert off  ({label})")
            return 0
        if len(rest) != 2 or not rest[0].isdigit() or rest[1] not in styles.REG:
            out("usage: statusline style alert <percent> <name> | off")
            return 2
        cfg.write(path, {"alert": {"at": int(rest[0]), "style": rest[1]}})
        out(f"alert: at {rest[0]}% use {rest[1]}  ({label})")
        return 0
    if cmd == "color":
        path, label = _target(args)
        if len(rest) != 1 or rest[0] not in cfg.MODES:
            out("usage: statusline style color on|gray|off")
            return 2
        cfg.write(path, {"color": None if rest[0] == "on" else rest[0]})
        out(f"color = {rest[0]}  ({label})")
        if cfg.color_mode(cwd) != rest[0]:
            out(f"note: {cfg.color_mode(cwd)} still wins (NO_COLOR, STATUSLINE_COLOR or a stronger file)")
        return 0
    out(USAGE)
    return 2


def main():
    if len(sys.argv) > 1:
        try:
            code = cli(sys.argv[1:], out=lambda s="": sys.stdout.buffer.write((s + "\n").encode("utf-8")))
        except Exception as e:  # a command line tool may say what went wrong
            sys.stderr.write(f"statusline: {e}\n")
            code = 1
        sys.stdout.buffer.flush()
        sys.exit(code)
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        line = run(raw)
    except Exception:
        line = "claude"
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
