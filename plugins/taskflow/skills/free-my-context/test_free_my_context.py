import json
import tempfile
import unittest
from pathlib import Path

import free_my_context as f


def tool(i, name, **inp):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": i, "name": name, "input": inp}]}}


class UsageTest(unittest.TestCase):
    def test_counts_tools_mcp_skills_and_dedupes_ids(self):
        with tempfile.TemporaryDirectory() as t:
            proj = Path(t) / "proj"
            proj.mkdir()
            d = f.transcripts_dir(proj, Path(t) / "projects")
            d.mkdir(parents=True)
            recs = [tool("1", "Bash"), tool("1", "Bash"), tool("2", "mcp__chrome__navigate"),
                    tool("3", "Skill", skill="/tdd"),
                    {"type": "user", "message": {"content":
                     "<command-name>/clear</command-name>"}}, "not json"]
            (d / "s.jsonl").write_text(
                "\n".join(r if isinstance(r, str) else json.dumps(r) for r in recs),
                encoding="utf-8")
            u = f.usage("here", proj, root=Path(t) / "projects")
            self.assertEqual(u["tools"]["Bash"], 1)
            self.assertEqual(u["mcp"], {"chrome": 1})
            self.assertEqual(u["skills"], {"tdd": 1, "clear": 1})

    def test_missing_folder_is_empty(self):
        with tempfile.TemporaryDirectory() as t:
            u = f.usage("here", t, root=Path(t) / "nope")
            self.assertEqual((u["tools"], u["sessions"]), ({}, 0))


class ApplyTest(unittest.TestCase):
    def run_apply(self, existing, plan):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / ".claude" / "settings.local.json"
            if existing is not None:
                p.parent.mkdir()
                p.write_text(json.dumps(existing), encoding="utf-8")
            data = f.apply(p, plan)
            return data, json.loads(p.read_text(encoding="utf-8")), list(p.parent.glob("*.bak-*"))

    def test_merges_without_touching_other_keys_and_backs_up(self):
        old = {"model": "sonnet", "permissions": {"allow": ["Bash(ls:*)"], "deny": ["X"]}}
        data, disk, baks = self.run_apply(old, {
            "deny": ["X", "WebFetch", "mcp__canva"], "skills": {"dataviz": "off"},
            "plugins_off": ["a@b"]})
        self.assertEqual(data, disk)
        self.assertEqual(disk["model"], "sonnet")
        self.assertEqual(disk["permissions"]["allow"], ["Bash(ls:*)"])
        self.assertEqual(disk["permissions"]["deny"], ["X", "WebFetch", "mcp__canva"])
        self.assertEqual(disk["skillOverrides"], {"dataviz": "off"})
        self.assertEqual(disk["enabledPlugins"], {"a@b": False})
        self.assertEqual(len(baks), 1)

    def test_creates_missing_file_without_backup(self):
        _, disk, baks = self.run_apply(None, {"deny": ["Agent"]})
        self.assertEqual(disk, {"permissions": {"deny": ["Agent"]}})
        self.assertEqual(baks, [])

    def test_empty_plan_adds_nothing(self):
        _, disk, _ = self.run_apply(None, {})
        self.assertEqual(disk, {})

    def test_refuses_core_tools_and_bad_state(self):
        for plan in ({"deny": ["Bash"]}, {"skills": {"free-my-context": "off"}},
                     {"skills": {"x": "maybe"}}):
            with self.assertRaises(ValueError):
                self.run_apply(None, plan)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "s.json"
            f.apply(p, {"deny": ["Agent"]}, dry_run=True)
            self.assertFalse(p.exists())


if __name__ == "__main__":
    unittest.main()
