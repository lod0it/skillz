#!/usr/bin/env python3
"""free_my_context - the mechanical half of /taskflow:free-my-context (zero tokens).

  free_my_context.py usage [--scope here|all] [--project DIR] [-n N]
  free_my_context.py apply SETTINGS PLAN.json [--dry-run]

usage: counts tools, MCP servers and skills called in the last N transcripts
(default 30) of the project ("here") or of every project ("all"), as JSON.

apply: merges PLAN.json {"deny": [], "skills": {name: state}, "plugins_off": []}
into SETTINGS. Existing keys stay, entries are added without duplicates, a
.bak-<time> copy is written first, and the core tools are refused.
Standard library only.
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

PROTECTED = {"Bash", "PowerShell", "Read", "Write", "Edit", "Skill", "ToolSearch",
             "AskUserQuestion", "free-my-context", "taskflow:free-my-context"}
STATES = {"on", "name-only", "user-invocable-only", "off"}
_MCP = re.compile(r"^mcp__(.+?)__.+$")
_COMMAND = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")


def transcripts_dir(project, root):
    """Claude Code names a project's transcript folder after its path."""
    return Path(root) / re.sub(r"[^A-Za-z0-9]", "-", str(Path(project).resolve()))


def _bump(d, k):
    d[k] = d.get(k, 0) + 1


def scan_file(path, out):
    seen = set()
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        msg = rec.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if rec.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                if b.get("id") in seen:
                    continue
                seen.add(b.get("id"))
                name = b.get("name")
                if not isinstance(name, str):
                    continue
                _bump(out["tools"], name)
                m = _MCP.match(name)
                if m:
                    _bump(out["mcp"], m.group(1))
                if name == "Skill":
                    sk = (b.get("input") or {}).get("skill")
                    if isinstance(sk, str) and sk:
                        _bump(out["skills"], sk.lstrip("/"))
        elif rec.get("type") == "user":
            texts = [content] if isinstance(content, str) else [
                b.get("text", "") for b in content or []
                if isinstance(b, dict) and b.get("type") == "text"]
            for t in texts:
                for m in _COMMAND.finditer(t if isinstance(t, str) else ""):
                    _bump(out["skills"], m.group(1))


def usage(scope="here", project=None, n=30, root=None):
    root = Path(root) if root else Path.home() / ".claude" / "projects"
    if scope == "all":
        dirs = [d for d in root.glob("*") if d.is_dir()] if root.is_dir() else []
    else:
        dirs = [transcripts_dir(project or Path.cwd(), root)]
    files = []
    for d in dirs:
        for p in d.glob("*.jsonl"):
            try:
                files.append((p.stat().st_mtime, p))
            except OSError:
                pass
    files.sort(reverse=True)
    out = {"tools": {}, "mcp": {}, "skills": {}, "sessions": min(n, len(files))}
    for _, p in files[:n]:
        scan_file(p, out)
    return out


def apply(settings, plan, dry_run=False):
    """Merge plan into the settings file; return the new data (written unless dry_run)."""
    settings = Path(settings)
    bad = PROTECTED & (set(plan.get("deny", [])) | set(plan.get("skills", {})))
    if bad:
        raise ValueError(f"protected, never switched off: {sorted(bad)}")
    for name, state in plan.get("skills", {}).items():
        if state not in STATES:
            raise ValueError(f"skill {name!r}: state {state!r} is not one of {sorted(STATES)}")
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    if plan.get("deny"):
        deny = data.setdefault("permissions", {}).setdefault("deny", [])
        for t in plan["deny"]:
            if t not in deny:
                deny.append(t)
    if plan.get("skills"):
        data.setdefault("skillOverrides", {}).update(plan["skills"])
    if plan.get("plugins_off"):
        data.setdefault("enabledPlugins", {}).update({p: False for p in plan["plugins_off"]})
    if not dry_run:
        if settings.exists():
            shutil.copy2(settings, settings.with_name(
                f"{settings.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}"))
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("usage")
    u.add_argument("--scope", choices=("here", "all"), default="here")
    u.add_argument("--project")
    u.add_argument("-n", type=int, default=30)
    a = sub.add_parser("apply")
    a.add_argument("settings")
    a.add_argument("plan")
    a.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "usage":
            print(json.dumps(usage(args.scope, args.project, args.n), indent=2))
        else:
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            data = apply(args.settings, plan, args.dry_run)
            print(json.dumps(data, indent=2, ensure_ascii=False) if args.dry_run
                  else f"updated {args.settings}")
    except (OSError, ValueError) as e:
        print(f"free_my_context: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
