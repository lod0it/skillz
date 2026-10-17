#!/usr/bin/env python3
"""Token figures of the subagents this repo's sessions dispatched, read from
their transcripts at zero tokens.

    subagent_usage.py [--last N] [--project-dir DIR]

Per subagent: the context it started from (system prompt, tools, first
prompt), the peak context, the turns, the cache reads. `output_tokens` is
partial in these files and is not reported. Standard library only.
"""

import argparse
import json
import re
import sys
from pathlib import Path

PEAK_WARN = 120_000  # above this the task was cut too large for one context window


def project_dir(cwd):
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def read(path):
    start = peak = turns = cache_read = 0
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
            turns += 1
            cache_read += usage.get("cache_read_input_tokens", 0)
    meta = path.with_name(path.name.replace(".jsonl", ".meta.json"))
    agent = json.loads(meta.read_text(encoding="utf-8")).get("agentType", "?") if meta.is_file() else "?"
    return {"agent": agent, "model": model, "start": start, "peak": peak, "turns": turns,
            "cache_read": cache_read, "prompt": " ".join(prompt.split())[:48]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--last", type=int, default=5, help="how many of the most recent subagents (default 5)")
    parser.add_argument("--project-dir", help="transcript folder (default: the one of the current directory)")
    args = parser.parse_args(argv)
    folder = Path(args.project_dir) if args.project_dir else project_dir(Path.cwd())
    files = sorted(folder.glob("*/subagents/agent-*.jsonl"), key=lambda p: p.stat().st_mtime)[-args.last:]
    if not files:
        print(f"no subagent transcript under {folder}")
        return 1
    print(f"{'agent':<16} {'model':<20} {'start':>7} {'peak':>8} {'turns':>5} {'cache reads':>12}  prompt")
    for path in files:
        row = read(path)
        flag = "  <- peak over 120k: the task was too large" if row["peak"] > PEAK_WARN else ""
        print(f"{row['agent']:<16} {row['model']:<20} {row['start']:>7} {row['peak']:>8} {row['turns']:>5} "
              f"{row['cache_read']:>12}  {row['prompt']}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
