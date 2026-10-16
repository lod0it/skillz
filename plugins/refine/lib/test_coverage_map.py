import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_map
import refine

HAS_COVERAGE = importlib.util.find_spec("coverage") is not None

BRANCHY_SH = """#!/bin/sh
x="$1"
if [ "$x" = "a" ]; then
  echo yes
else
  echo no
  echo still no
fi
. "$(dirname "$0")/inc.sh"
echo done
"""
INC_SH = "echo included\necho twice\necho thrice\n"
BRANCHY_PY = """import sys
x = sys.argv[1]
if x == "a":
    print("yes")
else:
    print("no")
    print("still no")
print("done")
"""


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = refine.main(argv)
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text, mode=None):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        if mode:
            p.chmod(mode)
        return p

    def cases(self, cases):
        return str(self.write("cases.json", json.dumps(cases)))

    def coverage(self, *args):
        code, out, err = run(["coverage", *args, "--scratch", str(self.root / "scratch")])
        return code, (json.loads(out) if out.strip() else None), err


class LanguageTest(Base):
    def test_extension_wins(self):
        for name, lang in [("a.py", "python"), ("a.sh", "shell"), ("a.bash", "shell"),
                           ("a.mjs", "node"), ("a.ts", "node"), ("a.go", "go")]:
            self.assertEqual(coverage_map.detect_language(self.write(name, "#!/bin/zsh\n")), lang)

    def test_shebang_when_no_extension(self):
        for line, lang in [("#!/usr/bin/env python3", "python"), ("#!/usr/bin/python3.12", "python"),
                           ("#!/bin/bash -e", "shell"), ("#!/bin/sh", "shell"),
                           ("#!/usr/bin/env -S node --no-warnings", "node"),
                           ("#!/bin/zsh", "zsh")]:
            self.assertEqual(coverage_map.detect_language(self.write("tool", line + "\necho\n")), lang)

    def test_unknown(self):
        self.assertEqual(coverage_map.detect_language(self.write("data", "plain\n")), "unknown")
        self.assertEqual(coverage_map.detect_language(self.write("x.rb", "puts 1\n")), "rb")


class ProbeTest(Base):
    def test_probe_shell_is_available(self):
        code, out, _ = self.coverage("--probe", str(self.write("s.sh", BRANCHY_SH)))
        self.assertEqual(code, 0)
        self.assertEqual((out["language"], out["tool"], out["available"]), ("shell", "bash -x", True))

    def test_probe_unknown_language_is_unavailable(self):
        code, out, _ = self.coverage("--probe", str(self.write("x.rb", "puts 1\n")))
        self.assertEqual(code, 3)
        self.assertFalse(out["available"])
        self.assertIsNone(out["install_hint"])

    def test_probe_does_not_need_cases(self):
        code, _, err = self.coverage(str(self.write("s.sh", BRANCHY_SH)))
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class ShellTest(Base):
    def setUp(self):
        super().setUp()
        self.script = self.write("s.sh", BRANCHY_SH)
        self.write("inc.sh", INC_SH)

    def test_untaken_else_is_not_covered(self):
        cases = self.cases([{"name": "a", "argv": ["bash", "{root}/s.sh", "a"]}])
        code, out, _ = self.coverage(str(self.script), cases)
        self.assertEqual(code, 0)
        self.assertEqual(out["mode"], "measured")
        self.assertEqual(out["covered"], [2, 3, 4, 9, 10])  # not 6, 7; not inc.sh's lines

    def test_cases_are_unioned_and_direct_execution_is_wrapped(self):
        self.script.chmod(0o755)
        cases = self.cases([{"name": "a", "argv": ["bash", "{root}/s.sh", "a"]},
                            {"name": "b", "argv": ["{root}/s.sh", "b"]}])
        code, out, _ = self.coverage(str(self.script), cases)
        self.assertEqual(code, 0)
        self.assertEqual(out["covered"], [2, 3, 4, 6, 7, 9, 10])

    def test_case_not_running_the_script_is_unmapped(self):
        cases = self.cases([{"name": "a", "argv": ["bash", "{root}/s.sh", "a"]},
                            {"name": "other", "argv": ["echo", "hi"]}])
        code, out, _ = self.coverage(str(self.script), cases)
        self.assertEqual(code, 0)
        self.assertEqual(out["unmapped_cases"], ["other"])

    def test_no_case_runs_the_script(self):
        cases = self.cases([{"name": "other", "argv": ["echo", "hi"]}])
        code, _, err = self.coverage(str(self.script), cases)
        self.assertEqual(code, 2)
        self.assertIn("no case runs", err)

    def test_script_stderr_and_cwd_fixtures(self):
        self.write("t.sh", 'cat in.txt\necho "+[refine-cov]99:: fake" >&2\n')
        self.write("in.txt", "data\n")
        cases = self.cases([{"name": "c", "argv": ["bash", "{root}/t.sh"], "files": ["in.txt"]}])
        code, out, _ = self.coverage(str(self.root / "t.sh"), cases)
        self.assertEqual(code, 0)
        self.assertIn(1, out["covered"])
        self.assertEqual(out["failed_cases"], [])

    def test_long_paths_are_matched(self):
        deep = "d" * 60 + "/" + "e" * 60
        script = self.write(f"{deep}/s.sh", BRANCHY_SH)
        self.write(f"{deep}/inc.sh", INC_SH)
        cases = self.cases([{"name": "a", "argv": ["bash", f"{{root}}/{deep}/s.sh", "a"]}])
        code, out, _ = self.coverage(str(script), cases)
        self.assertEqual((code, out["covered"]), (0, [2, 3, 4, 9, 10]))


class PythonTest(Base):
    def test_unavailable_has_a_local_install_hint(self):
        fake = self.write("fakepy", "#!/bin/sh\nexit 1\n", 0o755)
        script = self.write("p.py", BRANCHY_PY)
        cases = self.cases([{"name": "a", "argv": ["python3", "{root}/p.py", "a"]}])
        code, out, _ = self.coverage(str(script), cases, "--python", str(fake))
        self.assertEqual(code, 3)
        self.assertEqual(out["mode"], "unavailable")
        self.assertIn(str(self.root / "scratch" / "venv"), out["install_hint"])
        self.assertIn("pip install coverage", out["install_hint"])

    @unittest.skipUnless(HAS_COVERAGE, "coverage.py is not importable")
    def test_untaken_else_is_not_covered(self):
        script = self.write("p.py", BRANCHY_PY)
        cases = self.cases([{"name": "a", "argv": ["python3", "{root}/p.py", "a"]}])
        code, out, _ = self.coverage(str(script), cases, "--python", sys.executable)
        self.assertEqual(code, 0)
        self.assertEqual(out["covered"], [1, 2, 3, 4, 8])


class NodeTest(Base):
    def test_istanbul_lines(self):
        entry = {"statementMap": {"0": {"start": {"line": 1}, "end": {"line": 1}},
                                  "1": {"start": {"line": 3}, "end": {"line": 3}}},
                 "s": {"0": 1, "1": 0}}
        self.assertEqual(coverage_map.istanbul_lines(entry), {1})

    @unittest.skipIf(shutil.which("c8"), "c8 is installed")
    def test_unavailable_without_c8(self):
        code, out, _ = self.coverage("--probe", str(self.write("a.js", "console.log(1)\n")))
        self.assertEqual(code, 3)
        if shutil.which("npm"):
            self.assertIn("npm install --prefix", out["install_hint"])
            self.assertIn(str(self.root / "scratch" / "node"), out["install_hint"])

    @unittest.skipUnless(shutil.which("c8") and shutil.which("node"), "c8 or node is missing")
    def test_untaken_else_is_not_covered(self):
        script = self.write("a.js", "const x = process.argv[2];\nif (x === 'a') {\n"
                                    "  console.log('yes');\n} else {\n  console.log('no');\n}\n")
        cases = self.cases([{"name": "a", "argv": ["node", "{root}/a.js", "a"]}])
        code, out, _ = self.coverage(str(script), cases)
        self.assertEqual(code, 0)
        self.assertIn(3, out["covered"])
        self.assertNotIn(5, out["covered"])


class GoTest(Base):
    def test_profile_lines(self):
        text = ("mode: set\nexample.com/m/a.go:3.10,5.2 1 1\n"
                "example.com/m/a.go:5.8,7.3 1 0\nexample.com/m/b.go:1.1,2.2 1 1\n")
        self.assertEqual(coverage_map.goprofile_lines(text, "a.go"), {3, 4, 5})

    @unittest.skipUnless(shutil.which("go"), "go is missing")
    def test_package_without_tests_is_unavailable(self):
        code, out, _ = self.coverage("--probe", str(self.write("a.go", "package a\n")))
        self.assertEqual(code, 3)
        self.assertIn("_test.go", out["reason"])

    @unittest.skipUnless(shutil.which("go"), "go is missing")
    def test_untaken_else_is_not_covered(self):
        self.write("go.mod", "module example.com/a\n\ngo 1.20\n")
        script = self.write("a.go", "package a\n\nfunc F(x int) int {\n\tif x > 0 {\n"
                                    "\t\treturn 1\n\t} else {\n\t\treturn 2\n\t}\n}\n")
        self.write("a_test.go", 'package a\n\nimport "testing"\n\n'
                                "func TestF(t *testing.T) { F(1) }\n")
        cases = self.cases([{"name": "unused", "argv": ["true"]}])
        code, out, _ = self.coverage(str(script), cases)
        self.assertEqual(code, 0)
        self.assertIn(5, out["covered"])
        self.assertNotIn(7, out["covered"])


if __name__ == "__main__":
    unittest.main()
