import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import golden
import refine

PY = sys.executable

ECHO = "import sys\nprint('hello', sys.argv[1:])\nsys.stdout.write(sys.stdin.read())\n"
WRITER = ("import os, sys\n"
          "open('out.txt', 'w').write(open('in.txt').read().upper())\n"
          "os.remove('gone.txt')\n"
          "print(os.environ.get('GREETING', ''))\n"
          "sys.exit(3)\n")
CLOCK = "import time\nprint(time.perf_counter_ns())\n"
SLEEPER = "import time\ntime.sleep(30)\n"


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = refine.main(argv)
    return code, out.getvalue(), err.getvalue()


class GoldenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gold = self.root / "golden"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def cases(self, cases):
        return str(self.write("cases.json", json.dumps(cases)))

    def golden(self, *args):
        return run(["golden", *args])

    # -- record / verify

    def test_record_then_verify_unchanged_prints_ok(self):
        self.write("echo.py", ECHO)
        cases = self.cases([{"name": "echo", "argv": [PY, "{root}/echo.py", "a"], "stdin": "in\n"}])
        code, out, _ = self.golden("record", cases, str(self.gold))
        self.assertEqual((code, out), (0, "recorded echo\n"))
        self.assertEqual((self.gold / "echo" / "stdout").read_bytes(), b"hello ['a']\nin\n")
        code, out, _ = self.golden("verify", cases, str(self.gold))
        self.assertEqual((code, out), (0, "OK\n"))

    def test_one_changed_byte_fails_naming_the_case(self):
        script = self.write("echo.py", ECHO)
        cases = self.cases([
            {"name": "echo", "argv": [PY, "{root}/echo.py", "a"]},
            {"name": "other", "argv": [PY, "-c", "print(1)"]},
        ])
        self.assertEqual(self.golden("record", cases, str(self.gold))[0], 0)
        script.write_text(ECHO.replace("hello", "hellO"), encoding="utf-8")
        code, out, _ = self.golden("verify", cases, str(self.gold))
        self.assertEqual(code, 1)
        self.assertIn("FAIL echo", out)
        self.assertNotIn("FAIL other", out)
        self.assertIn("-hello ['a']", out)
        self.assertIn("+hellO ['a']", out)
        self.assertIn("1 of 2 cases differ", out)

    def test_files_env_exit_code_and_deletions_are_recorded(self):
        self.write("w.py", WRITER)
        self.write("fx/in.txt", "abc\n")
        self.write("fx/gone.txt", "x")
        cases = self.cases([{"name": "w", "argv": [PY, "{root}/w.py"],
                             "env": {"GREETING": "hi"},
                             "files": {"in.txt": "fx/in.txt", "gone.txt": "fx/gone.txt"}}])
        self.assertEqual(self.golden("record", cases, str(self.gold))[0], 0)
        meta = json.loads((self.gold / "w" / "result.json").read_text())
        self.assertEqual(meta, {"exit_code": 3, "files": ["out.txt"], "deleted": ["gone.txt"]})
        self.assertEqual((self.gold / "w" / "files" / "out.txt").read_text(), "ABC\n")
        self.assertEqual((self.gold / "w" / "stdout").read_text(), "hi\n")
        self.assertEqual(self.golden("verify", cases, str(self.gold))[:2], (0, "OK\n"))
        self.write("w.py", WRITER.replace(".upper()", "").replace("exit(3)", "exit(4)"))
        code, out, _ = self.golden("verify", cases, str(self.gold))
        self.assertEqual(code, 1)
        self.assertIn("exit code: 3 -> 4", out)
        self.assertIn("file out.txt:", out)
        self.assertIn("+abc", out)

    def test_fixture_list_and_directory(self):
        self.write("data/a.txt", "A")
        self.write("data/sub/b.txt", "B")
        prog = "import pathlib; print(sorted(str(p) for p in pathlib.Path('data').rglob('*.txt')))"
        cases = self.cases([{"name": "ls", "argv": [PY, "-c", prog], "files": ["data"]}])
        self.assertEqual(self.golden("record", cases, str(self.gold))[0], 0)
        self.assertEqual((self.gold / "ls" / "stdout").read_text(),
                         "['data/a.txt', 'data/sub/b.txt']\n")

    def test_unstable_case_is_reported_and_not_stored(self):
        self.write("clock.py", CLOCK)
        cases = self.cases([{"name": "clock", "argv": [PY, "{root}/clock.py"]},
                            {"name": "fine", "argv": [PY, "-c", "print(2)"]}])
        (self.gold / "clock").mkdir(parents=True)  # stale recording is removed
        code, out, _ = self.golden("record", cases, str(self.gold))
        self.assertEqual(code, 1)
        self.assertIn("unstable clock", out)
        self.assertIn("recorded fine", out)
        self.assertFalse((self.gold / "clock").exists())
        code, out, _ = self.golden("verify", cases, str(self.gold))
        self.assertEqual(code, 1)
        self.assertIn("FAIL clock\n  not recorded", out)

    def test_timeout_is_a_failure_not_a_hang(self):
        self.write("sleep.py", SLEEPER)
        cases = self.cases([{"name": "slow", "argv": [PY, "{root}/sleep.py"]}])
        code, out, _ = self.golden("record", cases, str(self.gold), "--timeout", "0.5")
        self.assertEqual(code, 1)
        self.assertIn("timeout slow", out)
        self.assertFalse((self.gold / "slow").exists())
        # recorded fast, then it starts hanging: verify fails within the timeout
        self.write("sleep.py", "print('quick')\n")
        self.assertEqual(self.golden("record", cases, str(self.gold))[0], 0)
        self.write("sleep.py", SLEEPER)
        code, out, _ = self.golden("verify", cases, str(self.gold), "--timeout=0.5")
        self.assertEqual(code, 1)
        self.assertIn("FAIL slow\n  timed out", out)

    def test_missing_program_is_a_result_not_a_crash(self):
        cases = self.cases([{"name": "nope", "argv": ["/no/such/program-xyz"]}])
        self.assertEqual(self.golden("record", cases, str(self.gold))[0], 0)
        self.assertEqual(json.loads((self.gold / "nope" / "result.json").read_text())["exit_code"], 127)

    # -- usage and validation

    def test_usage_errors(self):
        self.assertEqual(self.golden()[0], 2)
        self.assertEqual(self.golden("replay", "a", "b")[0], 2)
        self.assertEqual(self.golden("record", "a", "b", "--timeout")[0], 2)
        self.assertEqual(self.golden("record", "a", "b", "--timeout", "0")[0], 2)
        code, out, _ = self.golden("--help")
        self.assertEqual(code, 0)
        self.assertIn("cases.json", out)

    def test_invalid_cases(self):
        bad = [
            ("not json", "{"),
            ("empty", "[]"),
            ("no name", '[{"argv": ["x"]}]'),
            ("bad name", '[{"name": "a/b", "argv": ["x"]}]'),
            ("dup", '[{"name": "a", "argv": ["x"]}, {"name": "a", "argv": ["x"]}]'),
            ("argv", '[{"name": "a", "argv": []}]'),
            ("stdin", '[{"name": "a", "argv": ["x"], "stdin": 1}]'),
            ("env", '[{"name": "a", "argv": ["x"], "env": {"A": 1}}]'),
            ("files", '[{"name": "a", "argv": ["x"], "files": ["missing.txt"]}]'),
            ("escape", '[{"name": "a", "argv": ["x"], "files": {"../x": "cases.json"}}]'),
            ("unknown key", '[{"name": "a", "argv": ["x"], "expect": 1}]'),
        ]
        for label, text in bad:
            with self.subTest(label):
                p = self.write("cases.json", text)
                with self.assertRaises(golden.CasesError):
                    golden.load_cases(p)
                self.assertEqual(self.golden("verify", str(p), str(self.gold))[0], 2)

    def test_root_placeholder_in_argv_and_env(self):
        p = self.write("cases.json", json.dumps(
            [{"name": "a", "argv": ["{root}/s.py"], "env": {"D": "{root}"}}]))
        case = golden.load_cases(p)[0]
        root = str(self.root.resolve())
        self.assertEqual(case["argv"], [root + "/s.py"])
        self.assertEqual(case["env"], {"D": root})


class CompareTest(unittest.TestCase):
    def base(self, **kw):
        r = {"stdout": b"", "stderr": b"", "exit_code": 0, "files": {}, "deleted": []}
        r.update(kw)
        return r

    def test_equal_is_empty(self):
        self.assertEqual(golden.compare(self.base(), self.base()), [])

    def test_binary_and_newline_differences(self):
        diff = golden.compare(self.base(stdout=b"\xff\x00"), self.base(stdout=b"\xfe"))
        self.assertIn("binary content differs", diff[0])
        diff = golden.compare(self.base(stdout=b"a\n"), self.base(stdout=b"a"))
        self.assertIn("line endings or final newline", diff[0])

    def test_long_diff_is_truncated(self):
        a = "".join(f"{i}\n" for i in range(100)).encode()
        b = "".join(f"x{i}\n" for i in range(100)).encode()
        diff = golden.compare(self.base(stdout=a), self.base(stdout=b))
        self.assertLessEqual(len(diff), golden.DIFF_LINES + 2)
        self.assertIn("more diff lines", diff[-1])

    def test_file_presence_changes(self):
        diff = golden.compare(self.base(files={"a": b"1"}, deleted=["x"]),
                              self.base(files={"b": b"1"}))
        self.assertEqual(diff, ["  file a: no longer produced", "  file b: newly produced",
                                "  fixture x: no longer deleted"])


if __name__ == "__main__":
    unittest.main()
