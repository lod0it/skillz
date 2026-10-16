#!/usr/bin/env python3
"""refine measure: size of a source file, and optionally its runtime.

usage: refine measure <file> [--time <cases.json>] [--timeout S]

Prints one JSON object:
  {"file": ..., "lines": N, "total_lines": N, "tokens": N}
plus, with --time, "time_s": the median over 5 runs of the summed wall time
of every case in cases.json (format: see `refine golden --help`; only the
processes are timed, not the sandbox setup).

- lines: lines that are neither blank nor comment-only. A comment-only line
  starts (after indentation) with `#`, `//`, `--` or `;`. Block comments
  (/* */, triple-quoted docstrings, ...) are not recognised and count as
  code; trailing comments stay part of their line.
- tokens: lexemes on those same lines, language-agnostic: identifiers,
  numbers, string literals (one token each, '...', "..." or `...` on one
  line) and operators/punctuation (common multi-character operators count
  once). Not a model tokenizer: it is meant for before/after comparison of
  the same file, so consistency matters more than fidelity.

Exit codes: 0 ok; 1 when a timed case times out; 2 on usage or input errors.
"""
import json
import statistics
import sys
from pathlib import Path
import re

import golden

RUNS = 5
COMMENT_PREFIXES = ("#", "//", "--", ";")
TOKEN_RE = re.compile(r"""
    "(?:\\.|[^"\\\n])*"                     # double-quoted string
  | '(?:\\.|[^'\\\n])*'                     # single-quoted string
  | `(?:\\.|[^`\\\n])*`                     # backtick string
  | \d[\w.]*                                # number (0x1f, 1.5, 1_000, 2e9)
  | [^\W\d]\w*                              # identifier / keyword
  | \.\.\.|\*\*=|//=|>>=|<<=|===|!==        # three-char operators
  | ==|!=|<=|>=|->|=>|::|:=|\*\*|//|&&|\|\||<<|>>|\+\+|--|[-+*/%&|^]=
  | \S                                      # any other punctuation
""", re.VERBOSE)


def is_comment_only(stripped):
    return stripped.startswith(COMMENT_PREFIXES)


def measure_text(text):
    lines = text.splitlines()
    code = [l for l in lines if l.strip() and not is_comment_only(l.strip())]
    tokens = sum(len(TOKEN_RE.findall(l)) for l in code)
    return {"lines": len(code), "total_lines": len(lines), "tokens": tokens}


def time_cases(cases, runs=RUNS, timeout=golden.DEFAULT_TIMEOUT):
    """Median over `runs` of the summed process wall time of all cases.
    Returns (seconds, None) or (None, name of the case that timed out)."""
    totals = []
    for _ in range(runs):
        total = 0.0
        for case in cases:
            result = golden.run_case(case, timeout)
            if result["timeout"]:
                return None, case["name"]
            total += result["elapsed"]
        totals.append(total)
    return statistics.median(totals), None


def main(argv):
    argv = list(argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    try:
        timeout, args = golden.parse_timeout(argv)
    except ValueError as e:
        print(f"measure: {e}", file=sys.stderr)
        return 2
    cases_path = None
    if "--time" in args:
        i = args.index("--time")
        if i + 1 >= len(args):
            print("measure: --time needs a cases.json", file=sys.stderr)
            return 2
        cases_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print("usage: refine measure <file> [--time <cases.json>] [--timeout S]", file=sys.stderr)
        return 2
    path = Path(args[0])
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"measure: {e}", file=sys.stderr)
        return 2
    report = {"file": str(path), **measure_text(text)}
    if cases_path is not None:
        try:
            cases = golden.load_cases(cases_path)
        except golden.CasesError as e:
            print(f"measure: {e}", file=sys.stderr)
            return 2
        seconds, timed_out = time_cases(cases, timeout=timeout)
        if timed_out:
            print(f"measure: case '{timed_out}' timed out after {timeout:g} s", file=sys.stderr)
            return 1
        report["time_s"] = round(seconds, 4)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
