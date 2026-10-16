#!/usr/bin/env python3
"""refine golden: record a script's observable behaviour, then verify it.

usage:
  refine golden record <cases.json> <dir> [--timeout S]
  refine golden verify <cases.json> <dir> [--timeout S]

cases.json is a JSON list of cases:

  [{"name": "basic",                    required, [A-Za-z0-9._-]+, unique
    "argv": ["python3", "{root}/s.py"], required, non-empty list of strings
    "stdin": "text",                    optional, fed as UTF-8 (default: none)
    "env": {"LANG": "C"},               optional, added to the inherited env
    "files": ["data/in.csv"]}]          optional, fixtures (see below)

"{root}" in argv items and env values is replaced with the absolute path of
the directory holding cases.json. Each run happens in a fresh temporary
directory used as cwd. `files` lists paths relative to cases.json's
directory (files or whole directories), copied there under the same relative
path; a {"dest": "src"} object copies src to dest instead.

What a run observes: stdout, stderr, exit code, and the files it created,
changed or deleted in its working directory (a path + sha256 snapshot taken
before and after). All four must match for verify to pass.

record runs every case twice. A case whose two runs differ is reported as
`unstable` and not stored; a case that times out is reported as `timeout`
and not stored. Nothing is masked (no timestamp or path heuristics): the
caller rewrites or drops such cases. Recordings live in <dir>/<name>/
(stdout, stderr, result.json, files/<path>).

Exit codes: record 0 when every case was stored, 1 otherwise; verify 0 and
`OK` when every case matches, 1 with a compact diff per failing case
(timeouts and unrecorded cases count as failures); 2 on usage or cases.json
errors. A timeout (default 30 s) kills the case's whole process group.
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_TIMEOUT = 30.0
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
DIFF_LINES = 20


class CasesError(Exception):
    pass


# ---------------------------------------------------------------- cases

def load_cases(path):
    path = Path(path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CasesError(f"{path}: {e}")
    if not isinstance(data, list) or not data:
        raise CasesError(f"{path}: expected a non-empty list of cases")
    root = str(path.parent)
    seen, cases = set(), []
    for i, c in enumerate(data):
        where = f"case {i}"
        if not isinstance(c, dict):
            raise CasesError(f"{where}: expected an object")
        unknown = set(c) - {"name", "argv", "stdin", "env", "files"}
        if unknown:
            raise CasesError(f"{where}: unknown keys {sorted(unknown)}")
        name = c.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name) or name in (".", ".."):
            raise CasesError(f"{where}: 'name' must match [A-Za-z0-9._-]+")
        where = f"case '{name}'"
        if name in seen:
            raise CasesError(f"{where}: duplicate name")
        seen.add(name)
        argv = c.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise CasesError(f"{where}: 'argv' must be a non-empty list of strings")
        stdin = c.get("stdin")
        if stdin is not None and not isinstance(stdin, str):
            raise CasesError(f"{where}: 'stdin' must be a string")
        env = c.get("env", {})
        if not isinstance(env, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise CasesError(f"{where}: 'env' must map strings to strings")
        files = c.get("files", [])
        if isinstance(files, list):
            files = {f: f for f in files}
        if not isinstance(files, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
            raise CasesError(f"{where}: 'files' must be a list of paths or a dest->src object")
        fixtures = {}
        for dest, src in files.items():
            if Path(dest).is_absolute() or ".." in Path(dest).parts:
                raise CasesError(f"{where}: fixture destination '{dest}' must stay inside the run dir")
            s = (path.parent / src).resolve()
            if not s.exists():
                raise CasesError(f"{where}: fixture '{src}' not found")
            fixtures[dest] = s
        cases.append({
            "name": name,
            "argv": [a.replace("{root}", root) for a in argv],
            "stdin": stdin,
            "env": {k: v.replace("{root}", root) for k, v in env.items()},
            "files": fixtures,
        })
    return cases


# ---------------------------------------------------------------- running

def snapshot(d):
    """Map relative path -> sha256 of every regular file under d."""
    d = Path(d)
    out = {}
    for p in sorted(d.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[p.relative_to(d).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def run_case(case, timeout=DEFAULT_TIMEOUT):
    """Run one case in a fresh dir. Returns a result dict:
    stdout, stderr (bytes), exit_code, files {path: bytes} created or changed,
    deleted [paths], timeout (bool), elapsed (seconds of the process only)."""
    with tempfile.TemporaryDirectory(prefix="refine-golden-") as tmp:
        work = Path(tmp)
        for dest, src in case["files"].items():
            target = work / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, target, dirs_exist_ok=True)
            else:
                shutil.copy2(src, target)
        before = snapshot(work)
        env = dict(os.environ)
        env.update(case["env"])
        stdin = case["stdin"]
        start = time.perf_counter()
        try:
            proc = subprocess.Popen(
                case["argv"], cwd=work, env=env,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True)
        except OSError as e:
            return {"stdout": b"", "stderr": f"cannot run: {e}\n".encode(),
                    "exit_code": 127, "files": {}, "deleted": [], "timeout": False,
                    "elapsed": 0.0}
        try:
            out, err = proc.communicate(
                stdin.encode("utf-8") if stdin is not None else None, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            out, err = proc.communicate()
            timed_out = True
        elapsed = time.perf_counter() - start
        after = snapshot(work)
        files = {p: (work / p).read_bytes() for p, h in after.items() if before.get(p) != h}
        deleted = sorted(set(before) - set(after))
        return {"stdout": out, "stderr": err, "exit_code": proc.returncode,
                "files": files, "deleted": deleted, "timeout": timed_out,
                "elapsed": elapsed}


# ---------------------------------------------------------------- comparing

def _text_diff(label, a, b):
    try:
        a_lines = a.decode("utf-8").splitlines()
        b_lines = b.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return [f"  {label}: binary content differs ({len(a)} -> {len(b)} bytes)"]
    if a_lines == b_lines:  # only line endings or a trailing newline differ
        return [f"  {label}: differs in line endings or final newline"]
    diff = list(difflib.unified_diff(a_lines, b_lines, "expected", "actual",
                                     n=1, lineterm=""))[2:]
    lines = [f"  {label}:"] + [f"    {d}" for d in diff[:DIFF_LINES]]
    if len(diff) > DIFF_LINES:
        lines.append(f"    ... {len(diff) - DIFF_LINES} more diff lines")
    return lines


def compare(expected, actual):
    """Return a list of human-readable difference lines (empty when equal)."""
    out = []
    if actual.get("timeout"):
        out.append("  timed out")
    if expected["exit_code"] != actual["exit_code"]:
        out.append(f"  exit code: {expected['exit_code']} -> {actual['exit_code']}")
    for stream in ("stdout", "stderr"):
        if expected[stream] != actual[stream]:
            out += _text_diff(stream, expected[stream], actual[stream])
    ef, af = expected["files"], actual["files"]
    for p in sorted(set(ef) | set(af)):
        if p not in af:
            out.append(f"  file {p}: no longer produced")
        elif p not in ef:
            out.append(f"  file {p}: newly produced")
        elif ef[p] != af[p]:
            out += _text_diff(f"file {p}", ef[p], af[p])
    for p in sorted(set(expected["deleted"]) ^ set(actual["deleted"])):
        state = "deleted" if p in actual["deleted"] else "no longer deleted"
        out.append(f"  fixture {p}: {state}")
    return out


# ---------------------------------------------------------------- storage

def store(case_dir, result):
    case_dir = Path(case_dir)
    if case_dir.exists():
        shutil.rmtree(case_dir)
    (case_dir / "files").mkdir(parents=True)
    (case_dir / "stdout").write_bytes(result["stdout"])
    (case_dir / "stderr").write_bytes(result["stderr"])
    for p, data in result["files"].items():
        target = case_dir / "files" / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    meta = {"exit_code": result["exit_code"], "files": sorted(result["files"]),
            "deleted": result["deleted"]}
    (case_dir / "result.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def load(case_dir):
    case_dir = Path(case_dir)
    meta = json.loads((case_dir / "result.json").read_text(encoding="utf-8"))
    return {"stdout": (case_dir / "stdout").read_bytes(),
            "stderr": (case_dir / "stderr").read_bytes(),
            "exit_code": meta["exit_code"],
            "files": {p: (case_dir / "files" / p).read_bytes() for p in meta["files"]},
            "deleted": meta["deleted"]}


# ---------------------------------------------------------------- commands

def record(cases, out_dir, timeout=DEFAULT_TIMEOUT):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for case in cases:
        case_dir = out_dir / case["name"]
        first = run_case(case, timeout)
        second = None if first["timeout"] else run_case(case, timeout)
        problem = None
        if first["timeout"] or second["timeout"]:
            problem = [f"timeout {case['name']}: no result within {timeout:g} s"]
        else:
            diff = compare(first, second)
            if diff:
                problem = [f"unstable {case['name']}: two runs differ"] + diff
        if problem:
            ok = False
            if case_dir.exists():
                shutil.rmtree(case_dir)
            print("\n".join(problem))
        else:
            store(case_dir, first)
            print(f"recorded {case['name']}")
    return 0 if ok else 1


def verify(cases, out_dir, timeout=DEFAULT_TIMEOUT):
    out_dir = Path(out_dir)
    failures = []
    for case in cases:
        case_dir = out_dir / case["name"]
        if not (case_dir / "result.json").is_file():
            failures.append([f"FAIL {case['name']}", "  not recorded"])
            continue
        diff = compare(load(case_dir), run_case(case, timeout))
        if diff:
            failures.append([f"FAIL {case['name']}"] + diff)
    if not failures:
        print("OK")
        return 0
    for f in failures:
        print("\n".join(f))
    print(f"{len(failures)} of {len(cases)} cases differ")
    return 1


USAGE = """usage: refine golden record <cases.json> <dir> [--timeout S]
       refine golden verify <cases.json> <dir> [--timeout S]
"""


def parse_timeout(argv):
    """Pop `--timeout S` / `--timeout=S` from argv. Returns (timeout, rest)."""
    rest, timeout, i = [], DEFAULT_TIMEOUT, 0
    while i < len(argv):
        a = argv[i]
        if a == "--timeout" or a.startswith("--timeout="):
            if a == "--timeout":
                if i + 1 >= len(argv):
                    raise ValueError("--timeout needs a value")
                value, i = argv[i + 1], i + 2
            else:
                value, i = a.split("=", 1)[1], i + 1
            timeout = float(value)
            if timeout <= 0:
                raise ValueError("--timeout must be positive")
        else:
            rest.append(a)
            i += 1
    return timeout, rest


def main(argv):
    argv = list(argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    try:
        timeout, args = parse_timeout(argv)
    except ValueError as e:
        print(f"golden: {e}", file=sys.stderr)
        return 2
    if len(args) != 3 or args[0] not in ("record", "verify"):
        print(USAGE, end="", file=sys.stderr)
        return 2
    try:
        cases = load_cases(args[1])
    except CasesError as e:
        print(f"golden: {e}", file=sys.stderr)
        return 2
    action = record if args[0] == "record" else verify
    return action(cases, args[2], timeout)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
