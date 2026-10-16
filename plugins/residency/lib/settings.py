"""Settings model: effective state of every tunable item, pending toggles, diff and write.

Reads the three Claude Code settings scopes (user `~/.claude/settings.json`, project
`.claude/settings.json`, local `.claude/settings.local.json`; precedence local > project >
user), tells the effective state of an item and the scope it comes from, turns pending
toggles into per-file changes, shows them as a unified diff and writes them with a
timestamped backup. Nothing is written until `write()` is called (decision Q3 of
`docs/residency-design.md`).

Merge rules: `permissions.deny` lists merge across scopes; `skillOverrides` and
`enabledPlugins` are maps where the higher scope wins per key. Unknown keys and key order
of every file are kept; files are written with a 2-space indent and a trailing newline.

Independent of the repo's `./skillz` on purpose: the plugin must work without it.
"""
import copy
import datetime
import difflib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

USER, PROJECT, LOCAL = "user", "project", "local"
SCOPES = (USER, PROJECT, LOCAL)  # lowest to highest precedence
BADGE = {USER: "U", PROJECT: "P", LOCAL: "L"}

SKILL, TOOL, MCP, PLUGIN, PLUGIN_SKILL = "skill", "tool", "mcp", "plugin", "plugin-skill"

CYCLES = {
    SKILL: ("on", "name-only", "user-invocable-only", "off"),
    TOOL: ("allow", "deny"),
    MCP: ("on", "deny"),
    PLUGIN: ("on", "off"),
}
DEFAULT_SCOPE = {SKILL: USER, PLUGIN: USER, TOOL: LOCAL, MCP: LOCAL}

NOT_SUPPORTED = "per-skill override not supported"


class SettingsError(Exception):
    """A settings file cannot be read (bad JSON, not an object)."""


class NotSupported(Exception):
    """The item cannot be toggled (plugin skills, decision Q10)."""


@dataclass(frozen=True)
class Item:
    """A tunable item.

    `name` is the skill name, the tool name, the MCP server name, `<plugin>@<marketplace>`
    for a plugin, or `<plugin>:<skill>` for a plugin's skill.
    """
    kind: str
    name: str


@dataclass(frozen=True)
class State:
    value: str
    source: str = None  # scope that sets it, None when it is the default

    @property
    def badge(self):
        return BADGE.get(self.source, " ")


def scope_paths(project_dir, home=None):
    home = Path(home) if home is not None else Path.home()
    project_dir = Path(project_dir)
    return {
        USER: home / ".claude" / "settings.json",
        PROJECT: project_dir / ".claude" / "settings.json",
        LOCAL: project_dir / ".claude" / "settings.local.json",
    }


def _read(path):
    """Return (text, data); a missing file is ("", {})."""
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return "", {}
    if not text.strip():
        return text, {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SettingsError("%s is not valid JSON (%s)" % (path, e))
    if not isinstance(data, dict):
        raise SettingsError("%s is not a JSON object" % path)
    return text, data


def dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _mcp_patterns(server):
    return ("mcp__%s__*" % server, "mcp__%s" % server)


def _deny_list(data):
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        return []
    deny = perms.get("deny")
    return deny if isinstance(deny, list) else []


def _map(data, key):
    m = data.get(key)
    return m if isinstance(m, dict) else {}


def _check(item):
    if item.kind == PLUGIN_SKILL:
        raise NotSupported(NOT_SUPPORTED)
    if item.kind not in CYCLES:
        raise ValueError("unknown item kind: %r" % item.kind)


def effective_in(datas, item):
    """Effective State of `item` given {scope: data}."""
    _check(item)
    if item.kind in (TOOL, MCP):
        pats = (item.name,) if item.kind == TOOL else _mcp_patterns(item.name)
        for scope in reversed(SCOPES):
            if any(p in _deny_list(datas[scope]) for p in pats):
                return State("deny", scope)
        return State(CYCLES[item.kind][0])
    key = "skillOverrides" if item.kind == SKILL else "enabledPlugins"
    for scope in reversed(SCOPES):
        m = _map(datas[scope], key)
        if item.name in m:
            v = m[item.name]
            if item.kind == PLUGIN:
                v = "on" if v else "off"
            return State(v, scope)
    return State(CYCLES[item.kind][0])


def next_state(item, value):
    _check(item)
    cycle = CYCLES[item.kind]
    i = cycle.index(value) if value in cycle else -1
    return cycle[(i + 1) % len(cycle)]


def _apply(datas, item, value, target):
    """Mutate {scope: data} so that `item` becomes `value`, writing in `target`.

    Denies: added to the target; removed from every scope that holds them. Maps: the value
    goes in the target and the key is dropped from higher scopes (they would win); a skill
    back to `on` drops its override from every scope (on is the default).
    """
    if item.kind in (TOOL, MCP):
        pats = (item.name,) if item.kind == TOOL else _mcp_patterns(item.name)
        if value == "deny":
            if effective_in(datas, item).value != "deny":
                perms = datas[target].setdefault("permissions", {})
                perms.setdefault("deny", []).append(pats[0])
        else:
            for scope in SCOPES:
                deny = _deny_list(datas[scope])
                if any(p in deny for p in pats):
                    deny[:] = [d for d in deny if d not in pats]
        return
    higher = SCOPES[SCOPES.index(target) + 1:]
    if item.kind == SKILL:
        if value == "on":
            for scope in SCOPES:
                _map(datas[scope], "skillOverrides").pop(item.name, None)
            return
        datas[target].setdefault("skillOverrides", {})[item.name] = value
    else:
        datas[target].setdefault("enabledPlugins", {})[item.name] = (value == "on")
    key = "skillOverrides" if item.kind == SKILL else "enabledPlugins"
    for scope in higher:
        _map(datas[scope], key).pop(item.name, None)


class Settings:
    """The three scopes as read from disk."""

    def __init__(self, project_dir, home=None):
        self.paths = scope_paths(project_dir, home)
        self.reload()

    def reload(self):
        self.texts, self.data = {}, {}
        for scope, path in self.paths.items():
            self.texts[scope], self.data[scope] = _read(path)

    def effective(self, item):
        return effective_in(self.data, item)

    def pending(self):
        return Pending(self)


class Pending:
    """Toggles kept in memory: {item: (value, target scope)}."""

    def __init__(self, settings):
        self.settings = settings
        self.changes = {}
        self.scopes = {}  # target scope chosen with `s`, kept across toggles

    def __bool__(self):
        return bool(self.changes)

    def state(self, item):
        """The value the item will have (pending or effective)."""
        if item in self.changes:
            return self.changes[item][0]
        return self.settings.effective(item).value

    def scope(self, item):
        _check(item)
        return self.scopes.get(item, DEFAULT_SCOPE[item.kind])

    def set(self, item, value, scope=None):
        _check(item)
        if value not in CYCLES[item.kind]:
            raise ValueError("%s: invalid state %r" % (item.kind, value))
        if scope is not None:
            self.set_scope(item, scope)
        scope = self.scope(item)
        if value == self.settings.effective(item).value:
            self.changes.pop(item, None)
        else:
            self.changes[item] = (value, scope)

    def toggle(self, item):
        """Advance the item to the next state of its cycle; return the new value."""
        value = next_state(item, self.state(item))
        self.set(item, value)
        return value

    def set_scope(self, item, scope):
        """Change the target scope (key `s`); kept for the item even before a toggle."""
        _check(item)
        if scope not in SCOPES:
            raise ValueError("unknown scope: %r" % scope)
        self.scopes[item] = scope
        if item in self.changes:
            self.changes[item] = (self.changes[item][0], scope)

    def clear(self):
        self.changes.clear()
        self.scopes.clear()

    def after(self):
        """{scope: data} with every pending change applied (copies, disk untouched)."""
        datas = copy.deepcopy(self.settings.data)
        for item, (value, scope) in self.changes.items():
            _apply(datas, item, value, scope)
        return datas

    def effective_after(self, item):
        return effective_in(self.after(), item)

    def changed_scopes(self):
        after = self.after()
        return [s for s in SCOPES if after[s] != self.settings.data[s]]

    def fragments(self):
        """{scope: {top-level key: new value}} for the keys the toggles change, per file.

        For `permissions` only `deny` is included.
        """
        after, out = self.after(), {}
        for scope in SCOPES:
            old, new = self.settings.data[scope], after[scope]
            frag = {}
            for key in ("permissions", "skillOverrides", "enabledPlugins"):
                if key == "permissions":
                    if _deny_list(old) != _deny_list(new) or (
                            "permissions" in new) != ("permissions" in old):
                        frag["permissions"] = {"deny": list(_deny_list(new))}
                elif old.get(key) != new.get(key):
                    frag[key] = copy.deepcopy(new.get(key, {}))
            if frag:
                out[scope] = frag
        return out

    def as_cli_settings(self):
        """A dict for `claude --settings '<json>'` layered over the files on disk.

        Holds the pending skill overrides, plugin switches and added denies. Removing a deny
        cannot be expressed by a layered settings file (deny lists merge): those items are
        listed by `unexpressible()` and left out here.
        """
        out = {}
        for item, (value, _scope) in self.changes.items():
            if item.kind == SKILL:
                out.setdefault("skillOverrides", {})[item.name] = value
            elif item.kind == PLUGIN:
                out.setdefault("enabledPlugins", {})[item.name] = (value == "on")
            elif value == "deny":
                pat = item.name if item.kind == TOOL else _mcp_patterns(item.name)[0]
                out.setdefault("permissions", {}).setdefault("deny", []).append(pat)
        return out

    def unexpressible(self):
        """Pending items `as_cli_settings()` cannot express (deny removals)."""
        return [i for i, (v, _s) in self.changes.items()
                if i.kind in (TOOL, MCP) and v != "deny"]

    def diff(self):
        """{scope: unified diff text} for every file that would change."""
        after, out = self.after(), {}
        for scope in self.changed_scopes():
            path = str(self.settings.paths[scope])
            old = self.settings.texts[scope]
            new = dump(after[scope])
            out[scope] = "".join(difflib.unified_diff(
                old.splitlines(True), new.splitlines(True),
                fromfile=path if old else "/dev/null", tofile=path))
        return out

    def write(self, now=None):
        """Back up and write every changed file; return [(path, backup or None)].

        The backup is `<file>.bak-<YYYYmmdd-HHMMSS>`, made before the write; a file that did
        not exist gets no backup. Pending changes are cleared and the settings reloaded.
        """
        now = now or datetime.datetime.now()
        stamp = now.strftime("%Y%m%d-%H%M%S")
        after, done = self.after(), []
        for scope in self.changed_scopes():
            path = Path(self.settings.paths[scope])
            backup = None
            if path.exists():
                backup = path.with_name("%s.bak-%s" % (path.name, stamp))
                shutil.copy2(path, backup)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(dump(after[scope]))
            done.append((path, backup))
        self.settings.reload()
        self.clear()
        return done
