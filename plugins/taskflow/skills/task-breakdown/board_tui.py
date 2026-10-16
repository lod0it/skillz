"""State and actions of `taskflow board -i`, without drawing.

Everything the interactive board needs that is not curses: a cursor over the
waves, multi-selection, the highlighted chain, the detail box, the commands
behind the keys and change detection on `tasks/`. Nothing here touches the
terminal or runs a process: the builders return commands (`Command`) and the
curses layer runs them. This module must not import `curses` at module level.
"""

import os
import shlex
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402

DEFAULT_LOOP = "/taskflow:task-loop"


class Command(NamedTuple):
    argv: list
    stdin: str = None  # text to feed on standard input, when any
    note: str = ""     # what to tell the user about it


def columns(view):
    """The waves, then the held tasks as a last pseudo-column (they are in no wave)."""
    cols = [list(w) for w in view.waves if w]
    if view.held:
        cols.append(list(view.held))
    return cols


def column_label(view, index):
    """Header of column `index`, as `taskflow board` names them; HELD for the last pseudo-column."""
    if view.held and index == len(columns(view)) - 1:
        return "HELD"
    return "NOW" if index == 0 else f"AFTER {index}"


class Cursor:
    def __init__(self, view, task_id=None):
        self.view = view
        self.wave = 0
        self.row = 0
        self.columns = columns(view)
        if task_id is not None:
            self._seek(task_id)

    def _seek(self, task_id):
        for w, col in enumerate(self.columns):
            for r, t in enumerate(col):
                if t.id == task_id:
                    self.wave, self.row = w, r
                    return True
        return False

    @property
    def selected_task(self):
        if not self.columns:
            return None
        return self.columns[self.wave][self.row]

    def up(self):
        self.row = max(self.row - 1, 0)

    def down(self):
        if self.columns:
            self.row = min(self.row + 1, len(self.columns[self.wave]) - 1)

    def left(self):
        self._sideways(-1)

    def right(self):
        self._sideways(1)

    def _sideways(self, step):
        if not self.columns:
            return
        self.wave = min(max(self.wave + step, 0), len(self.columns) - 1)
        self.row = min(self.row, len(self.columns[self.wave]) - 1)

    def move(self, key):
        """`key` is one of up, down, left, right."""
        getattr(self, key)()

    def reload(self, view):
        """Use a fresh view; stay on the same task id, else on the nearest position."""
        current = self.selected_task.id if self.selected_task else None
        was = (self.wave, self.row)
        self.view = view
        self.columns = columns(view)
        if current is not None and self._seek(current):
            return
        if not self.columns:
            self.wave = self.row = 0
            return
        self.wave = min(was[0], len(self.columns) - 1)
        self.row = min(was[1], len(self.columns[self.wave]) - 1)


class Selection:
    """Multi-selection by task id (space toggles)."""

    def __init__(self):
        self.ids = set()

    def toggle(self, task):
        if task is not None:
            self.ids.symmetric_difference_update({task.id})

    def __contains__(self, task_id):
        return task_id in self.ids

    def clear(self):
        self.ids.clear()

    def prune(self, view):
        """Forget ids that left the active waves."""
        self.ids &= {t.id for t in view.tasks}

    def targets(self, cursor):
        """The selection, in the order the board prints it, or the cursor's task alone."""
        if self.ids:
            return [t for col in cursor.columns for t in col if t.id in self.ids]
        task = cursor.selected_task
        return [task] if task else []


def highlight(view, task):
    """Ids to draw bright: the task and the chain it releases; the rest is dimmed."""
    if task is None:
        return set()
    return {task.id} | {t.id for t in view.unlocks(task)}


def detail(view, task):
    """Lines of the detail box under the board."""
    if task is None:
        return ["Nothing selected."]
    waits = view.board.waits_for(task)
    released = view.unlocks(task)
    waits_line = "Waits for: " + (", ".join(waits) or "—")
    if task in view.held:
        waits_line += f" (held: {view.why_held(task)})"
    return [f"Task {task.id}: {task.title}",
            f"Who: {task.who or '—'} · {view.kind(task)} · {task.stage.name}",
            "Files: " + (", ".join(task.files) or "—"),
            waits_line,
            "Releases: " + (", ".join(t.id for t in released) or "—")]


# --- commands behind the keys ------------------------------------------------

def edit_command(task, env=None):
    env = os.environ if env is None else env
    return Command([env.get("EDITOR") or "vi", str(task.path)])


def stage_choices():
    """Stage names for the picker, in pipeline order."""
    return [s.name for s in tasks.STAGES]


def move_commands(targets, stage, note=None):
    """One `taskflow move` per target. Raises ValueError on an unknown stage."""
    try:
        resolved = tasks.resolve_stage(stage)
    except SystemExit as exc:
        raise ValueError(str(exc)) from None
    out = []
    for t in targets:
        argv = ["taskflow", "move", t.id, resolved.name]
        if note:
            argv += ["--note", note]
        out.append(Command(argv))
    return out


def loop_text(board, targets):
    command = board.config_code("loop") or DEFAULT_LOOP
    return command + " " + " ".join(t.id for t in targets)


def loop_command(board, targets, env=None):
    """Inside tmux a new window running claude; otherwise copy the command with pbcopy."""
    if not targets:
        return None
    env = os.environ if env is None else env
    text = loop_text(board, targets)
    if env.get("TMUX"):
        return Command(["tmux", "new-window", "-c", str(board.root), "claude " + shlex.quote(text)],
                       note=f"Loop started in a new tmux window: {text}")
    return Command(["pbcopy"], stdin=text, note=f"Not in tmux: copied `{text}`; paste it in Claude Code.")


# --- change detection ----------------------------------------------------------

def signature(root):
    """(path, mtime, size) of every file under tasks/ plus TASKS.md."""
    root = Path(root)
    paths = [root / "TASKS.md"]
    if (root / "tasks").is_dir():
        paths += sorted(p for p in (root / "tasks").rglob("*") if p.is_file())
    sig = []
    for p in paths:
        try:
            st = p.stat()
        except OSError:
            continue
        sig.append((str(p), st.st_mtime_ns, st.st_size))
    return tuple(sig)


class TasksWatcher:
    def __init__(self, root):
        self.root = Path(root)
        self._last = signature(self.root)

    def changed(self):
        """True once per change since the last call."""
        now = signature(self.root)
        if now == self._last:
            return False
        self._last = now
        return True
