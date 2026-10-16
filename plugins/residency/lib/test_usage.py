import json
import os
import tempfile
import unittest
from pathlib import Path

import snapshot
import usage


def tu(i, name, **inp):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": i, "name": name, "input": inp}]}}


def write(path, recs, junk=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in recs]
    if junk:
        lines.insert(1, "not json {")
    path.write_text("\n".join(lines) + "\n")


class UsageTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "projects"
        self.cache = Path(t.name) / "cache.json"
        self.proj = "/work/my.proj"
        self.here = self.root / snapshot.project_key(self.proj)

    def test_scan_file(self):
        p = self.here / "a.jsonl"
        write(p, [
            tu("1", "Bash", command="ls"),
            tu("2", "Skill", skill="refine:ablate"),
            tu("2", "Skill", skill="refine:ablate"),  # duplicate record
            tu("3", "mcp__pen__x"), tu("4", "mcp__pen__y"),
            {"type": "assistant", "isSidechain": True, "message": {"content": [
                {"type": "tool_use", "id": "5", "name": "Bash", "input": {}}]}},
            {"type": "user", "message": {"content":
                "<command-name>/clear</command-name>\n<command-args></command-args>"}},
            {"type": "user", "message": {"content": [
                {"type": "text", "text": "<command-name>/taskflow:board</command-name>"}]}},
        ])
        c = usage.scan_file(p)
        self.assertEqual(c.tools, {"Bash": 2, "Skill": 1, "mcp__pen__x": 1, "mcp__pen__y": 1})
        self.assertEqual(c.mcp, {"pen": 2})
        self.assertEqual(c.skills, {"refine:ablate": 1, "clear": 1, "taskflow:board": 1})

    def test_here_all_and_last_n(self):
        other = self.root / "-other"
        for i, d in enumerate([self.here, self.here, other]):
            p = d / ("s%d.jsonl" % i)
            write(p, [tu("x", "Read")])
            os.utime(p, (1000 + i, 1000 + i))
        r = lambda scope, n=30: usage.usage(scope, self.proj, n, self.root, self.cache)
        self.assertEqual(r("here").tools, {"Read": 2})
        self.assertEqual(r("all").tools, {"Read": 3})
        self.assertEqual(r("all", 2).tools, {"Read": 2})  # newest two sessions
        with self.assertRaises(ValueError):
            r("x")

    def test_cache_reads_nothing_second_time(self):
        for i in range(2):
            write(self.here / ("s%d.jsonl" % i), [tu("x", "Read")])
        calls = []

        def scanner(p):
            calls.append(p)
            return usage.scan_file(p)
        run = lambda: usage.usage("here", self.proj, 30, self.root, self.cache, scanner)
        first = run()
        self.assertEqual(len(calls), 2)
        second = run()
        self.assertEqual(len(calls), 2)
        self.assertEqual(first, second)
        # a changed file is the only one re-read
        p = self.here / "s0.jsonl"
        write(p, [tu("x", "Read"), tu("y", "Edit")])
        self.assertEqual(run().tools, {"Read": 2, "Edit": 1})
        self.assertEqual(calls, calls[:2] + [p])

    def test_corrupt_cache_and_missing_dir(self):
        self.cache.write_text("garbage")
        self.assertEqual(usage.usage("here", self.proj, 30, self.root, self.cache), usage.Counts())
        self.assertEqual(usage.usage("all", None, 30, self.root / "none", self.cache), usage.Counts())


if __name__ == "__main__":
    unittest.main()
