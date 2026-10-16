import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure
import refine

PY = sys.executable


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = refine.main(argv)
    return code, out.getvalue(), err.getvalue()


class MeasureTextTest(unittest.TestCase):
    def test_lines_skip_blank_and_comment_only(self):
        text = ("#!/usr/bin/env python3\n"
                "# comment\n"
                "\n"
                "x = 1  # trailing comment stays\n"
                "    // js comment\n"
                "-- sql comment\n"
                "; lisp comment\n"
                "   \n"
                "y = 2\n")
        r = measure.measure_text(text)
        self.assertEqual((r["lines"], r["total_lines"]), (2, 9))

    def test_block_comments_are_not_stripped(self):
        r = measure.measure_text("/* a\n   b */\n")
        self.assertEqual(r["lines"], 2)

    def test_tokens(self):
        cases = {
            "x = 1": 3,
            "foo(bar, 'a b c')": 6,
            'print("he said \\"hi\\"")': 4,
            "a == b != c": 5,
            "x **= 2": 3,
            "f = lambda a: a->b": 8,
            "n = 0x1F + 1.5e3": 5,
            "a && b || !c": 6,
            "è_var = 1": 3,
            "`tpl ${x}`": 1,
        }
        for src, n in cases.items():
            with self.subTest(src):
                self.assertEqual(measure.measure_text(src)["tokens"], n)

    def test_comment_lines_have_no_tokens(self):
        self.assertEqual(measure.measure_text("# a b c\nx\n")["tokens"], 1)

    def test_consistent_for_equal_input(self):
        text = Path(measure.__file__).read_text(encoding="utf-8")
        self.assertEqual(measure.measure_text(text), measure.measure_text(text))


class MeasureCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_prints_json(self):
        f = self.write("s.py", "# c\nx = 1\n\nprint(x)\n")
        code, out, _ = run(["measure", f])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"file": f, "lines": 2, "total_lines": 4, "tokens": 7})

    def test_time_median(self):
        f = self.write("s.py", "print(1)\n")
        cases = self.write("cases.json", json.dumps([{"name": "a", "argv": [PY, "{root}/s.py"]}]))
        code, out, _ = run(["measure", f, "--time", cases])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertGreater(report["time_s"], 0)
        self.assertLess(report["time_s"], 10)

    def test_time_cases_median_of_runs(self):
        calls = []
        saved = measure.golden.run_case

        def fake(case, timeout):
            calls.append(case["name"])
            return {"timeout": False, "elapsed": [5.0, 1.0, 2.0, 3.0, 4.0][len(calls) - 1]}
        measure.golden.run_case = fake
        try:
            seconds, timed_out = measure.time_cases([{"name": "a"}])
        finally:
            measure.golden.run_case = saved
        self.assertEqual((seconds, timed_out, len(calls)), (3.0, None, measure.RUNS))

    def test_time_timeout_exits_1(self):
        f = self.write("s.py", "import time\ntime.sleep(30)\n")
        cases = self.write("cases.json", json.dumps([{"name": "slow", "argv": [PY, "{root}/s.py"]}]))
        code, out, err = run(["measure", f, "--time", cases, "--timeout", "0.3"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("'slow' timed out", err)

    def test_usage_errors(self):
        f = self.write("s.py", "x\n")
        self.assertEqual(run(["measure"])[0], 2)
        self.assertEqual(run(["measure", f, "--time"])[0], 2)
        self.assertEqual(run(["measure", str(self.root / "missing.py")])[0], 2)
        self.assertEqual(run(["measure", f, "--time", self.write("c.json", "[]")])[0], 2)
        code, out, _ = run(["measure", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("tokens", out)


if __name__ == "__main__":
    unittest.main()
