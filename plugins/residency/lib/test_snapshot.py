import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import snapshot as S

FIX = Path(__file__).resolve().parent / "fixtures"


class TokenCells(unittest.TestCase):
    def test_formats(self):
        cases = {"56.1k": (56100, False), "1m": (1000000, False), "429": (429, False),
                 "~120": (120, False), "< 20": (20, True), "<20": (20, True),
                 "0": (0, False), "1.4k": (1400, False), "33k": (33000, False), " 2.5k ": (2500, False)}
        for cell, want in cases.items():
            self.assertEqual(S.parse_tokens(cell), want, cell)

    def test_rejects_garbage(self):
        for bad in ("", "abc", "k", "1x"):
            with self.assertRaises(ValueError):
                S.parse_tokens(bad)


class Markdown(unittest.TestCase):
    def test_interactive_fixture(self):
        s = S.parse_context((FIX / "context_interactive.md").read_text())
        self.assertEqual((s.model, s.total, s.window), ("claude-opus-5-5", 56100, 1000000))
        self.assertEqual(s.categories["System tools"], 20200)
        self.assertEqual(s.categories["Autocompact buffer"], 33000)
        self.assertNotIn("MCP tools", s.categories)
        canva = [i for i in s.mcp_tools if i.name.endswith("create-design")][0]
        self.assertEqual((canva.tokens, canva.source), (1400, "claude_ai_Canva"))
        sk = {i.name: i for i in s.skills}
        self.assertEqual((sk["code-review"].tokens, sk["code-review"].source), (330, "Built-in"))
        self.assertEqual(sk["board:board-add"].source, "Plugin (board)")
        self.assertEqual([a.name for a in s.agents], ["shrike"])
        self.assertEqual(s.memory_files[0].tokens, 57)
        self.assertTrue(s.memory_files[0].path.endswith("MEMORY.md"))

    def test_unknown_category_kept_and_approx_cell(self):
        md = (FIX / "context_interactive.md").read_text()
        md = md.replace("| Messages |", "| Brand new thing | 7 | 0.0% |\n| Messages |")
        md = md.replace("| init | Built-in | ~20 |", "| init | Built-in | < 20 |")
        s = S.parse_context(md)
        self.assertEqual(s.categories["Brand new thing"], 7)
        init = [i for i in s.skills if i.name == "init"][0]
        self.assertEqual((init.tokens, init.approx), (20, True))

    def test_not_context(self):
        with self.assertRaises(ValueError):
            S.parse_context("hello")


class Headless(unittest.TestCase):
    def test_fixture(self):
        s = S.read_headless((FIX / "context_headless.json").read_text())
        self.assertEqual(s.total, 12800)
        self.assertEqual(s.categories["System tools"], 5000)
        self.assertEqual(len(s.agents), 2)

    def test_path_input(self):
        self.assertEqual(S.read_headless(FIX / "context_headless.json").window, 1000000)

    def test_refuses_paid_run(self):
        d = json.loads((FIX / "context_headless.json").read_text())
        for k, v in (("total_cost_usd", 0.01), ("num_turns", 1)):
            bad = dict(d, **{k: v})
            with self.assertRaises(ValueError):
                S.read_headless(json.dumps(bad))


class Latest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.proj = "/Users/x/code/my.proj_1"
        self.dir = self.root / "-Users-x-code-my-proj-1"
        self.dir.mkdir()

    def put(self, name, text, mtime):
        p = self.dir / (name + ".jsonl")
        p.write_text(text)
        os.utime(p, (mtime, mtime))
        return p

    def test_key(self):
        self.assertEqual(S.project_key("/Users/galfano/code/skillz"), "-Users-galfano-code-skillz")
        self.assertEqual(S.project_key("/Users/galfano/.claude"), "-Users-galfano--claude")

    def test_empty_project(self):
        self.assertIsNone(S.latest_snapshot("/nope", self.root))
        self.assertIsNone(S.latest_snapshot(self.proj, self.root))

    def test_transcript_fixture(self):
        self.put("sessA", (FIX / "transcript.jsonl").read_text(), 100)
        f = S.latest_snapshot(self.proj, self.root)
        self.assertEqual((f.source, f.session, f.timestamp), ("context", "sessA", "2026-10-16T10:01:01.000Z"))
        self.assertEqual(f.snapshot.total, 56100)
        self.assertEqual(len(f.snapshot.mcp_tools), 2)

    def test_newest_session_and_newest_context(self):
        text = (FIX / "transcript.jsonl").read_text()
        newer = text.replace("56.1k", "60k") + text.replace("56.1k", "70k").replace("10:01:01", "11:00:00")
        self.put("old", text, 100)
        self.put("new", newer, 200)
        f = S.latest_snapshot(self.proj, self.root)
        self.assertEqual((f.session, f.snapshot.total), ("new", 70000))

    def test_session_without_context_falls_through_to_older(self):
        self.put("old", (FIX / "transcript.jsonl").read_text(), 100)
        self.put("new", json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n", 200)
        self.assertEqual(S.latest_snapshot(self.proj, self.root).session, "old")

    def test_ansi_and_tool_result_ignored_fallback_to_usage(self):
        lines = [l for l in (FIX / "transcript.jsonl").read_text().splitlines()
                 if '"isMeta": true' not in l]
        self.put("s", "\n".join(lines) + "\nnot json\n", 100)
        f = S.latest_snapshot(self.proj, self.root)
        self.assertEqual((f.source, f.session), ("usage", "s"))
        self.assertEqual(f.snapshot.total, 6 + 20000 + 1500)
        self.assertEqual(f.snapshot.model, "claude-opus-5-5")
        self.assertTrue(f.snapshot.approx)
        self.assertEqual(f.snapshot.categories, {})

    def test_no_context_no_usage(self):
        self.put("s", json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n", 100)
        self.assertIsNone(S.latest_snapshot(self.proj, self.root))


if __name__ == "__main__":
    unittest.main()
