"""Tests for board_tui.py: python3 -m unittest test_board_tui (from this folder)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_tui as bt  # noqa: E402
import tasks  # noqa: E402
from test_tasks import BoardCase  # noqa: E402


class TuiCase(BoardCase):
    def chain(self):
        self.add("ready", "10_port.md", title="Port", files="`src/port.py`")
        self.add("ready", "11_endpoint.md", title="Endpoint", depends="Task 10", files="`src/api.py`")
        self.add("real-check", "12_printer.md", title="Printer", who="interactive", files="—")
        self.add("ready", "13_print.md", title="Print", depends="Task 11, Task 12", files="`src/print.py`")
        self.add("to-grill", "14_limits.md", title="Limits", files="—")
        self.add("backlog", "20_later.md", files="—")
        self.add("ready", "21_after_later.md", depends="Task 20", files="`src/z.py`")
        self.run_cmd("index")

    def view(self):
        return tasks.BoardView(tasks.Board(self.root))


class CursorTest(TuiCase):
    def test_moves_are_clamped(self):
        self.chain()
        c = bt.Cursor(self.view())
        self.assertEqual(c.selected_task.id, "10")
        c.up()
        c.left()
        self.assertEqual((c.wave, c.row), (0, 0))
        for _ in range(4):
            c.down()
        self.assertEqual(c.row, 2)
        c.right()
        self.assertEqual((c.wave, c.row, c.selected_task.id), (1, 0, "11"))
        for _ in range(9):
            c.right()
        self.assertEqual(c.wave, len(c.columns) - 1)

    def test_held_tasks_are_the_last_column(self):
        self.chain()
        v = self.view()
        last = len(bt.columns(v)) - 1
        self.assertEqual([t.id for t in bt.columns(v)[-1]], ["21"])
        self.assertEqual(bt.column_label(v, last), "HELD")
        self.assertEqual(bt.column_label(v, 0), "NOW")
        self.assertEqual(bt.column_label(v, 1), "AFTER 1")

    def test_reload_keeps_the_task_id(self):
        self.chain()
        c = bt.Cursor(self.view(), "11")
        self.add("ready", "9_new.md", files="`src/n.py`", title="New")
        c.reload(self.view())
        self.assertEqual(c.selected_task.id, "11")

    def test_reload_falls_back_to_nearest_position(self):
        self.chain()
        c = bt.Cursor(self.view(), "14")
        self.assertEqual((c.wave, c.row), (0, 2))
        self.run_cmd("move", "14", "done")
        c.reload(self.view())
        self.assertEqual((c.wave, c.row), (0, 1))
        self.assertEqual(c.selected_task.id, "12")
        self.run_cmd("move", "12", "done")
        self.run_cmd("move", "10", "done")
        c.reload(self.view())
        self.assertIsNotNone(c.selected_task)

    def test_empty_board(self):
        c = bt.Cursor(self.view())
        self.assertIsNone(c.selected_task)
        c.down()
        c.right()
        c.reload(self.view())
        self.assertIsNone(c.selected_task)
        self.assertEqual(bt.detail(self.view(), None), ["Nothing selected."])


class SelectionTest(TuiCase):
    def test_targets_are_selection_in_board_order_or_cursor(self):
        self.chain()
        b = tasks.Board(self.root)
        c = bt.Cursor(self.view(), "11")
        s = bt.Selection()
        self.assertEqual([t.id for t in s.targets(c)], ["11"])
        s.toggle(b.open_by_id["13"])
        s.toggle(b.open_by_id["10"])
        self.assertEqual([t.id for t in s.targets(c)], ["10", "13"])
        s.toggle(b.open_by_id["13"])
        self.assertNotIn("13", s)
        s.toggle(b.open_by_id["11"])
        self.run_cmd("move", "11", "done")
        s.prune(self.view())
        self.assertEqual(s.ids, {"10"})


class HighlightDetailTest(TuiCase):
    def test_highlight_is_task_plus_chain(self):
        self.chain()
        v = self.view()
        self.assertEqual(bt.highlight(v, v.board.open_by_id["10"]), {"10", "11", "13"})
        self.assertEqual(bt.highlight(v, v.board.open_by_id["13"]), {"13"})

    def test_detail(self):
        self.chain()
        v = self.view()
        lines = bt.detail(v, v.board.open_by_id["13"])
        self.assertEqual(lines[0], "Task 13: Print")
        self.assertIn("Files: src/print.py", lines)
        self.assertIn("Waits for: 11, 12", lines)
        self.assertIn("Releases: —", lines)
        self.assertIn("Releases: 11, 13", bt.detail(v, v.board.open_by_id["10"]))
        self.assertIn("real check", bt.detail(v, v.board.open_by_id["12"])[1])
        self.assertIn("(held: 20 in backlog)", bt.detail(v, v.board.open_by_id["21"])[3])


class ActionTest(TuiCase):
    def test_edit(self):
        self.chain()
        t = self.view().board.open_by_id["10"]
        self.assertEqual(bt.edit_command(t, {"EDITOR": "nano"}).argv, ["nano", str(t.path)])
        self.assertEqual(bt.edit_command(t, {}).argv[0], "vi")

    def test_move(self):
        self.chain()
        b = self.view().board
        cmds = bt.move_commands([b.open_by_id["10"], b.open_by_id["11"]], "tested", "ok")
        self.assertEqual([c.argv for c in cmds], [
            ["taskflow", "move", "10", "to-be-tested", "--note", "ok"],
            ["taskflow", "move", "11", "to-be-tested", "--note", "ok"]])
        self.assertEqual(bt.move_commands([b.open_by_id["10"]], "done")[0].argv, ["taskflow", "move", "10", "done"])
        with self.assertRaises(ValueError):
            bt.move_commands([b.open_by_id["10"]], "nowhere")
        self.assertEqual(bt.stage_choices()[0], "backlog")

    def test_loop_in_tmux_and_outside(self):
        self.chain()
        b = self.view().board
        ts = [b.open_by_id["10"], b.open_by_id["12"]]
        c = bt.loop_command(b, ts, {"TMUX": "/tmp/tmux-1/default,1,0"})
        self.assertEqual(c.argv[:2], ["tmux", "new-window"])
        self.assertEqual(c.argv[-1], "claude '/taskflow:task-loop 10 12'")
        c = bt.loop_command(b, ts, {})
        self.assertEqual((c.argv, c.stdin), (["pbcopy"], "/taskflow:task-loop 10 12"))
        self.assertIsNone(bt.loop_command(b, [], {}))

    def test_loop_name_comes_from_config(self):
        self.chain()
        md = self.root / "TASKS.md"
        md.write_text(md.read_text().replace("`/taskflow:task-loop`", "`/my:loop`"), encoding="utf-8")
        b = tasks.Board(self.root)
        self.assertEqual(bt.loop_text(b, [b.open_by_id["10"]]), "/my:loop 10")


class WatcherTest(TuiCase):
    def test_changed_once_per_change(self):
        self.chain()
        w = bt.TasksWatcher(self.root)
        self.assertFalse(w.changed())
        path = self.root / "tasks" / "03_ready" / "10_port.md"
        path.write_text(path.read_text() + "x", encoding="utf-8")
        self.assertTrue(w.changed())
        self.assertFalse(w.changed())
        self.run_cmd("move", "10", "done")
        self.assertTrue(w.changed())
        (self.root / "TASKS.md").write_text("changed\n", encoding="utf-8")
        self.assertTrue(w.changed())

    def test_no_curses_at_module_level(self):
        self.assertNotIn("curses", vars(bt))


if __name__ == "__main__":
    unittest.main()
