"""Parse `/context` markdown into a Snapshot and find the latest one in a project's transcripts.

Zero tokens: everything is read from disk (transcripts) or from a headless `/context` JSON.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MARKER = "## Context Usage"
_CELL = re.compile(r"^(~|<)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM]?)$")


def parse_tokens(cell):
    """Parse a token cell into (tokens, approx).

    `56.1k` -> 56100, `1m` -> 1000000, `429`, `0`, `~120` -> 120 and `< 20` -> 20 with
    approx=True (an upper bound, not a measure). `~` is the normal rounding of the skills
    table, so it does not set the flag. Raises ValueError on anything else.
    """
    m = _CELL.match(cell.strip())
    if not m:
        raise ValueError("not a token cell: %r" % cell)
    prefix, num, unit = m.groups()
    value = float(num.replace(",", ""))
    value *= {"": 1, "k": 1000, "m": 1000000}[unit.lower()]
    return int(round(value)), prefix == "<"


@dataclass
class Item:
    name: str
    tokens: int
    source: str = ""  # MCP server, skill source, agent source or memory type
    approx: bool = False
    path: str = ""  # memory files only


@dataclass
class Snapshot:
    model: str = ""
    total: int = 0
    window: int = 0
    categories: dict = field(default_factory=dict)  # name -> tokens, unknown names kept
    mcp_tools: list = field(default_factory=list)  # Item, source = server
    skills: list = field(default_factory=list)  # Item, source = Built-in / Plugin (x) / ...
    agents: list = field(default_factory=list)
    memory_files: list = field(default_factory=list)
    approx: bool = False  # True when built from `usage` only (total, no breakdown)


def _rows(lines):
    """Yield the cell lists of a markdown table body (header and separator skipped)."""
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines if ln.strip().startswith("|")]
    return rows[2:]


def _sections(md):
    """Split markdown into {heading: [lines]} on `###` headings; preamble under ''."""
    out, cur = {"": []}, ""
    for ln in md.splitlines():
        if ln.startswith("### "):
            cur = ln[4:].strip()
            out[cur] = []
        else:
            out[cur].append(ln)
    return out


def parse_context(md):
    """Parse the markdown of `/context` into a Snapshot."""
    if MARKER not in md:
        raise ValueError("not a /context output (no '%s')" % MARKER)
    snap = Snapshot()
    sec = _sections(md)
    for ln in sec[""]:
        m = re.match(r"\*\*Model:\*\*\s*(.+?)\s*$", ln)
        if m:
            snap.model = m.group(1)
        m = re.match(r"\*\*Tokens:\*\*\s*(\S+)\s*/\s*(\S+)", ln)
        if m:
            snap.total = parse_tokens(m.group(1))[0]
            snap.window = parse_tokens(m.group(2))[0]
    for row in _rows(sec.get("Estimated usage by category", [])):
        if len(row) >= 2:
            snap.categories[row[0]] = parse_tokens(row[1])[0]
    for row in _rows(sec.get("MCP Tools", [])):
        t, a = parse_tokens(row[2])
        snap.mcp_tools.append(Item(row[0], t, row[1], a))
    for row in _rows(sec.get("Skills", [])):
        t, a = parse_tokens(row[2])
        snap.skills.append(Item(row[0], t, row[1], a))
    for row in _rows(sec.get("Custom Agents", [])):
        t, a = parse_tokens(row[2])
        snap.agents.append(Item(row[0], t, row[1], a))
    for row in _rows(sec.get("Memory Files", [])):
        t, a = parse_tokens(row[2])
        snap.memory_files.append(Item(row[1], t, row[0], a, path=row[1]))
    return snap


def read_headless(path_or_text):
    """Read the JSON of `claude -p "/context" --output-format json` into a Snapshot.

    Raises ValueError when the run was not free (total_cost_usd != 0 or num_turns != 0).
    """
    text = path_or_text
    if isinstance(path_or_text, Path):
        text = path_or_text.read_text()
    data = json.loads(text)
    if data.get("total_cost_usd") != 0 or data.get("num_turns") != 0:
        raise ValueError("headless /context was not free: cost=%r turns=%r"
                         % (data.get("total_cost_usd"), data.get("num_turns")))
    return parse_context(data["result"])


def project_key(project_dir):
    """Transcript folder name of a project: every non-alphanumeric character becomes `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(project_dir))


def transcripts_dir(project_dir, projects_root=None):
    root = Path(projects_root) if projects_root else Path.home() / ".claude" / "projects"
    return root / project_key(project_dir)


@dataclass
class Found:
    snapshot: Snapshot
    session: str
    timestamp: str
    source: str  # "context" (interactive /context) or "usage" (first-turn fallback)


def _records(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            try:
                yield json.loads(ln)
            except ValueError:
                continue


def _text(rec):
    c = (rec.get("message") or {}).get("content")
    return c if isinstance(c, str) else ""


def latest_context_in(path):
    """Newest interactive /context in one transcript as (markdown, timestamp), or None.

    Only `type: user` + `isMeta: true` records count; the `system`/`local_command`
    records carry the ANSI version and are ignored.
    """
    best = None
    for rec in _records(path):
        if rec.get("type") == "user" and rec.get("isMeta") and _text(rec).lstrip().startswith(MARKER):
            best = (_text(rec), rec.get("timestamp", ""))
    return best


def first_turn_total(path):
    """Total from the first assistant turn's usage, as (total, model, timestamp), or None."""
    for rec in _records(path):
        if rec.get("type") != "assistant" or rec.get("isSidechain"):
            continue
        msg = rec.get("message") or {}
        u = msg.get("usage")
        if u:
            total = sum(int(u.get(k) or 0) for k in
                        ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            return total, msg.get("model", ""), rec.get("timestamp", "")
    return None


def latest_snapshot(project_dir, projects_root=None):
    """Latest interactive /context of a project, else the first-turn fallback, else None."""
    d = transcripts_dir(project_dir, projects_root)
    sessions = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
    for p in sessions:
        got = latest_context_in(p)
        if got:
            return Found(parse_context(got[0]), p.stem, got[1], "context")
    for p in sessions:
        got = first_turn_total(p)
        if got:
            total, model, ts = got
            return Found(Snapshot(model=model, total=total, approx=True), p.stem, ts, "usage")
    return None
