"""Tests for tasks.py: python3 -m unittest test_tasks (from this folder)."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402

TASKS_MD = """# Implementation tasks

## Task system

- **Inbox:** `note.md` (raw ideas)
- **Loop:** `/task-loop`
- **Who:** interactive, opus, sonnet
- **Archived ids:** 1–9 (in `tasks/archive.md`)

## Index

{start}
{end}

Text after the index.
""".format(start=tasks.INDEX_START, end=tasks.INDEX_END)


def task_text(task_id, title="A task", mark="[ ]", status="not started", type_="feature",
              depends="—", who="opus", files="`src/a.py`", manual="Nothing to check by hand."):
    return (f"# Task {task_id}: {title}\n**Status:** {mark} {status}\n**Type:** {type_}\n"
            f"**Depends on:** {depends}\n**Who:** {who}\n**Files:** {files}\n"
            f"**Conventions:** `TASKS.md`.\n\n## Goal\nDo it.\n\n## Manual check\n{manual}\n")


class BoardCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        (self.root / "TASKS.md").write_text(TASKS_MD, encoding="utf-8")
        self.run_cmd("init")

    def run_cmd(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = tasks.main(["--root", str(self.root), *argv])
            except SystemExit as exc:
                return 2, str(exc)
        return code, out.getvalue()

    def add(self, stage, name, **kwargs):
        task_id = tasks.FILE_RE.match(name).group(1)
        path = self.root / "tasks" / tasks.resolve_stage(stage).folder / name
        path.write_text(task_text(task_id, **kwargs), encoding="utf-8")
        return path

    def check(self):
        code, out = self.run_cmd("check")
        return code, out

    def index(self):
        return (self.root / "TASKS.md").read_text(encoding="utf-8")


class InitTest(BoardCase):
    def test_creates_every_stage_folder_with_gitkeep(self):
        for stage in tasks.STAGES:
            folder = self.root / "tasks" / stage.folder
            self.assertTrue(folder.is_dir(), stage.folder)
        self.assertTrue((self.root / "tasks" / "03_ready" / ".gitkeep").is_file())

    def test_creates_tasks_md_from_the_template_when_missing(self):
        (self.root / "TASKS.md").unlink()
        self.assertEqual(self.run_cmd("init")[0], 0)
        text = self.index()
        self.assertIn("## Task system", text)
        self.assertIn("### 03 Ready (0)", text)
        self.assertEqual(self.check()[0], 0)

    def test_empty_board_passes_check(self):
        self.assertEqual(self.check()[0], 0)


class ParseTest(unittest.TestCase):
    def test_depends(self):
        self.assertEqual(tasks.parse_depends("Task 93a, Task 74c (same file)"), (["93a", "74c"], None))
        self.assertEqual(tasks.parse_depends("Tasks 48, 49"), (["48", "49"], None))
        for nothing in ("—", "none", ""):
            self.assertEqual(tasks.parse_depends(nothing), ([], None))
        self.assertIsNotNone(tasks.parse_depends("Tasks 59–67")[1])
        self.assertIsNotNone(tasks.parse_depends("Task 61; the base is Task 51")[1])

    def test_paths_overlap(self):
        self.assertTrue(tasks.paths_overlap("web/app.js", "web/app.js"))
        self.assertTrue(tasks.paths_overlap("board_core/stt_*.py", "board_core/stt_engine.py"))
        self.assertTrue(tasks.paths_overlap("tests/", "tests/test_web.py"))
        self.assertFalse(tasks.paths_overlap("web/app.js", "web/demo.js"))

    def test_set_field_replaces_or_inserts_in_order(self):
        text = "# Task 1: T\n**Status:** [ ] x\n**Depends on:** —\n**Conventions:** c\n\n## Goal\n"
        text = tasks.set_field(text, "Type", "bug")
        text = tasks.set_field(text, "Files", "`a.py`")
        text = tasks.set_field(text, "Who", "opus")
        text = tasks.set_field(text, "Depends on", "Task 2")
        header = text.split("\n\n")[0].splitlines()
        self.assertEqual(header, ["# Task 1: T", "**Status:** [ ] x", "**Type:** bug", "**Depends on:** Task 2",
                                  "**Who:** opus", "**Files:** `a.py`", "**Conventions:** c"])


class CheckTest(BoardCase):
    def test_clean_board(self):
        self.add("ready", "10_first.md")
        self.run_cmd("index")
        code, out = self.check()
        self.assertEqual((code, out.strip()), (0, "0 errors, 0 warnings"))

    def test_reports_each_kind_of_error(self):
        self.add("ready", "10_first.md", mark="[x]", type_="chore", who="haiku", depends="Task 77", files="—")
        self.add("ready", "11-Bad-Name.md")
        path = self.add("to-grill", "12_idea.md")
        path.write_text("# Task 99: Wrong id\n**Status:** [ ] to grill\n", encoding="utf-8")
        (self.root / "tasks" / "features").mkdir()
        (self.root / "tasks" / "features" / "13_old.md").write_text("x", encoding="utf-8")
        code, out = self.check()
        self.assertEqual(code, 1)
        for expected in ("Status mark is [x], the folder means [ ]", "Type `chore`", "Who `haiku`",
                         "depends on Task 77, which has no file", "names the files it touches",
                         "11-Bad-Name.md: name must be", "the title says Task 99, the file name says 12",
                         "missing `**Type:**`", "LEGACY tasks/features/ (1 task files)",
                         "the index in TASKS.md is stale"):
            self.assertIn(expected, out)

    def test_archived_and_closed_dependencies_are_known(self):
        self.add("done", "20-old-style.md", mark="[x]", status="done")
        self.add("ready", "21_next.md", depends="Task 20, Task 3")
        self.run_cmd("index")
        self.assertEqual(self.check()[0], 0)

    def test_dependency_cycle(self):
        self.add("ready", "10_a.md", depends="Task 11")
        self.add("ready", "11_b.md", depends="Task 10", files="`src/b.py`")
        self.assertIn("dependency cycle", self.check()[1])

    def test_overlap_between_startable_tasks_is_a_warning(self):
        self.add("ready", "10_a.md")
        self.add("ready", "11_b.md")
        self.add("ready", "12_c.md", depends="Task 10")
        self.run_cmd("index")
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("Tasks 10 and 11 are both ready and both touch src/a.py", out)
        self.assertNotIn("and 12 are both", out)

    def test_to_be_tested_without_steps_belongs_in_done(self):
        self.add("to-be-tested", "10_a.md", mark="[~]")
        self.assertIn("nothing to check by hand, so it belongs in 99_done", self.check()[1])

    def test_closed_tasks_are_never_validated(self):
        (self.root / "tasks" / "99_done" / "36b-one.md").write_text("# Task 36b: One\n**Status:** superseded\n")
        (self.root / "tasks" / "99_done" / "36b-two.md").write_text("no header at all\n")
        self.run_cmd("index")
        self.assertEqual(self.check()[0], 0)


class IndexTest(BoardCase):
    def test_lists_open_tasks_by_stage_and_keeps_the_surrounding_text(self):
        self.add("ready", "10_first.md", title="First | piped")
        self.add("ready", "11_second.md", depends="Task 10", files="`src/b.py`")
        self.add("to-be-tested", "9_tested.md", mark="[~]", manual="1. Open Home.")
        self.add("done", "8_closed.md", mark="[x]", status="done")
        self.run_cmd("index")
        text = self.index()
        self.assertIn("Open: 3 (to grill 0 · design gate 0 · ready 2 · real check 0 · to be tested 1). Closed: 1", text)
        self.assertIn("| 10 First \\| piped | `tasks/03_ready/10_first.md` | not started | — | feature | opus |", text)
        self.assertIn("| 11 A task | `tasks/03_ready/11_second.md` | not started | 10 | feature | opus |", text)
        self.assertNotIn("8_closed", text)
        self.assertTrue(text.rstrip().endswith("Text after the index."))
        done = (self.root / "tasks" / "99_done" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("| 8 A task | `8_closed.md` | [x] done |", done)

    def test_is_stable(self):
        self.add("ready", "10_first.md")
        self.run_cmd("index")
        first = self.index()
        self.run_cmd("index")
        self.assertEqual(first, self.index())

    def test_sorts_ids_naturally(self):
        for name in ("100_c.md", "9_a.md", "93b_x.md", "93a_y.md", "93_z.md"):
            self.add("to-grill", name, files="—")
        self.run_cmd("index")
        text = self.index()
        order = [text.index(f"| {i} A task") for i in ("9", "93", "93a", "93b", "100")]
        self.assertEqual(order, sorted(order))


class MoveTest(BoardCase):
    def test_moves_sets_status_and_regenerates_the_index(self):
        self.add("ready", "10_first.md")
        code, out = self.run_cmd("move", "10", "to-be-tested")
        self.assertEqual(code, 0)
        moved = self.root / "tasks" / "05_to-be-tested" / "10_first.md"
        self.assertIn("**Status:** [~] code done; manual check pending", moved.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "tasks" / "03_ready" / "10_first.md").exists())
        self.assertIn("`tasks/05_to-be-tested/10_first.md`", self.index())

    def test_done_with_note_and_rejected(self):
        self.add("ready", "10_first.md")
        self.add("to-grill", "11_idea.md", files="—")
        self.run_cmd("move", "10", "done", "--note", "done; check failed, fixed by Task 12")
        self.run_cmd("move", "11", "99", "--rejected")
        done = self.root / "tasks" / "99_done"
        self.assertIn("**Status:** [x] done; check failed, fixed by Task 12", (done / "10_first.md").read_text())
        self.assertIn("**Status:** [-] rejected", (done / "11_idea.md").read_text())
        self.assertEqual(self.check()[0], 0)

    def test_same_stage_only_fixes_the_mark(self):
        self.add("ready", "10_first.md", mark="[x]", status="half way")
        self.run_cmd("move", "10", "ready")
        text = (self.root / "tasks" / "03_ready" / "10_first.md").read_text(encoding="utf-8")
        self.assertIn("**Status:** [ ] half way", text)

    def test_edits_stand_when_tasks_md_has_no_markers_yet(self):
        self.add("ready", "10_first.md")
        (self.root / "TASKS.md").write_text("# Tasks\n", encoding="utf-8")
        code, out = self.run_cmd("set", "10", "Who", "sonnet")
        self.assertEqual(code, 0)
        self.assertIn("index not rewritten", out)
        self.assertEqual(self.run_cmd("move", "10", "done")[0], 0)
        self.assertTrue((self.root / "tasks" / "99_done" / "10_first.md").is_file())

    def test_unknown_task_or_stage(self):
        self.assertEqual(self.run_cmd("move", "77", "done")[0], 2)
        self.add("ready", "10_first.md")
        self.assertEqual(self.run_cmd("move", "10", "nowhere")[0], 2)

    def test_uses_git_mv_for_tracked_files(self):
        def git(*args):
            return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
        if git("init").returncode != 0:
            self.skipTest("git not available")
        self.add("ready", "10_first.md")
        git("add", "-A")
        self.run_cmd("move", "10", "done")
        status = git("status", "--porcelain").stdout
        self.assertIn("tasks/99_done/10_first.md", status)
        self.assertNotIn("?? tasks/99_done/10_first.md", status)


class AdoptAndSetTest(BoardCase):
    def test_adopt_renames_and_keeps_the_status_text(self):
        legacy = self.root / "tasks" / "to-be-tested"
        legacy.mkdir()
        (legacy / "66-Mini-atures.md").write_text(task_text("66", mark="[x]", status="code done; browser pending"))
        code, out = self.run_cmd("adopt", "tasks/to-be-tested/66-Mini-atures.md", "to-be-tested")
        self.assertEqual(code, 0, out)
        text = (self.root / "tasks" / "05_to-be-tested" / "66_mini_atures.md").read_text(encoding="utf-8")
        self.assertIn("**Status:** [~] code done; browser pending", text)

    def test_adopt_into_done_leaves_the_file_alone(self):
        legacy = self.root / "tasks" / "done"
        legacy.mkdir()
        (legacy / "5-old.md").write_text("# Task 5: Old\n**Status:** finished\n")
        self.run_cmd("adopt", "tasks/done/5-old.md", "done")
        self.assertEqual((self.root / "tasks" / "99_done" / "5-old.md").read_text(), "# Task 5: Old\n**Status:** finished\n")

    def test_set_updates_the_file_and_the_index(self):
        self.add("ready", "10_first.md")
        self.add("ready", "11_second.md", files="`src/b.py`")
        self.run_cmd("set", "11", "depends on", "Task 10")
        self.assertIn("| 11 A task | `tasks/03_ready/11_second.md` | not started | 10 |", self.index())
        self.assertEqual(self.run_cmd("set", "11", "Status", "[x] done")[0], 2)


class ReportsTest(BoardCase):
    def test_next_separates_loopable_blocked_and_disjoint(self):
        self.add("ready", "10_a.md")
        self.add("ready", "11_b.md")
        self.add("ready", "12_c.md", files="`src/c.py`")
        self.add("ready", "13_d.md", who="interactive", files="`src/d.py`")
        self.add("ready", "14_e.md", depends="Task 10", files="`src/e.py`")
        self.add("to-be-tested", "9_t.md", mark="[~]", manual="1. Open Home.")
        self.add("real-check", "15_f.md", who="interactive", files="—")
        self.add("real-check", "16_g.md", who="interactive", files="—", depends="Task 14")
        out = self.run_cmd("next")[1]
        self.assertIn("Real checks unblocked, with the user only: 15\n", out)
        self.assertIn("Ready and unblocked (4):", out)
        self.assertIn("  loop  10 ", out)
        self.assertIn("  you   13 ", out)
        self.assertIn("  14    waits for 10", out)
        self.assertIn("side by side in separate worktrees: [10, 12]  [11]", out)
        self.assertIn("3 tasks fit /task-loop: propose it", out)
        self.assertIn("1 tasks wait for the user's manual check", out)

    def test_next_says_nothing_about_the_loop_for_a_single_task(self):
        self.add("ready", "10_a.md")
        self.assertNotIn("/task-loop", self.run_cmd("next")[1])

    def test_dependency_on_a_to_be_tested_task_is_satisfied(self):
        self.add("to-be-tested", "9_t.md", mark="[~]", manual="1. Open Home.")
        self.add("ready", "10_a.md", depends="Task 9")
        self.assertIn("Ready and unblocked (1):", self.run_cmd("next")[1])

    def test_checks_prints_every_manual_check(self):
        self.add("to-be-tested", "9_t.md", title="Voice", mark="[~]", manual="1. Open Home.\n2. Hold the mic.")
        out = self.run_cmd("checks")[1]
        self.assertIn("## Task 9: Voice  (tasks/05_to-be-tested/9_t.md)", out)
        self.assertIn("2. Hold the mic.", out)

    def test_status_counts_and_inbox(self):
        self.add("ready", "10_a.md")
        (self.root / "note.md").write_text("an idea\n\nanother\n", encoding="utf-8")
        out = self.run_cmd("status")[1]
        self.assertRegex(out, r"03_ready\s+1  10")
        self.assertIn("inbox note.md: 2 non-empty lines", out)

    def test_next_id_counts_files_and_archived_ids(self):
        self.assertEqual(self.run_cmd("next-id")[1].strip(), "10")
        self.add("to-grill", "41b_x.md", files="—")
        self.add("done", "57-old.md", mark="[x]", status="done")
        self.assertEqual(self.run_cmd("next-id")[1].strip(), "58")


if __name__ == "__main__":
    unittest.main()
