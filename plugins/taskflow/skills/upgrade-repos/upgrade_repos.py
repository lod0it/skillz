#!/usr/bin/env python3
"""Find the repos whose taskflow layout is older than the installed plugin, and bring them up to date.

Usage:
  upgrade_repos.py scan [DIR] [--json]          list the taskflow repos at DIR (default: cwd), its children and its siblings
  upgrade_repos.py apply REPO... [--commit]     init + migrate-tool + check in each repo; --commit makes one local commit
  upgrade_repos.py hint                         SessionStart hook: JSON for Claude when an old repo is near; silent otherwise
  upgrade_repos.py snooze REPO...               stop hinting about these repos until the next taskflow version

Never pushes. Standard library only.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent
TASKS_PY = PLUGIN / "skills" / "break-it-down" / "tasks.py"
SNOOZE = Path.home() / ".claude" / "taskflow" / "upgrade_snooze.json"
SCAN_CAP = 80
UPGRADE_PATHS = ("TASKS.md", ".claude/agents/implementer.md", "tasks")

sys.path.insert(0, str(TASKS_PY.parent))
import tasks  # noqa: E402


def plugin_version():
    try:
        return (PLUGIN / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def is_taskflow_repo(path):
    md = Path(path) / "TASKS.md"
    try:
        return re.search(r"^## Task system\s*$", md.read_text(encoding="utf-8"), re.M) is not None
    except OSError:
        return False


def candidates(base):
    """base, its children and its siblings: the cheap neighbourhood of a session."""
    base = Path(base).resolve()
    seen, out = set(), []
    for root in (base, *base.iterdir(), *(base.parent.iterdir() if base.parent != base else ())):
        try:
            if root.is_dir() and not root.name.startswith(".") and root.name != "node_modules" and root not in seen:
                seen.add(root)
                out.append(root)
        except OSError:
            continue
        if len(out) >= SCAN_CAP:
            break
    return out


def assess(repo):
    """{'repo', 'state': ok|auto|manual, 'reasons': [...]}: auto = init + migrate-tool fixes it,
    manual = an older layout that needs the migrate branch of /taskflow:break-it-down."""
    repo = Path(repo)
    board = tasks.Board(repo)
    errors, warnings = tasks.check(board)
    reasons, manual = [], False
    for line in errors:
        if line.startswith("LEGACY"):
            manual = True
            reasons.append(line)
        elif line.startswith("OLD-TOOL") or "(run `init`)" in line:
            reasons.append(line)
    reasons += [w for w in warnings if "LESSONS" in w]
    state = "ok" if not reasons else "manual" if manual else "auto"
    return {"repo": str(repo), "state": state, "reasons": reasons}


def scan(base):
    return [assess(p) for p in candidates(base) if is_taskflow_repo(p)]


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def run_tool(repo, *args):
    r = subprocess.run([sys.executable, str(TASKS_PY), "--root", str(repo), *args],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout.strip()


def apply_repo(repo, commit=False):
    """Returns (status, detail). Skips a repo with uncommitted changes so the commit holds only the upgrade."""
    repo = Path(repo)
    if not is_taskflow_repo(repo):
        return "skipped", "no `## Task system` in TASKS.md"
    is_git = git(repo, "rev-parse", "--is-inside-work-tree")[0] == 0
    if is_git and git(repo, "status", "--porcelain")[1]:
        return "skipped", "uncommitted changes: commit or stash them first"
    before = assess(repo)
    if before["state"] == "manual":
        return "manual", "older layout: run /taskflow:break-it-down in this repo (migrate branch)"
    if before["state"] == "ok":
        return "ok", "already up to date"
    run_tool(repo, "init")
    run_tool(repo, "migrate-tool")
    code, out = run_tool(repo, "check")
    summary = out.splitlines()[-1] if out else "check printed nothing"
    if code:
        return "check-failed", summary
    if commit and is_git:
        git(repo, "add", "--", *[p for p in UPGRADE_PATHS if (repo / p).exists()])
        if git(repo, "diff", "--cached", "--quiet")[0] == 0:
            return "upgraded", f"{summary}; nothing to commit"
        rc, msg = git(repo, "commit", "-m", f"taskflow: upgrade to {plugin_version()} "
                      "(LESSONS.md with Project and General sections, current Tool paths)")
        return ("upgraded", f"{summary}; committed, not pushed") if rc == 0 else ("check-failed", f"commit failed: {msg}")
    return "upgraded", f"{summary}; changes left uncommitted"


def load_snooze():
    try:
        return json.loads(SNOOZE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def snooze(repos):
    data = load_snooze()
    for r in repos:
        data[str(Path(r).resolve())] = plugin_version()
    SNOOZE.parent.mkdir(parents=True, exist_ok=True)
    SNOOZE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def hint(base):
    snoozed = load_snooze()
    old = [a for a in scan(base) if a["state"] != "ok" and snoozed.get(a["repo"]) != plugin_version()]
    if not old:
        return None
    lines = "\n".join(f"- {a['repo']} ({a['state']}): {a['reasons'][0]}" for a in old)
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": (
        f"taskflow {plugin_version()} is installed, and these repos near this session still use an older "
        f"taskflow layout:\n{lines}\n"
        "Before anything else, tell the user in one line and ask with AskUserQuestion whether to run "
        "/taskflow:upgrade-repos now (options: upgrade, dry run first, not now). Do not upgrade anything unasked.")}}


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    flags = {a for a in rest if a.startswith("--")}
    args = [a for a in rest if not a.startswith("--")]
    if cmd == "scan":
        report = scan(args[0] if args else os.getcwd())
        if "--json" in flags:
            print(json.dumps({"version": plugin_version(), "repos": report}, indent=2))
        else:
            for a in report:
                print(f"{a['state']:7} {a['repo']}")
                for r in a["reasons"]:
                    print(f"        {r}")
            print(f"{len(report)} taskflow repos, {sum(a['state'] != 'ok' for a in report)} to upgrade (taskflow {plugin_version()})")
        return 0
    if cmd == "apply":
        for repo in args:
            status, detail = apply_repo(repo, commit="--commit" in flags)
            print(f"{status:12} {repo}: {detail}")
        return 0
    if cmd == "snooze":
        snooze(args)
        return 0
    if cmd == "hint":
        try:
            out = hint(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        except Exception:
            out = None
        if out:
            print(json.dumps(out))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
