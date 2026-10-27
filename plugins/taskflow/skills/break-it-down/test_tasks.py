"""Tests for tasks.py: python3 -m unittest test_tasks (from this folder)."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402

TASKS_MD = """# Implementation tasks

## Task system

- **Inbox:** `note.md` (raw ideas)
- **Loop:** `/taskflow:loop-it`
- **Who:** interactive, opus, sonnet
- **Archived ids:** 1–9 (in `tasks/archive.md`)

## Index

{start}
{end}

Text after the index.
""".format(start=tasks.INDEX_START, end=tasks.INDEX_END)


def task_text(task_id, title="A task", mark="[ ]", status="not started", type_="feature",
              depends="—", who="opus", files="`src/a.py`", manual="Nothing to check by hand.",
              heading="Verification"):
    return (f"# Task {task_id}: {title}\n**Status:** {mark} {status}\n**Type:** {type_}\n"
            f"**Depends on:** {depends}\n**Who:** {who}\n**Files:** {files}\n"
            f"**Conventions:** `TASKS.md`.\n\n## Goal\nDo it.\n\n## {heading}\n{manual}\n")


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


class BacklogTest(BoardCase):
    def test_backlog_is_the_first_folder_and_hold_is_an_alias(self):
        self.assertEqual(tasks.STAGES[0].folder, "00_backlog")
        self.assertIs(tasks.resolve_stage("hold"), tasks.STAGES[0])

    def test_backlog_task_is_out_of_next_and_listed_last_in_the_index(self):
        self.add("backlog", "12_later.md", files="—")
        self.assertEqual(self.run_cmd("index")[0], 0)
        code, out = self.run_cmd("next")
        self.assertNotIn("12", out)
        text = self.index()
        self.assertGreater(text.index("Backlog (1)"), text.index("To be tested"))

    def test_ready_task_depending_on_backlog_warns_and_waits(self):
        self.add("backlog", "12_later.md", files="—")
        self.add("ready", "13_now.md", depends="Task 12", files="`a.py`")
        code, out = self.check()
        self.assertIn("in the backlog", out)
        self.assertIn("waits for 12", self.run_cmd("next")[1])


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

    def test_ready_task_needs_a_verification_section(self):
        path = self.add("ready", "10_a.md")
        path.write_text(path.read_text(encoding="utf-8").replace("## Verification", "## Notes"), encoding="utf-8")
        self.run_cmd("index")
        self.assertIn("missing `## Verification`", self.check()[1])

    def test_lessons_file_belongs_in_the_tasks_root(self):
        (self.root / "tasks" / "LESSONS.md").write_text("# Lessons of the Loop\n", encoding="utf-8")
        self.run_cmd("index")
        self.assertEqual(self.check()[0], 0)

    def test_legacy_manual_check_section_still_counts(self):
        self.add("ready", "10_a.md", heading="Manual check")
        self.run_cmd("index")
        self.assertEqual(self.check()[0], 0)

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
        self.assertIn("Open: 3 (to grill 0 · design gate 0 · ready 2 · real check 0 · to be tested 1 · backlog 0). Closed: 1", text)
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
        self.assertIn("**Status:** [~] code done; verification pending", moved.read_text(encoding="utf-8"))
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
        self.assertIn("3 tasks fit /taskflow:loop-it: propose it", out)
        self.assertIn("1 tasks wait for verification (the Loop runs it before new work)", out)
        self.assertNotIn("handed to the user", out)

    def test_next_and_checks_flag_a_verification_handed_to_the_user(self):
        self.add("to-be-tested", "9_t.md", mark="[~]", status="needs the user: a second machine", manual="1. Open Home.")
        self.add("to-be-tested", "8_u.md", mark="[~]", manual="1. Open Home.", heading="Manual check")
        out = self.run_cmd("next")[1]
        self.assertIn("1 tasks wait for verification", out)
        self.assertIn("Verification handed to the user: 9 (`checks`)", out)
        out = self.run_cmd("checks")[1]
        self.assertIn("(tasks/05_to-be-tested/9_t.md)  [needs the user]", out)
        self.assertIn("## Task 8: A task  (tasks/05_to-be-tested/8_u.md)\n1. Open Home.", out)

    def test_next_says_nothing_about_the_loop_for_a_single_task(self):
        self.add("ready", "10_a.md")
        self.assertNotIn("/taskflow:loop-it", self.run_cmd("next")[1])

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


class MigrateToolTest(BoardCase):
    OLD = ("- **Tool:** `python3 ~/.claude/skills/task-breakdown/tasks.py`\nRun /task-loop, see /task-breakdown notes, "
           "~/.claude/skills/task-breakdown/x, then /taskflow:task-loop 3 or /taskflow:task-breakdown checks\n")

    def setUp(self):
        super().setUp()
        profile = self.root / ".claude" / "agents" / "implementer.md"
        profile.parent.mkdir(parents=True)
        profile.write_text(self.OLD, encoding="utf-8")
        self.profile = profile

    def test_check_flags_the_old_tool(self):
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("OLD-TOOL .claude/agents/implementer.md", out)

    def test_migrate_rewrites_tool_and_commands_only(self):
        code, out = self.run_cmd("migrate-tool")
        self.assertEqual(code, 0)
        text = self.profile.read_text(encoding="utf-8")
        self.assertIn("`taskflow`", text)
        self.assertIn("/taskflow:loop-it", text)
        self.assertIn("/taskflow:break-it-down notes", text)
        self.assertIn("~/.claude/skills/task-breakdown/x", text)
        self.assertIn("/taskflow:loop-it 3 or /taskflow:break-it-down checks", text)
        self.assertEqual(self.check()[0], 0)

    def test_migrate_is_idempotent(self):
        self.run_cmd("migrate-tool")
        self.assertIn("nothing to migrate", self.run_cmd("migrate-tool")[1])


class ExclusiveTest(BoardCase):
    def lock(self):
        return tasks.lock_path(self.root)

    def test_runs_the_command_returns_its_code_and_releases_the_lock(self):
        if not tasks._shell():
            self.skipTest("bash not available")
        code, _ = self.run_cmd("exclusive", "true; exit 3")
        self.assertEqual(code, 3)
        self.assertFalse(self.lock().exists())

    def test_a_held_lock_makes_the_second_caller_wait_then_give_up(self):
        self.assertTrue(tasks.acquire_lock(self.lock(), "first", wait=0))
        self.assertFalse(tasks.acquire_lock(self.lock(), "second", wait=0))
        with mock.patch.object(tasks, "LOCK_POLL", 0.01):
            code, _ = self.run_cmd("exclusive", "--wait", "0.0005", "exit 0")
        self.assertEqual(code, tasks.EXIT_BUSY)
        self.assertIn("first", self.lock().read_text(encoding="utf-8"))

    def test_a_lock_nobody_refreshes_is_broken(self):
        self.assertTrue(tasks.acquire_lock(self.lock(), "dead holder", wait=0))
        self.assertTrue(tasks.acquire_lock(self.lock(), "next", wait=0, stale=-1))
        self.assertIn("next", self.lock().read_text(encoding="utf-8"))

    def test_worktrees_share_one_lock(self):
        def git(*args, cwd=self.root):
            return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
        if git("init").returncode != 0:
            self.skipTest("git not available")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "init")
        other = self.root.parent / (self.root.name + "-wt")
        self.addCleanup(lambda: git("worktree", "remove", "--force", str(other)))
        self.assertEqual(git("worktree", "add", str(other)).returncode, 0)
        self.assertEqual(tasks.lock_path(self.root).resolve(), tasks.lock_path(other).resolve())


class PluginVersionTest(unittest.TestCase):
    def test_version_file_matches_the_manifest(self):
        import json
        plugin = Path(__file__).resolve().parents[2]
        manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual((plugin / "VERSION").read_text(encoding="utf-8").strip(), manifest["version"])


class BoardTest(BoardCase):
    def board(self, *extra):
        code, out = self.run_cmd("board", "--plain", "--width", "120", *extra)
        self.assertEqual(code, 0)
        return out

    def chain(self):
        self.add("ready", "10_port.md", title="Port", files="`src/port.py`")
        self.add("ready", "11_endpoint.md", title="Endpoint", depends="Task 10", files="`src/api.py`")
        self.add("real-check", "12_printer.md", title="Printer", who="interactive", files="—")
        self.add("ready", "13_print.md", title="Print", depends="Task 11, Task 12", files="`src/print.py`")
        self.add("to-grill", "14_limits.md", title="Limits", files="—")
        self.run_cmd("index")

    def test_waves_follow_the_longest_chain(self):
        self.chain()
        view = tasks.BoardView(tasks.Board(self.root))
        self.assertEqual([[t.id for t in w] for w in view.waves], [["10", "12", "14"], ["11"], ["13"]])
        self.assertEqual([t.id for t in view.unlocks(view.board.open_by_id["10"])], ["11", "13"])

    def test_columns_roles_and_footer(self):
        self.chain()
        out = self.board()
        self.assertRegex(out.splitlines()[2], r"^NOW \(3\)\s+│ AFTER 1 \(1\)\s+│ AFTER 2 \(1\)$")
        self.assertRegex(out, r"● 10 Port\s+▶2")
        self.assertRegex(out, r"◆ 12 Printer\s+▶1")
        self.assertIn("◇ 14 Limits", out)
        self.assertIn("○ 13 Print", out)
        self.assertIn("← 11, 12 · opus", out)
        self.assertIn("Loop now:   /taskflow:loop-it 10\n", out)
        self.assertIn("Needs you:  12 real check ▶1 · 14 grill\n", out)
        self.assertIn("Bottleneck: 12 (real check) holds 13\n", out)
        self.assertNotIn("\033[", out)

    def test_narrow_terminal_stacks_the_waves(self):
        self.chain()
        out = self.run_cmd("board", "--plain", "--width", "60")[1]
        self.assertIn("NOW (3)\n● 10 Port", out)
        self.assertNotIn("│", out)

    def test_loop_groups_split_on_shared_files(self):
        self.add("ready", "10_a.md")
        self.add("ready", "11_b.md")
        self.add("ready", "12_c.md", files="`src/c.py`")
        self.assertIn("/taskflow:loop-it 10 12  (then 11: same files)", self.board())

    def test_backlog_and_missing_dependencies_hold_the_chain(self):
        self.add("backlog", "12_later.md", files="—")
        self.add("ready", "13_csv.md", title="CSV", depends="Task 12", files="`src/csv.py`")
        self.add("ready", "14_mail.md", title="Mail", depends="Task 13", files="`src/mail.py`")
        out = self.board()
        self.assertIn("Held:       13 CSV ← 12 in backlog", out)
        self.assertIn("Held:       14 Mail ← 13 held", out)
        self.assertNotIn("NOW", out)

    def test_to_be_tested_counts_as_done_and_errors_are_flagged(self):
        self.add("to-be-tested", "9_t.md", mark="[~]", manual="1. Open Home.")
        self.add("ready", "10_a.md", depends="Task 9")
        out = self.board()
        self.assertIn("● 10", out)
        self.assertIn("To test:    1 waiting for verification (`taskflow checks`)", out)
        self.assertIn("in the pipeline: run `taskflow check`", out)  # the index is stale after add()
        self.run_cmd("index")
        self.assertNotIn("in the pipeline", self.board())

    def test_empty_board(self):
        self.assertIn("Nothing active.", self.board())

    def test_interactive_needs_a_terminal(self):
        err = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO()), contextlib.redirect_stderr(err):
            code, _ = self.run_cmd("board", "-i")
        self.assertEqual(code, 2)
        self.assertIn("board -i needs a terminal: run it outside Claude Code", err.getvalue())

    def test_interactive_from_the_shell_without_a_tty(self):
        script = Path(tasks.__file__).resolve()
        done = subprocess.run([sys.executable, str(script), "--root", str(self.root), "board", "-i"],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("needs a terminal", done.stderr)

    def test_colour_only_when_asked_for(self):
        self.chain()
        text = tasks.render_board(tasks.Board(self.root), 120, color=True)
        self.assertIn("\033[32m●\033[0m", text)
