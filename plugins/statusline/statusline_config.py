"""Style configuration: layers, alert rule and fit rule.

Layers, strongest first: env STATUSLINE_STYLE, <project>/.claude/statusline.json,
<config dir>/statusline/config.json, the default. fit, alert and columns are
read from the project file over the user file. Never raises on bad files.
"""
import json
import os
import tempfile
from pathlib import Path

import statusline_styles as styles


def config_dir():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def user_path():
    return config_dir() / "statusline" / "config.json"


def project_path(cwd):
    return Path(cwd) / ".claude" / "statusline.json"


def read(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def write(path, update):
    """Merge update into the JSON file at path (atomic). -> the new document."""
    path = Path(path)
    doc = read(path)
    doc.update(update)
    for k in [k for k, v in doc.items() if v is None]:
        del doc[k]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".cfg-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return doc


def _valid(name):
    return isinstance(name, str) and name in styles.REG


def layers(cwd, env=None):
    """-> [(source, style name or None)], strongest first."""
    env = os.environ if env is None else env
    proj = read(project_path(cwd)) if cwd else {}
    return [("env STATUSLINE_STYLE", env.get("STATUSLINE_STYLE") or None),
            ("project file", proj.get("style")),
            ("user config", read(user_path()).get("style"))]


def settings(cwd):
    """-> the merged fit/alert/columns settings."""
    cfg = read(user_path())
    if cwd:
        cfg.update({k: v for k, v in read(project_path(cwd)).items() if k != "style"})
    return cfg


def requested(cwd, env=None):
    """-> (name, source): the first valid layer, else the default."""
    for source, name in layers(cwd, env):
        if _valid(name):
            return name, source
    return styles.DEFAULT, "default"


def choose(data, paint, cwd, cols=None, env=None):
    """-> (style name, trace lines) after the alert and fit rules."""
    cfg = settings(cwd)
    name, source = requested(cwd, env)
    trace = [f"requested {name} from {source}"]

    alert = cfg.get("alert")
    if isinstance(alert, dict) and _valid(alert.get("style")) and \
            isinstance(alert.get("at"), (int, float)) and data.metrics:
        top = max(m.pct for m in data.metrics)
        if round(top) >= alert["at"]:
            name = alert["style"]
            trace.append(f"alert: highest value {round(top)}% >= {alert['at']}%, using {name}")
        else:
            trace.append(f"alert: highest value {round(top)}% < {alert['at']}%, no change")

    fit = cfg.get("fit")
    if isinstance(fit, list) and cols:
        chain = [name] + [x for x in fit if _valid(x) and x != name]
        parts = []
        chosen = None
        for cand in chain:
            w = styles.visible_width(styles.render(cand, data, paint))
            if w <= cols:
                parts.append(f"{cand} needs {w}, fits")
                chosen = cand
                break
            parts.append(f"{cand} needs {w}, too wide")
        if chosen is None:
            chosen = chain[-1]
            parts.append("nothing fits, the line will be clipped")
        trace.append(f"fit at {cols} columns: " + "; ".join(parts))
        name = chosen
    return name, trace


def terminal_columns(cwd):
    """-> the terminal width in columns, or None when it cannot be told."""
    cols = settings(cwd).get("columns")
    if isinstance(cols, int) and not isinstance(cols, bool) and cols > 0:
        return cols
    try:
        fd = os.open("/dev/tty", os.O_RDONLY)
        try:
            n = os.get_terminal_size(fd).columns
        finally:
            os.close(fd)
        if n > 0:
            return n
    except (OSError, ValueError):
        pass
    try:
        n = int(os.environ.get("COLUMNS", ""))
        return n if n > 0 else None
    except ValueError:
        return None
