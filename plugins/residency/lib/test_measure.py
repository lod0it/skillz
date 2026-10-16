import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import measure as M


def md(total, instr="1.4k", tools="20k", mem="2k"):
    return ("## Context Usage\n\n**Model:** m\n**Tokens:** %s / 1m (1%%)\n\n"
            "### Estimated usage by category\n\n| Category | Tokens | Percentage |\n|---|---|---|\n"
            "| System tools | %s | 1%% |\n| MCP server instructions | %s | 0%% |\n"
            "| Memory files | %s | 0%% |\n" % (total, tools, instr, mem))


def out(markdown, cost=0, turns=0):
    return json.dumps({"total_cost_usd": cost, "num_turns": turns, "result": markdown})


class Fake:
    """Stands in for subprocess.run: answers by the --settings JSON it receives."""

    def __init__(self, answers, version="2.1.301"):
        self.answers = answers  # key (settings json) -> list of stdout, consumed in order
        self.calls = []
        self.version = version

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[1] == "--version":
            return subprocess.CompletedProcess(cmd, 0, self.version + "\n", "")
        assert cmd[-2:] == ["-p", "/context"]
        lst = self.answers[cmd[2]]
        o = lst.pop(0) if len(lst) > 1 else lst[0]
        return subprocess.CompletedProcess(cmd, 0, o, "")

    def runs(self):
        return [c for c in self.calls if c[1] != "--version"]


DENY = {"permissions": {"deny": ["Agent"]}}
DENYJ = json.dumps(DENY, sort_keys=True)


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "cache.json"

    def tearDown(self):
        self.tmp.cleanup()

    def m(self, fake, **kw):
        return M.Measurer("/proj", {"a": 1}, self.cache, fake, **kw)

    def test_delta_math(self):
        f = Fake({"{}": [out(md("30k", tools="20k"))], DENYJ: [out(md("28.8k", tools="18.8k"))]})
        d = self.m(f).delta(DENY)
        self.assertTrue(d.ok)
        self.assertEqual(d.total, 1200)
        self.assertEqual(d.categories["System tools"], 1200)
        self.assertEqual(f.runs()[0][-2:], ["-p", "/context"])

    def test_negative_delta(self):
        f = Fake({"{}": [out(md("30k", tools="20k"))], DENYJ: [out(md("30.5k", tools="20.5k"))]})
        self.assertEqual(self.m(f).delta(DENY).total, -500)

    def test_race_retry_then_ok(self):
        f = Fake({"{}": [out(md("30k"))], DENYJ: [out(md("28k", instr="78")), out(md("28.8k"))]})
        d = self.m(f).delta(DENY)
        self.assertTrue(d.ok)
        self.assertEqual(d.total, 1200)

    def test_race_twice_unknown(self):
        f = Fake({"{}": [out(md("30k"))], DENYJ: [out(md("28k", instr="78"))]})
        d = self.m(f).delta(DENY)
        self.assertFalse(d.ok)
        self.assertIn("unknown", d.reason)
        self.assertFalse(self.cache.exists())

    def test_cache_hit_and_invalidation(self):
        f = Fake({"{}": [out(md("30k"))], DENYJ: [out(md("28.8k"))]})
        self.m(f).delta(DENY)
        n = len(f.runs())
        d = self.m(f).delta(DENY)
        self.assertTrue(d.cached)
        self.assertEqual(d.total, 1200)
        self.assertEqual(len(f.runs()), n)
        # a new claude version misses and drops the old entry
        f2 = Fake({"{}": [out(md("30k"))], DENYJ: [out(md("29k"))]}, version="2.2.0")
        d2 = self.m(f2).delta(DENY)
        self.assertFalse(d2.cached)
        self.assertEqual(d2.total, 1000)
        self.assertEqual(len(json.loads(self.cache.read_text())), 1)

    def test_cost_refused(self):
        f = Fake({"{}": [out(md("30k"), cost=0.01, turns=1)]})
        with self.assertRaises(M.MeasureError):
            self.m(f).delta(DENY)
        self.assertEqual(len(f.runs()), 1)  # never retried

    def test_background(self):
        f = Fake({"{}": [out(md("30k"))], DENYJ: [out(md("28.8k"))]})
        got = []
        b = M.Background(self.m(f), lambda n, r: got.append((n, r)))
        b.submit("Agent", DENY)
        b.close()
        b.join(5)
        self.assertEqual(got[0][0], "Agent")
        self.assertEqual(got[0][1].total, 1200)

    def test_background_error_and_cancel(self):
        f = Fake({"{}": [out(md("30k"), cost=1, turns=1)]})
        got = []
        b = M.Background(self.m(f), lambda n, r: got.append((n, r)))
        b.submit("x", DENY)
        b.close()
        b.join(5)
        self.assertIsInstance(got[0][1], M.MeasureError)
        b2 = M.Background(self.m(Fake({})), lambda n, r: got.append(n))
        b2.cancel()
        b2.submit("late", DENY)
        b2.join(5)
        self.assertNotIn("late", got)


if __name__ == "__main__":
    unittest.main()
