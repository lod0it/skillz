"""Usage counts from session transcripts: skills invoked, tools called, MCP servers.

Facts only (design Q5). Per-file counts are cached in ~/.claude/residency-usage-cache.json
keyed by path with mtime and size, so only changed transcripts are re-read.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import snapshot

DEFAULT_N = 30
_COMMAND = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")
_MCP = re.compile(r"^mcp__(.+?)__.+$")


@dataclass
class Counts:
    skills: dict = field(default_factory=dict)
    tools: dict = field(default_factory=dict)
    mcp: dict = field(default_factory=dict)  # server -> calls

    def add(self, other):
        for mine, theirs in ((self.skills, other.skills), (self.tools, other.tools),
                             (self.mcp, other.mcp)):
            for k, v in theirs.items():
                mine[k] = mine.get(k, 0) + v

    def to_json(self):
        return {"skills": self.skills, "tools": self.tools, "mcp": self.mcp}

    @classmethod
    def from_json(cls, d):
        return cls(dict(d.get("skills", {})), dict(d.get("tools", {})), dict(d.get("mcp", {})))


def default_cache_path():
    return Path.home() / ".claude" / "residency-usage-cache.json"


def _bump(d, k):
    d[k] = d.get(k, 0) + 1


def scan_file(path):
    """Count skills, tools and MCP servers in one transcript (sub-agent calls included)."""
    c = Counts()
    seen = set()
    for rec in snapshot._records(path):
        if not isinstance(rec, dict):
            continue
        content = (rec.get("message") or {}).get("content") if isinstance(
            rec.get("message"), dict) else None
        if rec.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                bid = b.get("id")
                if bid:
                    if bid in seen:
                        continue
                    seen.add(bid)
                name = b.get("name")
                if not isinstance(name, str):
                    continue
                _bump(c.tools, name)
                m = _MCP.match(name)
                if m:
                    _bump(c.mcp, m.group(1))
                if name == "Skill":
                    sk = (b.get("input") or {}).get("skill")
                    if isinstance(sk, str) and sk:
                        _bump(c.skills, sk.lstrip("/"))
        elif rec.get("type") == "user":
            texts = [content] if isinstance(content, str) else [
                b.get("text", "") for b in content or []
                if isinstance(b, dict) and b.get("type") == "text"]
            for t in texts:
                for m in _COMMAND.finditer(t if isinstance(t, str) else ""):
                    _bump(c.skills, m.group(1))
    return c


def _load(cache_path):
    try:
        d = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def recent_files(project_dirs, n=DEFAULT_N):
    files = []
    for d in project_dirs:
        for p in Path(d).glob("*.jsonl"):
            try:
                files.append((p.stat().st_mtime, str(p)))
            except OSError:
                pass
    files.sort(reverse=True)
    return [Path(p) for _, p in files[:n]]


def aggregate(files, cache_path=None, scanner=None):
    """Sum counts over files, re-scanning only those whose mtime or size changed."""
    scanner = scanner or scan_file
    cache_path = Path(cache_path) if cache_path else default_cache_path()
    cache = _load(cache_path)
    entries = cache.get("files") if isinstance(cache.get("files"), dict) else {}
    total, dirty = Counts(), False
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        e = entries.get(str(f))
        if (isinstance(e, dict) and e.get("mtime") == st.st_mtime and e.get("size") == st.st_size
                and isinstance(e.get("counts"), dict)):
            counts = Counts.from_json(e["counts"])
        else:
            counts = scanner(f)
            entries[str(f)] = {"mtime": st.st_mtime, "size": st.st_size,
                               "counts": counts.to_json()}
            dirty = True
        total.add(counts)
    if dirty:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"files": entries}), encoding="utf-8")
        except OSError:
            pass
    return total


def usage(scope="here", project_dir=None, n=DEFAULT_N, projects_root=None,
          cache_path=None, scanner=None):
    """Counts over the last n sessions (by mtime) of this project ('here') or all ('all')."""
    root = Path(projects_root) if projects_root else Path.home() / ".claude" / "projects"
    if scope == "all":
        dirs = [d for d in root.glob("*") if d.is_dir()] if root.is_dir() else []
    elif scope == "here":
        dirs = [snapshot.transcripts_dir(project_dir or Path.cwd(), root)]
    else:
        raise ValueError("scope must be 'here' or 'all'")
    return aggregate(recent_files(dirs, n), cache_path, scanner)
