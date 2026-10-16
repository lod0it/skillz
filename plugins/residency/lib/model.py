"""The model the TUI draws: categories of items, NOW/AFTER totals, stale banner, predictions.

Joins the latest interactive snapshot (`snapshot.py`), the settings and pending toggles
(`settings.py`), headless measures (`measure.py`) and usage counts (`usage.py`). Zero
tokens: everything is read from disk or passed in.

Origin marks (design Q2): `=` measured (a `/context` row, a headless delta or a delta
learned from two interactive snapshots), `~` estimated (an unmeasured toggle using the
item's own size, or an item added after the snapshot sized at chars/4 of its SKILL.md
description), `?` unknown.

Totals: NOW is the real resident total of the snapshot (its total minus `Messages`);
`AFTER = NOW - sum of the deltas of the toggled items`; a delta learned from interactive
snapshots wins over a headless one, which wins over an estimate.
"""
import datetime
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import settings as S
import snapshot

MEASURED, ESTIMATED, UNKNOWN = "=", "~", "?"

# Built-in tools that can be denied. /context has no per-tool rows, so the list is this
# constant plus every non-MCP tool seen in usage and every plain name in a deny list.
BUILTIN_TOOLS = ("Agent", "Bash", "Edit", "Glob", "Grep", "NotebookEdit", "Read", "Skill",
                 "TodoWrite", "WebFetch", "WebSearch", "Write")

OFF_STATES = ("off", "user-invocable-only", "deny")
NAME_ONLY_COST = 20  # `< 20` in /context once a skill is name-only

CORE, TOOLS, SKILLS, PLUGINS, MCP, AGENTS, MEMORY = (
    "core", "tools", "skills", "plugins", "mcp", "agents", "memory")

# Bar groups (design Q4 legend) -> the snapshot categories they sum.
GROUPS = (
    ("core", ("System prompt", "System tools")),
    ("skills", ("Skills",)),
    ("mcp", ("MCP server instructions", "MCP tools")),
    ("memory", ("Memory files", "Custom agents")),
)
GROUP_OF = {CORE: "core", TOOLS: "core", SKILLS: "skills", PLUGINS: "skills", MCP: "mcp",
            AGENTS: "memory", MEMORY: "memory"}


def default_predictions_path():
    return Path.home() / ".claude" / "residency-predictions.jsonl"


def default_learned_path():
    return Path.home() / ".claude" / "residency-learned.json"


# ---------------------------------------------------------------- formatting


def fmt(n, k=False):
    """Token count for display: `330`, `1.2k`, `146.9k`, `1m`; `?` for None.

    `k=True` forces the `k` form below 1000 (`0.1k`), as category rows do.
    """
    if n is None:
        return "?"
    sign, a = ("-" if n < 0 else ""), abs(int(n))
    if a >= 1000000 and a % 1000000 == 0:
        return "%s%dm" % (sign, a // 1000000)
    if a < 1000 and not k:
        return sign + str(a)
    tenths = (a + 50) // 100  # round half up on integers: no float surprises
    return "%s%d.%dk" % (sign, tenths // 10, tenths % 10)


def parse_ts(ts):
    """ISO timestamp (transcripts use `...Z`) -> aware datetime, None when unreadable."""
    if not ts:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def now_ts(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------- data


@dataclass
class Row:
    """One item of a category."""
    key: str
    label: str
    setting: object = None  # settings.Item, None when not tunable
    resident: int = None  # tokens resident now, None when unknown
    origin: str = UNKNOWN
    on_load: int = None  # MCP: tokens of its tools when loaded
    upper_bound: bool = False  # `< 20` in /context
    size_on: int = None  # resident size when on, when known (for estimates)
    state: str = None  # effective state now
    after: str = None  # state after the pending toggles
    badge: str = " "  # U/P/L of the scope the effective state comes from, ' ' default
    target: str = None  # scope a toggle writes to
    here: int = None
    all: int = None
    delta: int = None  # resident tokens saved by the toggle (negative: it costs more)
    delta_origin: str = None
    note: str = ""
    lump: bool = False  # the interactive-only pseudo-row

    @property
    def toggled(self):
        return self.setting is not None and self.after != self.state

    @property
    def tunable(self):
        return self.setting is not None and self.setting.kind != S.PLUGIN_SKILL


@dataclass
class Category:
    key: str
    label: str
    resident: int = None
    origin: str = MEASURED
    after: int = None
    on_load: int = None
    rows: list = field(default_factory=list)
    note: str = ""


@dataclass
class Prediction:
    time: str
    claude_version: str
    project: str
    predicted_after: int
    changes: list  # [{kind, name, from, to, scope}]


@dataclass
class Comparison:
    """`last change  predicted 31.4k  actual 31.9k  error +0.5k (1.6%)`; actual None = waiting."""
    predicted: int
    actual: int = None
    time: str = ""

    @property
    def error(self):
        return None if self.actual is None else self.actual - self.predicted

    @property
    def error_pct(self):
        if self.actual is None or not self.predicted:
            return None
        return 100.0 * self.error / self.predicted

    def line(self):
        if self.actual is None:
            return "last change  predicted %s  (run claude, /context, /exit to check)" % fmt(
                self.predicted)
        e = self.error
        return "last change  predicted %s  actual %s  error %s%s (%.1f%%)" % (
            fmt(self.predicted), fmt(self.actual), "+" if e >= 0 else "", fmt(e),
            abs(self.error_pct))


@dataclass
class Model:
    found: object = None  # snapshot.Found, None when no snapshot exists
    now: int = None
    after: int = None
    after_origin: str = MEASURED
    window: int = None
    categories: list = field(default_factory=list)
    stale_since: object = None  # datetime of the newest settings file when stale
    comparison: object = None  # Comparison

    @property
    def saved(self):
        return None if self.now is None or self.after is None else self.now - self.after

    @property
    def saved_pct(self):
        return 100.0 * self.saved / self.now if self.now else None

    @property
    def window_pct(self):
        return 100.0 * self.now / self.window if self.now is not None and self.window else None

    def stale_line(self):
        if not self.stale_since:
            return ""
        return ("snapshot stale: settings changed since %s; run claude, /context, /exit"
                % self.stale_since.astimezone().strftime("%Y-%m-%d %H:%M"))

    def category(self, key):
        return next((c for c in self.categories if c.key == key), None)

    def rows(self):
        return [r for c in self.categories for r in c.rows]

    def toggled(self):
        return [r for r in self.rows() if r.toggled]

    def segments(self, after=False):
        """{bar group: tokens} for NOW, or AFTER (deltas subtracted from their group)."""
        snap = self.found.snapshot if self.found else None
        cats = snap.categories if snap else {}
        out = {g: sum(cats.get(c, 0) for c in names) for g, names in GROUPS}
        if after:
            for c in self.categories:
                for r in c.rows:
                    if r.toggled and r.delta:
                        out[GROUP_OF[c.key]] -= r.delta
        return out

    def sort(self, mode="cost"):
        for c in self.categories:
            c.rows = sort_rows(c.rows, mode)


# ---------------------------------------------------------------- helpers


def resident_total(snap):
    """Resident tokens of a snapshot: its total minus the conversation (`Messages`)."""
    if snap.approx or not snap.categories:
        return snap.total
    return snap.total - snap.categories.get("Messages", 0)


def measure_key(item, value):
    """Key of a measured delta: the item and the state it is toggled to."""
    return "%s|%s|%s" % (item.kind, item.name, value)


def change_for(sett, item, value):
    """The `--settings` dict that puts `item` in `value` over the files on disk, or None
    when a layered settings file cannot express it (removing a deny)."""
    p = sett.pending()
    p.set(item, value)
    if p.unexpressible():
        return None
    return p.as_cli_settings()


def _cost_in(state, size_on):
    if state in OFF_STATES:
        return 0
    if state == "name-only":
        return NAME_ONLY_COST if size_on is None else min(size_on, NAME_ONLY_COST)
    return size_on


def frontmatter_tokens(path):
    """chars/4 of a SKILL.md's `name` + `description` frontmatter, None when unreadable."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    fields, cur = {}, None
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ln[:1] in (" ", "\t") and cur:
            fields[cur] = (fields[cur] + " " + ln.strip()).strip()
            continue
        k, sep, v = ln.partition(":")
        if sep:
            cur = k.strip()
            v = v.strip()
            fields[cur] = "" if v in (">", "|", ">-", "|-") else v.strip("\"'")
    text = fields.get("name", "") + fields.get("description", "")
    return -(-len(text) // 4) if fields.get("description") else None


def installed_plugins(project_dir, home=None):
    """{"name@marketplace": installPath} of the plugins that apply to this project."""
    home = Path(home) if home is not None else Path.home()
    try:
        data = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    plugins = data.get("plugins") if isinstance(data, dict) else None
    for pid, entries in (plugins or {}).items():
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict):
                continue
            if e.get("scope") in ("project", "local") and \
                    str(e.get("projectPath", "")) != str(project_dir):
                continue
            out[pid] = e.get("installPath", "")
    return out


def _plugin_size(install_path):
    if not install_path:
        return None
    sizes = [frontmatter_tokens(p) for p in sorted(Path(install_path).glob("skills/*/SKILL.md"))]
    sizes = [s for s in sizes if s is not None]
    return sum(sizes) if sizes else None


def _settings_names(sett, key):
    names = []
    for scope in S.SCOPES:
        m = sett.data[scope].get(key)
        if isinstance(m, dict):
            names += [k for k in m if k not in names]
    return names


def _denied(sett):
    out = []
    for scope in S.SCOPES:
        for d in S._deny_list(sett.data[scope]):
            if isinstance(d, str) and d not in out:
                out.append(d)
    return out


def _count(counts, attr, name):
    if counts is None:
        return None
    return getattr(counts, attr).get(name, 0)


# ---------------------------------------------------------------- builder


class Builder:
    def __init__(self, found, sett, pending=None, measures=None, learned=None, here=None,
                 all_=None, headless=None, project_dir=None, home=None, tools=None):
        self.found = found
        self.snap = found.snapshot if found else snapshot.Snapshot(approx=True)
        self.sett = sett
        self.pending = pending if pending is not None else sett.pending()
        self.measures = measures or {}
        self.learned = learned or {}
        self.here, self.all = here, all_
        self.headless = headless
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.home = Path(home) if home is not None else Path.home()
        self.tools = tools

    # rows ---------------------------------------------------------
    def _tunable(self, row, item):
        row.setting = item
        st = self.sett.effective(item)
        row.state, row.badge = st.value, st.badge
        row.after = self.pending.state(item)
        row.target = self.pending.scope(item)
        return row

    def _measured(self, item, value):
        k = measure_key(item, value)
        if k in self.learned:
            return self.learned[k]
        d = self.measures.get(k)
        if d is not None and getattr(d, "ok", False):
            return d.total
        return None

    def _set_delta(self, row):
        if not row.toggled:
            return
        m = self._measured(row.setting, row.after)
        if m is not None:
            row.delta, row.delta_origin = m, MEASURED
            return
        if row.resident is not None and (row.after in OFF_STATES or row.size_on is not None
                                         or row.after == "name-only"):
            cost = _cost_in(row.after, row.size_on)
            if cost is not None:
                row.delta, row.delta_origin = row.resident - cost, ESTIMATED
                return
        row.delta, row.delta_origin = None, UNKNOWN

    def _skill_file(self, name):
        for base in (self.project_dir / ".claude" / "skills", self.home / ".claude" / "skills"):
            p = base / name / "SKILL.md"
            if p.is_file():
                return p
        return None

    def _missing(self, row, size):
        """An item the snapshot does not list: 0 when off, else the estimate (`~`) or `?`."""
        row.size_on = size
        if (row.state or "") in OFF_STATES:
            row.resident, row.origin = 0, MEASURED
        elif size is not None:
            row.resident, row.origin = _cost_in(row.state, size), ESTIMATED
            row.note = "added after the snapshot"
        else:
            row.resident, row.origin = None, UNKNOWN
            row.note = "added after the snapshot"

    def skills(self):
        rows, seen = [], set()
        for it in self.snap.skills:
            seen.add(it.name)
            row = Row("skill:" + it.name, it.name, resident=it.tokens, origin=MEASURED,
                      upper_bound=it.approx, here=_count(self.here, "skills", it.name),
                      all=_count(self.all, "skills", it.name))
            if it.source.startswith("Plugin"):
                row.setting = S.Item(S.PLUGIN_SKILL, it.name)
                row.note = S.NOT_SUPPORTED
            else:
                self._tunable(row, S.Item(S.SKILL, it.name))
                if row.state == "on":
                    row.size_on = it.tokens
                else:
                    f = self._skill_file(it.name)
                    row.size_on = frontmatter_tokens(f) if f else None
            rows.append(row)
        extra = _settings_names(self.sett, "skillOverrides")
        for base in (self.home / ".claude" / "skills", self.project_dir / ".claude" / "skills"):
            if base.is_dir():
                extra += sorted(p.parent.name for p in base.glob("*/SKILL.md"))
        for name in extra:
            if name in seen or ":" in name:
                continue
            seen.add(name)
            row = self._tunable(Row("skill:" + name, name, here=_count(self.here, "skills", name),
                                    all=_count(self.all, "skills", name)), S.Item(S.SKILL, name))
            f = self._skill_file(name)
            self._missing(row, frontmatter_tokens(f) if f else None)
            rows.append(row)
        for r in rows:
            self._set_delta(r)
        return rows

    def _plugin_usage(self, counts, short):
        if counts is None:
            return None
        return sum(v for k, v in counts.skills.items() if k.split(":", 1)[0] == short
                   and ":" in k)

    def plugins(self):
        installed = installed_plugins(self.project_dir, self.home)
        known = list(installed) + [k for k in _settings_names(self.sett, "enabledPlugins")
                                   if k not in installed]
        sizes = {}
        for it in self.snap.skills:
            if it.source.startswith("Plugin (") and it.source.endswith(")"):
                short = it.source[len("Plugin ("):-1]
                sizes[short] = sizes.get(short, 0) + it.tokens
        rows, done = [], set()
        for short, size in sizes.items():
            pid = next((k for k in known if k.split("@", 1)[0] == short), None)
            row = Row("plugin:" + (pid or short), pid or short, resident=size, origin=MEASURED,
                      size_on=size, here=self._plugin_usage(self.here, short),
                      all=self._plugin_usage(self.all, short))
            if pid:
                self._tunable(row, S.Item(S.PLUGIN, pid))
                done.add(pid)
            else:
                row.note = "marketplace unknown"
            rows.append(row)
        for pid in known:
            if pid in done:
                continue
            short = pid.split("@", 1)[0]
            row = self._tunable(Row("plugin:" + pid, pid, here=self._plugin_usage(self.here, short),
                                    all=self._plugin_usage(self.all, short)), S.Item(S.PLUGIN, pid))
            self._missing(row, _plugin_size(installed.get(pid)))
            rows.append(row)
        for r in rows:
            self._set_delta(r)
        return rows

    def tool_names(self):
        names = list(self.tools if self.tools is not None else BUILTIN_TOOLS)
        for c in (self.here, self.all):
            for t in (c.tools if c else {}):
                if not t.startswith("mcp__") and t not in names:
                    names.append(t)
        for d in _denied(self.sett):
            if not d.startswith("mcp__") and "(" not in d and d not in names:
                names.append(d)
        return names

    def tools_rows(self):
        rows = []
        for name in self.tool_names():
            item = S.Item(S.TOOL, name)
            row = self._tunable(Row("tool:" + name, name, here=_count(self.here, "tools", name),
                                    all=_count(self.all, "tools", name)), item)
            if row.state == "deny":
                row.resident, row.origin = 0, MEASURED
            else:
                m = self._measured(item, "deny")
                if m is not None:
                    row.resident, row.origin = m, MEASURED
            self._set_delta(row)
            rows.append(row)
        return rows

    def mcp_rows(self):
        servers = {}
        for it in self.snap.mcp_tools:
            servers[it.source] = servers.get(it.source, 0) + it.tokens
        for d in _denied(self.sett):
            if d.startswith("mcp__"):
                name = d[len("mcp__"):]
                name = name[:-3] if name.endswith("__*") else name
                if "__" not in name:
                    servers.setdefault(name, None)
        rows = []
        for name, on_load in servers.items():
            item = S.Item(S.MCP, name)
            row = self._tunable(Row("mcp:" + name, name, on_load=on_load,
                                    here=_count(self.here, "mcp", name),
                                    all=_count(self.all, "mcp", name)), item)
            if row.state == "deny":
                row.resident, row.origin = 0, MEASURED
            else:
                m = self._measured(item, "deny")
                if m is not None:
                    row.resident, row.origin = m, MEASURED
            self._set_delta(row)
            rows.append(row)
        return rows

    # categories ---------------------------------------------------
    def build(self):
        cats = self.snap.categories
        has = bool(cats)
        g = (lambda *names: sum(cats.get(n, 0) for n in names)) if has else (lambda *n: None)
        out = []

        out.append(Category(CORE, "core (system prompt)", g("System prompt"), note="not tunable"))

        tools = Category(TOOLS, "built-in tools", g("System tools"), rows=self.tools_rows())
        if has and self.headless is not None and self.headless.categories:
            lump = cats.get("System tools", 0) - self.headless.categories.get("System tools", 0)
            tools.rows.append(Row("lump:interactive-only", "interactive-only", resident=lump,
                                  origin=MEASURED, lump=True))
        elif has:
            tools.rows.append(Row("lump:interactive-only", "interactive-only", lump=True,
                                  note="needs the headless base"))
        out.append(tools)

        skills = self.skills()
        out.append(Category(SKILLS, "skills (%d)" % len(skills), g("Skills"), rows=skills))

        plugins = self.plugins()
        out.append(Category(PLUGINS, "plugins (%d)" % len(plugins),
                            sum(r.resident for r in plugins if r.origin == MEASURED
                                and r.resident is not None) if has else None, rows=plugins,
                            note="inside skills"))

        mcp = self.mcp_rows()
        # the category rows are rounded once, the per-tool rows each: prefer the categories
        on_load = g("MCP tools", "MCP tools (deferred)") if has else sum(
            r.on_load or 0 for r in mcp)
        out.append(Category(MCP, "mcp (%d)" % len(mcp),
                            g("MCP server instructions", "MCP tools"), on_load=on_load, rows=mcp))

        agents = [Row("agent:" + a.name, a.name, resident=a.tokens, origin=MEASURED, note=a.source)
                  for a in self.snap.agents]
        out.append(Category(AGENTS, "custom agents (%d)" % len(agents), g("Custom agents"),
                            rows=agents, note="not tunable"))

        mem = [Row("memory:" + m.path, m.path, resident=m.tokens, origin=MEASURED, note=m.source)
               for m in self.snap.memory_files]
        out.append(Category(MEMORY, "memory / CLAUDE.md", g("Memory files"), rows=mem,
                            note="not tunable"))

        model = Model(found=self.found, categories=out,
                      window=self.snap.window or None)
        if self.found:
            model.now = resident_total(self.snap)
        worst = MEASURED
        saved = 0
        for c in out:
            if not has:
                c.origin = UNKNOWN
            c.after = c.resident
            for r in c.rows:
                if not r.toggled:
                    continue
                if r.delta_origin == UNKNOWN:
                    worst = UNKNOWN
                elif r.delta_origin == ESTIMATED and worst == MEASURED:
                    worst = ESTIMATED
                saved += r.delta or 0
                if c.after is not None:
                    c.after -= r.delta or 0
        if model.now is not None:
            model.after = model.now - saved
        model.after_origin = worst
        return model


def build(found, sett, pending=None, measures=None, learned=None, here=None, all_=None,
          headless=None, project_dir=None, home=None, tools=None, predictions=None,
          snapshots=None, sort="cost"):
    """Build the Model.

    found: snapshot.Found or None. sett/pending: settings.Settings and its Pending.
    measures: {measure_key: measure.Delta}. learned: {measure_key: tokens} (interactive).
    here/all_: usage.Counts. headless: the headless base Snapshot (interactive-only lump).
    tools: built-in tool names (default BUILTIN_TOOLS + usage + denies).
    predictions/snapshots: from load_predictions() and interactive_snapshots(), for the
    prediction vs actual line.
    """
    m = Builder(found, sett, pending, measures, learned, here, all_, headless, project_dir,
                home, tools).build()
    m.stale_since = stale_since(sett.paths.values(), found)
    if predictions is not None:
        m.comparison = compare(predictions, snapshots or [], project_dir)
    m.sort(sort)
    return m


# ---------------------------------------------------------------- sorting


def waste(row):
    """cost x unused: the resident cost divided by 1 + the uses in this project."""
    cost = row.resident or 0
    uses = row.here if row.here is not None else (row.all or 0)
    return cost / (1.0 + uses)


def sort_rows(rows, mode="cost"):
    """Sort by resident cost or by cost x unused (`o`), both descending; the
    interactive-only lump stays last and unknown costs sink."""
    if mode == "cost":
        key = lambda r: (r.lump, -(r.resident if r.resident is not None else -1), r.label)
    elif mode == "waste":
        key = lambda r: (r.lump, -waste(r), -(r.resident or 0), r.label)
    else:
        raise ValueError("sort mode must be 'cost' or 'waste'")
    return sorted(rows, key=key)


# ---------------------------------------------------------------- stale


def stale_since(paths, found):
    """mtime (aware datetime) of the newest settings file when it is newer than the
    snapshot, else None."""
    if not found:
        return None
    ts = parse_ts(found.timestamp)
    if ts is None:
        return None
    newest = None
    for p in paths:
        try:
            m = os.stat(p).st_mtime
        except OSError:
            continue
        newest = m if newest is None else max(newest, m)
    if newest is None:
        return None
    d = datetime.datetime.fromtimestamp(newest, datetime.timezone.utc)
    return d if d > ts else None


# ---------------------------------------------------------------- predictions


def record_prediction(model, pending, project_dir, claude_version, path=None, now=None):
    """Append the prediction of a write; call it before `pending.write()`."""
    changes = []
    for item, (value, scope) in pending.changes.items():
        changes.append({"kind": item.kind, "name": item.name,
                        "from": pending.settings.effective(item).value, "to": value,
                        "scope": scope})
    p = Prediction(now_ts(now), claude_version, str(project_dir), model.after, changes)
    path = Path(path) if path else default_predictions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(p.__dict__, sort_keys=True) + "\n")
    return p


def load_predictions(path=None, project_dir=None):
    """Predictions in file order, only this project's when project_dir is given."""
    path = Path(path) if path else default_predictions_path()
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            d = json.loads(ln)
            p = Prediction(d["time"], d.get("claude_version", ""), d.get("project", ""),
                           d.get("predicted_after"), list(d.get("changes") or []))
        except (ValueError, KeyError, TypeError):
            continue
        if project_dir is None or p.project == str(project_dir):
            out.append(p)
    return out


def interactive_snapshots(project_dir, projects_root=None):
    """Every interactive /context of the project as [(aware datetime, Snapshot)], oldest first."""
    d = snapshot.transcripts_dir(project_dir, projects_root)
    out = []
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        for rec in snapshot._records(f):
            if not isinstance(rec, dict):
                continue
            if rec.get("type") == "user" and rec.get("isMeta") and \
                    snapshot._text(rec).lstrip().startswith(snapshot.MARKER):
                ts = parse_ts(rec.get("timestamp"))
                if ts is None:
                    continue
                try:
                    out.append((ts, snapshot.parse_context(snapshot._text(rec))))
                except ValueError:
                    continue
    out.sort(key=lambda x: x[0])
    return out


def compare(predictions, snaps, project_dir=None):
    """Comparison for the latest prediction (of the project): the first interactive
    snapshot newer than it is the actual; None when there is no prediction."""
    preds = [p for p in predictions if project_dir is None or p.project == str(project_dir)]
    preds = [p for p in preds if parse_ts(p.time) and p.predicted_after is not None]
    if not preds:
        return None
    p = max(preds, key=lambda x: parse_ts(x.time))
    t = parse_ts(p.time)
    nxt = next((s for ts, s in snaps if ts > t), None)
    return Comparison(p.predicted_after, resident_total(nxt) if nxt else None, p.time)


def learn(predictions, snaps, project_dir=None):
    """Interactive deltas: {measure_key: tokens} from predictions with exactly one change
    whose surrounding snapshots (last before, first after) enclose no other write."""
    preds = [p for p in predictions if project_dir is None or p.project == str(project_dir)]
    times = [(parse_ts(p.time), p) for p in preds if parse_ts(p.time)]
    out = {}
    for t, p in sorted(times, key=lambda x: x[0]):
        if len(p.changes) != 1:
            continue
        before = [(ts, s) for ts, s in snaps if ts < t]
        after = [(ts, s) for ts, s in snaps if ts > t]
        if not before or not after:
            continue
        (ta, a), (tb, b) = before[-1], after[0]
        if any(o is not p and ta < ot < tb for ot, o in times):
            continue
        c = p.changes[0]
        try:
            key = measure_key(S.Item(c["kind"], c["name"]), c["to"])
        except (KeyError, TypeError):
            continue
        out[key] = resident_total(a) - resident_total(b)
    return out


def load_learned(path=None):
    path = Path(path) if path else default_learned_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v["delta"] for k, v in data.items() if isinstance(v, dict) and
            isinstance(v.get("delta"), int)}


def save_learned(new, path=None, now=None):
    """Merge {measure_key: tokens} into the learned file (kept after transcripts expire)."""
    if not new:
        return
    path = Path(path) if path else default_learned_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    stamp = now_ts(now)
    for k, v in new.items():
        data[k] = {"delta": int(v), "time": stamp}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
