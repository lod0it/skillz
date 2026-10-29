#!/usr/bin/env python3
"""Token figures of the subagents this repo's sessions dispatched, read from
their transcripts at zero tokens.

    subagent_usage.py [--last N] [--task ID] [--ids] [--project-dir DIR]

`--task ID` keeps the subagents whose first prompt starts `<verb> Task ID:`.
`--ids` prints one line per subagent, `<agent id> <role> <prompt>`, newest last:
the ids the Loop passes to `TaskStop` once a task has its verdict, so that no
agent outlives its task (stopping one that already finished is harmless).

Per subagent: the context it started from (system prompt, tools, first
prompt), the peak context, the turns, the cache reads. The last line is the
current context of the session running the Loop (the most recent top-level
transcript): past 150k the Loop stops and asks for a fresh session.
`output_tokens` is partial in these files and is not reported. Standard
library only.
"""

import argparse
import json
import re
import sys
from pathlib import Path

PEAK_WARN = 120_000  # above this the task was cut too large for one context window
SESSION_WARN = 150_000  # above this the orchestrating session is too worn to go on


def project_dir(cwd):
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def read(path):
    start = peak = turns = cache_read = current = 0
    model = prompt = ""
    seen = set()
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") or {}
            if entry.get("type") == "user" and not prompt:
                content = message.get("content")
                prompt = content if isinstance(content, str) else " ".join(
                    part.get("text", "") for part in content or [] if isinstance(part, dict))
            usage = message.get("usage")
            if entry.get("type") != "assistant" or not usage or message.get("id") in seen:
                continue
            seen.add(message.get("id"))
            model = message.get("model", model)
            context = (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                       + usage.get("cache_read_input_tokens", 0))
            start = start or context
            peak = max(peak, context)
            current = context
            turns += 1
            cache_read += usage.get("cache_read_input_tokens", 0)
    meta = path.with_name(path.name.replace(".jsonl", ".meta.json"))
    agent = json.loads(meta.read_text(encoding="utf-8")).get("agentType", "?") if meta.is_file() else "?"
    return {"id": path.stem.removeprefix("agent-"), "agent": agent, "model": model, "start": start, "peak": peak, "turns": turns,
            "cache_read": cache_read, "current": current, "prompt": " ".join(prompt.split())[:48], "full_prompt": " ".join(prompt.split())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--last", type=int, default=5, help="how many of the most recent subagents (default 5)")
    parser.add_argument("--project-dir", help="transcript folder (default: the one of the current directory)")
    parser.add_argument("--task", help="only the subagents dispatched for this task id")
    parser.add_argument("--ids", action="store_true", help="print agent ids to stop, not token figures")
    args = parser.parse_args(argv)
    folder = Path(args.project_dir) if args.project_dir else project_dir(Path.cwd())
    files = sorted(folder.glob("*/subagents/agent-*.jsonl"), key=lambda p: p.stat().st_mtime)
    rows = [(path, read(path)) for path in files]
    if args.task:
        pattern = re.compile(rf"Task {re.escape(args.task)}:")
        rows = [(path, row) for path, row in rows if pattern.search(row["full_prompt"][:120])]
    rows = rows[-args.last:]
    if not rows:
        print(f"no subagent transcript under {folder}")
        return 1
    if args.ids:
        for _, row in rows:
            print(f"{row['id']} {row['agent']} {row['prompt']}")
        return 0
    print(f"{'agent':<16} {'model':<20} {'start':>7} {'peak':>8} {'turns':>5} {'cache reads':>12}  prompt")
    for _, row in rows:
        flag = "  <- peak over 120k: the task was too large" if row["peak"] > PEAK_WARN else ""
        print(f"{row['agent']:<16} {row['model']:<20} {row['start']:>7} {row['peak']:>8} {row['turns']:>5} "
              f"{row['cache_read']:>12}  {row['prompt']}{flag}")
    sessions = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if sessions:
        current = read(sessions[-1])["current"]
        verdict = ("over 150k: stop the Loop, ask for /clear and a new /taskflow:loop-it"
                   if current > SESSION_WARN else "ok")
        print(f"this session's context: {current} ({verdict})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
