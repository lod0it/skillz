#!/usr/bin/env python3
"""refine coverage: which lines of a script the cases execute.

usage:
  refine coverage <script> <cases.json> [--scratch DIR] [--python PY] [--timeout S]
  refine coverage --probe <script> [--scratch DIR] [--python PY]

The language comes from the extension, then from the shebang. The cases
(same cases.json as `refine golden`, see `refine golden --help`) run one by
one, each in a fresh temporary directory, under the language's coverage
tool. Only lines of <script> itself are reported: imported modules and
sourced files are ignored.

Output is one JSON object:
  {"language", "tool", "mode": "measured", "covered": [line numbers],
   "cases": N, "unmapped_cases": [names], "failed_cases": [names]}
  {"language", "tool", "mode": "unavailable", "reason", "install_hint"}

Adapters:
  python  coverage.py (`python -m coverage run`, then `coverage json`); the
          interpreter is --python, else <scratch>/venv/bin/python, else
          python3, the first one that imports `coverage`.
  shell   `bash -x` with a PS4 that tags each trace line with file:line.
  node    c8 (JS and TS), from node_modules/.bin next to the script or above
          it, <scratch>/node/node_modules/.bin, or PATH. Never downloaded.
  go      `go test -coverprofile` in the script's package; needs *_test.go
          files there. The cases are not used: the package tests drive it.

A case is "unmapped" when none of its argv items is the script's absolute
path (after {root} expansion) and the adapter needs to wrap the script
(python, shell): it is not run. A case is "failed" when the tool produced
no data for it. --scratch (default: $TMPDIR/refine-tools) is where the
install_hint puts tools; it is never global.

Exit codes: 0 measured; 3 unavailable (no usable tool: install_hint is a
local install command, or null when there is none); 2 usage or cases.json
errors, or no case runs the script. --probe prints
{"language", "tool", "available", "reason", "install_hint"} and exits 0 when
available, 3 otherwise.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import golden

EXTENSIONS = {
    ".py": "python", ".pyw": "python",
    ".sh": "shell", ".bash": "shell",
    ".js": "node", ".mjs": "node", ".cjs": "node", ".jsx": "node",
    ".ts": "node", ".mts": "node", ".cts": "node", ".tsx": "node",
    ".go": "go",
}
SHEBANGS = {
    "python": "python", "python3": "python", "python2": "python",
    "sh": "shell", "bash": "shell", "dash": "shell",
    "node": "node", "nodejs": "node", "tsx": "node", "ts-node": "node",
    "zsh": "zsh", "ruby": "ruby", "perl": "perl",
}
TOOLS = {"python": "coverage.py", "shell": "bash -x", "node": "c8", "go": "go test -cover"}
PS4_TAG = "[refine-cov]"


class Unavailable(Exception):
    def __init__(self, reason, install_hint=None):
        super().__init__(reason)
        self.reason = reason
        self.install_hint = install_hint


# ---------------------------------------------------------------- language

def shebang_language(script):
    try:
        with open(script, "rb") as f:
            first = f.readline(256).decode("utf-8", "replace").strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    words = first[2:].split()
    if not words:
        return None
    if Path(words[0]).name == "env":
        words = [w for w in words[1:] if not w.startswith("-") and "=" not in w]
        if not words:
            return None
    name = Path(words[0]).name
    if name in SHEBANGS:
        return SHEBANGS[name]
    m = re.match(r"(python)[0-9.]*$", name)
    return "python" if m else name


def detect_language(script):
    ext = Path(script).suffix.lower()
    if ext in EXTENSIONS:
        return EXTENSIONS[ext]
    return shebang_language(script) or (ext.lstrip(".") or "unknown")


# ---------------------------------------------------------------- tools

def default_scratch():
    return Path(tempfile.gettempdir()) / "refine-tools"


def _imports_coverage(python):
    try:
        r = subprocess.run([python, "-c", "import coverage"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def find_python(scratch, python=None):
    candidates = [python] if python else [
        str(Path(scratch) / "venv" / "bin" / "python"), shutil.which("python3")]
    for c in candidates:
        if c and (os.sep not in c or Path(c).exists()) and _imports_coverage(c):
            return c
    venv = Path(scratch) / "venv"
    hint = (f"python3 -m venv {shlex.quote(str(venv))} && "
            f"{shlex.quote(str(venv / 'bin' / 'python'))} -m pip install coverage")
    which = f"'{python}'" if python else "python3"
    raise Unavailable(f"coverage.py is not importable by {which}", hint)


def find_c8(script, scratch):
    d = Path(script).resolve().parent
    for parent in [d, *d.parents]:
        c = parent / "node_modules" / ".bin" / "c8"
        if c.exists():
            return str(c)
    c = Path(scratch) / "node" / "node_modules" / ".bin" / "c8"
    if c.exists():
        return str(c)
    found = shutil.which("c8")
    if found:
        return found
    node_dir = Path(scratch) / "node"
    if not shutil.which("npm"):
        raise Unavailable("c8 not found and npm is not installed", None)
    raise Unavailable("c8 not found",
                      f"npm install --prefix {shlex.quote(str(node_dir))} c8")


def find_go(script, scratch):
    go = shutil.which("go")
    local = Path(scratch) / "go" / "bin" / "go"
    if not go and local.exists():
        go = str(local)
    if not go:
        raise Unavailable(
            "go is not installed",
            f"download a Go archive from https://go.dev/dl/ and extract it into "
            f"{shlex.quote(str(Path(scratch)))} (it creates go/bin/go)")
    if not list(Path(script).resolve().parent.glob("*_test.go")):
        raise Unavailable("no *_test.go files in the script's package", None)
    return go


def find_tool(language, script, scratch, python=None):
    """Return the tool executable for the language, or raise Unavailable."""
    if language == "python":
        return find_python(scratch, python)
    if language == "shell":
        bash = shutil.which("bash")
        if not bash:
            raise Unavailable("bash is not installed", None)
        return bash
    if language == "node":
        return find_c8(script, scratch)
    if language == "go":
        return find_go(script, scratch)
    raise Unavailable(f"no coverage adapter for language '{language}'", None)


# ---------------------------------------------------------------- runs

def wrap_argv(argv, script, prefix):
    """Replace everything up to the item that names the script with prefix +
    [script]. Returns None when no argv item is the script."""
    for i, a in enumerate(argv):
        if os.path.isabs(a) and Path(a).resolve() == script:
            return prefix + [str(script)] + argv[i + 1:]
    return None


# bash 3.2 truncates a long PS4 expansion, so the script's path is not
# printed: PS4 strips it from BASH_SOURCE, leaving "" for the script itself
# and a non-empty rest for any other (sourced) file.
PS4 = f'+{PS4_TAG}${{LINENO}}:${{BASH_SOURCE#"$REFINE_COV_SCRIPT"}}: '
BASH_LINE_RE = re.compile(r"^\++" + re.escape(PS4_TAG) + r"(\d+):: ")


def bash_lines(stderr):
    """Line numbers of the script in a bash -x trace written with PS4."""
    lines = set()
    for raw in stderr.decode("utf-8", "replace").splitlines():
        m = BASH_LINE_RE.match(raw)
        if m:
            lines.add(int(m.group(1)))
    return lines


def run_shell(cases, script, bash, timeout):
    covered, unmapped, failed = set(), [], []
    for case in cases:
        argv = wrap_argv(case["argv"], script, [bash, "-x"])
        if argv is None:
            unmapped.append(case["name"])
            continue
        env = dict(case["env"], PS4=PS4, REFINE_COV_SCRIPT=str(script))
        result = golden.run_case(dict(case, argv=argv, env=env), timeout)
        lines = bash_lines(result["stderr"])
        if not lines:
            failed.append(case["name"])
        covered |= lines
    return covered, unmapped, failed


def _report_lines(files, script, base):
    """Pick `script`'s entry from a report keyed by (maybe relative) paths."""
    for name, entry in files.items():
        p = Path(name)
        if not p.is_absolute():
            p = Path(base) / p
        if p.resolve() == script:
            return entry
    return None


def run_python(cases, script, python, timeout):
    covered, unmapped, failed = set(), [], []
    with tempfile.TemporaryDirectory(prefix="refine-cov-") as tmp:
        for n, case in enumerate(cases):
            data = Path(tmp) / f"data-{n}"
            prefix = [python, "-m", "coverage", "run", f"--data-file={data}",
                      f"--include={script}"]
            argv = wrap_argv(case["argv"], script, prefix)
            if argv is None:
                unmapped.append(case["name"])
                continue
            golden.run_case(dict(case, argv=argv), timeout)
            report = Path(tmp) / f"report-{n}.json"
            if data.exists():
                subprocess.run([python, "-m", "coverage", "json", f"--data-file={data}",
                                "-o", str(report), f"--include={script}"],
                               cwd=script.parent, capture_output=True, timeout=timeout)
            entry = None
            if report.exists():
                files = json.loads(report.read_text(encoding="utf-8")).get("files", {})
                entry = _report_lines(files, script, script.parent)
            if not entry:
                failed.append(case["name"])
                continue
            covered |= set(entry.get("executed_lines", []))
    return covered, unmapped, failed


def istanbul_lines(entry):
    """Covered line numbers from one file of an istanbul coverage-final.json."""
    lines = set()
    for sid, count in entry.get("s", {}).items():
        loc = entry.get("statementMap", {}).get(sid)
        if count and loc:
            lines.add(loc["start"]["line"])
    return lines


def run_node(cases, script, c8, timeout):
    covered, failed = set(), []
    with tempfile.TemporaryDirectory(prefix="refine-cov-") as tmp:
        for n, case in enumerate(cases):
            report_dir = Path(tmp) / f"report-{n}"
            argv = [c8, "--reporter=json", f"--report-dir={report_dir}",
                    f"--temp-directory={Path(tmp) / f'v8-{n}'}",
                    # the run's cwd is a temp dir: allow reporting the script outside it
                    "--allowExternal", *case["argv"]]
            golden.run_case(dict(case, argv=argv), timeout)
            report = report_dir / "coverage-final.json"
            entry = None
            if report.exists():
                files = json.loads(report.read_text(encoding="utf-8"))
                entry = _report_lines(files, script, script.parent)
            if not entry:
                failed.append(case["name"])
                continue
            covered |= istanbul_lines(entry)
    return covered, [], failed


def goprofile_lines(text, filename):
    """Covered line numbers of `filename` (a base name) in a Go cover profile."""
    lines = set()
    for row in text.splitlines():
        m = re.match(r"(.+):(\d+)\.\d+,(\d+)\.\d+ \d+ (\d+)$", row)
        if m and Path(m.group(1)).name == filename and int(m.group(4)) > 0:
            lines.update(range(int(m.group(2)), int(m.group(3)) + 1))
    return lines


def run_go(script, go, timeout):
    with tempfile.TemporaryDirectory(prefix="refine-cov-") as tmp:
        profile = Path(tmp) / "cover.out"
        try:
            subprocess.run([go, "test", f"-coverprofile={profile}", "."], cwd=script.parent,
                           capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
        if not profile.exists():
            return set(), [], ["go test"]
        return goprofile_lines(profile.read_text(encoding="utf-8"), script.name), [], []


# ---------------------------------------------------------------- commands

def parse_args(argv):
    opts = {"scratch": None, "python": None, "timeout": golden.DEFAULT_TIMEOUT, "probe": False}
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--probe":
            opts["probe"] = True
            i += 1
            continue
        key = next((k for k in ("scratch", "python", "timeout")
                    if a == f"--{k}" or a.startswith(f"--{k}=")), None)
        if key is None:
            rest.append(a)
            i += 1
            continue
        if "=" in a:
            value, i = a.split("=", 1)[1], i + 1
        elif i + 1 < len(argv):
            value, i = argv[i + 1], i + 2
        else:
            raise ValueError(f"--{key} needs a value")
        if key == "timeout":
            value = float(value)
            if value <= 0:
                raise ValueError("--timeout must be positive")
        opts[key] = value
    return opts, rest


def emit(obj):
    print(json.dumps(obj, indent=2))


def main(argv):
    argv = list(argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    try:
        opts, args = parse_args(argv)
    except ValueError as e:
        print(f"coverage: {e}", file=sys.stderr)
        return 2
    if len(args) != (1 if opts["probe"] else 2):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    script = Path(args[0]).resolve()
    if not script.is_file():
        print(f"coverage: {args[0]}: not a file", file=sys.stderr)
        return 2
    scratch = Path(opts["scratch"]).resolve() if opts["scratch"] else default_scratch()
    language = detect_language(script)
    tool_name = TOOLS.get(language)
    try:
        tool = find_tool(language, script, scratch, opts["python"])
    except Unavailable as u:
        out = {"language": language, "tool": tool_name}
        out.update({"available": False} if opts["probe"] else {"mode": "unavailable"})
        out.update({"reason": u.reason, "install_hint": u.install_hint})
        emit(out)
        return 3
    if opts["probe"]:
        emit({"language": language, "tool": tool_name, "available": True,
              "reason": None, "install_hint": None})
        return 0
    try:
        cases = golden.load_cases(args[1])
    except golden.CasesError as e:
        print(f"coverage: {e}", file=sys.stderr)
        return 2
    timeout = opts["timeout"]
    if language == "shell":
        covered, unmapped, failed = run_shell(cases, script, tool, timeout)
    elif language == "python":
        covered, unmapped, failed = run_python(cases, script, tool, timeout)
    elif language == "node":
        covered, unmapped, failed = run_node(cases, script, tool, timeout)
    else:
        covered, unmapped, failed = run_go(script, tool, timeout)
    if unmapped and len(unmapped) == len(cases):
        print(f"coverage: no case runs {script} by its absolute path "
              f"(use \"{{root}}/...\" in argv)", file=sys.stderr)
        return 2
    emit({"language": language, "tool": tool_name, "mode": "measured",
          "covered": sorted(covered), "cases": len(cases),
          "unmapped_cases": unmapped, "failed_cases": failed})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
