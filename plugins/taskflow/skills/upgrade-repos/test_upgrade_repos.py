"""Tests for upgrade_repos.py: python3 -m unittest test_upgrade_repos (from this folder)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upgrade_repos as up  # noqa: E402

TASKS_MD = "# Tasks\n\n## Task system\n\n- **Tool:** `taskflow`\n\n## Index\n\n{}\n{}\n".format(
    up.tasks.INDEX_START, up.tasks.INDEX_END)
OLD_TASKS_MD = TASKS_MD.replace("`taskflow`", "`python3 ~/.claude/skills/task-breakdown/tasks.py`")


def make_repo(root, name, tasks_md=TASKS_MD, lessons="# Lessons\n\n- a lesson\n", git=True):
    repo = Path(root) / name
    (repo / "tasks").mkdir(parents=True)
    (repo / "TASKS.md").write_text(tasks_md, encoding="utf-8")
    for stage in up.tasks.STAGES:
        (repo / "tasks" / stage.folder).mkdir()
        (repo / "tasks" / stage.folder / ".gitkeep").write_text("")
    if lessons is not None:
        (repo / "tasks" / "LESSONS.md").write_text(lessons, encoding="utf-8")
    if git:
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                     ["add", "-A"], ["commit", "-qm", "init"]):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


class UpgradeReposTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(up, "SNOOZE", self.root / "snooze.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_scan_classifies_repos(self):
        make_repo(self.root, "fresh", lessons=up.tasks.LESSONS_TEMPLATE)
        make_repo(self.root, "oldlessons")
        make_repo(self.root, "oldtool", tasks_md=OLD_TASKS_MD, lessons=up.tasks.LESSONS_TEMPLATE)
        legacy = make_repo(self.root, "legacy", lessons=up.tasks.LESSONS_TEMPLATE)
        (legacy / "tasks" / "old_stage").mkdir()
        (self.root / "plain").mkdir()
        states = {Path(a["repo"]).name: a["state"] for a in up.scan(self.root)}
        self.assertEqual(states, {"fresh": "ok", "oldlessons": "auto", "oldtool": "auto", "legacy": "manual"})

    def test_apply_upgrades_and_commits(self):
        repo = make_repo(self.root, "old", tasks_md=OLD_TASKS_MD)
        status, detail = up.apply_repo(repo, commit=True)
        self.assertEqual(status, "upgraded", detail)
        self.assertIn("0 errors", detail)
        self.assertEqual(up.assess(repo)["state"], "ok")
        self.assertEqual(up.git(repo, "status", "--porcelain")[1], "")
        self.assertIn("taskflow: upgrade", up.git(repo, "log", "-1", "--format=%s")[1])

    def test_apply_without_commit_leaves_changes(self):
        repo = make_repo(self.root, "old")
        self.assertEqual(up.apply_repo(repo)[0], "upgraded")
        self.assertNotEqual(up.git(repo, "status", "--porcelain")[1], "")

    def test_apply_skips_dirty_and_manual_and_ok(self):
        dirty = make_repo(self.root, "dirty")
        (dirty / "scratch.txt").write_text("x")
        self.assertEqual(up.apply_repo(dirty)[0], "skipped")
        legacy = make_repo(self.root, "legacy")
        (legacy / "tasks" / "old_stage").mkdir()
        self.assertEqual(up.apply_repo(legacy)[0], "manual")  # an empty folder is not tracked: the repo is clean
        fresh = make_repo(self.root, "fresh", lessons=up.tasks.LESSONS_TEMPLATE)
        self.assertEqual(up.apply_repo(fresh)[0], "ok")

    def test_hint_names_old_repos_and_respects_snooze(self):
        old = make_repo(self.root, "old")
        make_repo(self.root, "fresh", lessons=up.tasks.LESSONS_TEMPLATE)
        out = up.hint(self.root)
        text = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn(str(old.resolve()), text)
        self.assertNotIn("fresh", text)
        up.snooze([old])
        self.assertIsNone(up.hint(self.root))

    def test_hint_silent_when_all_ok(self):
        make_repo(self.root, "fresh", lessons=up.tasks.LESSONS_TEMPLATE)
        self.assertIsNone(up.hint(self.root))

    def test_hint_command_prints_json(self):
        make_repo(self.root, "old")
        r = subprocess.run([sys.executable, str(Path(up.__file__)), "hint"], cwd=self.root,
                           capture_output=True, text=True, env={"HOME": str(self.root), "USERPROFILE": str(self.root)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")


if __name__ == "__main__":
    unittest.main()
