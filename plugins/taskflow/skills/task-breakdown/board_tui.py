"""State and actions of `taskflow board -i`, without drawing.

Everything the interactive board needs that is not curses: a cursor over the
waves, multi-selection, the highlighted chain, the detail box, the commands
behind the keys and change detection on `tasks/`. Nothing here touches the
terminal or runs a process: the builders return commands (`Command`) and the
curses layer runs them. This module must not import `curses` at module level.
"""

import locale
import os
import shlex
import subprocess
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
    editor = shlex.split(env.get("EDITOR") or "") or ["vi"]  # EDITOR may carry flags: "code -w"
    return Command(editor + [str(task.path)])


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


# --- the screen ----------------------------------------------------------------
# Pure helpers first (tested without a terminal), then `Screen`, the curses
# layer, which `run` builds after importing curses.

HELP = "↑↓←→ move  ⏎ edit  m move to stage  space select  l Loop  esc clear  q quit"
SEP = " │ "
GUTTER = 1          # a mark left of each cell: * for the multi-selection
DETAIL_HEIGHT = 7   # the five lines of detail() inside a border
POLL_MS = 500       # how often getch gives up waiting to look at tasks/
MIN_SIZE = (10, 40)  # rows, columns


class Spans:
    """Text as (text, style) pieces: what `board_cell` paints, with no escape codes."""

    def __init__(self, pieces=()):
        self.pieces = [p for p in pieces if p[0]]

    def __add__(self, other):
        if isinstance(other, Spans):
            return Spans(self.pieces + other.pieces)
        if isinstance(other, str):
            return Spans(self.pieces + [(other, None)])
        return NotImplemented

    def __radd__(self, other):
        if isinstance(other, str):
            return Spans([(other, None)] + self.pieces)
        return NotImplemented

    def __str__(self):
        return "".join(text for text, _ in self.pieces)

    def __len__(self):
        return len(str(self))


def span_paint(text, style):
    """The `paint` argument of `board_cell` for curses: styles stay names (keys of tasks.ANSI)."""
    return Spans([(text, style)])


def cell_lines(view, task, width):
    """The two lines `taskflow board` draws for a task, as Spans."""
    return [line if isinstance(line, Spans) else Spans([(line, None)])
            for line in tasks.board_cell(view, task, width, span_paint)]


def cell_mode(task, cursor_task, bright):
    """How to draw a cell: cursor, bright (in the chain), dim (outside it) or normal.

    The rest is dimmed only when the cursor's task releases something: otherwise
    the whole board would lose its colours whenever a leaf task is selected."""
    if cursor_task is not None and task.id == cursor_task.id:
        return "cursor"
    if len(bright) > 1:
        return "bright" if task.id in bright else "dim"
    return "normal"


def follow(offset, pos, size, total):
    """Scroll offset that keeps `pos` inside a window of `size` over `total` items."""
    size = max(size, 1)
    if pos < offset:
        offset = pos
    elif pos >= offset + size:
        offset = pos - size + 1
    return max(0, min(offset, max(total - size, 0)))


def fit_columns(count, width):
    """(columns shown, cell width): as many columns as fit at tasks.COLUMN[0] or wider."""
    if count == 0:
        return 0, 0

    def cell(n):
        return min((width - len(SEP) * (n - 1)) // n - GUTTER, tasks.COLUMN[1])

    shown = count
    while shown > 1 and cell(shown) < tasks.COLUMN[0]:
        shown -= 1
    return shown, cell(shown)


def header(board, view, errors):
    """(title, summary, warning) of the top line, as `taskflow board` words them."""
    summary = (f"  {len(view.tasks)} active · {len(board.in_stage('backlog'))} backlog · "
               f"{len(board.in_stage('to-be-tested'))} to test · {len(board.closed)} done")
    warning = f"  ⚠ {errors} error{'s' if errors > 1 else ''}: run `taskflow check`" if errors else ""
    return "taskflow board", summary, warning


RAW_ARROWS = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}


def raw_arrow(keys):
    """UP/DOWN/RIGHT/LEFT for the keys after an ESC that spell an arrow (`[B`, `OB`), else None."""
    if len(keys) == 2 and keys[0] in ("[", "O") and keys[1] in RAW_ARROWS:
        return RAW_ARROWS[keys[1]]
    return None


def runnable(argv, root):
    """`taskflow ...` through this very tasks.py: `taskflow` need not be on PATH outside Claude Code."""
    if argv and argv[0] == "taskflow":
        return [sys.executable, str(Path(tasks.__file__).resolve()), "--root", str(root)] + list(argv[1:])
    return list(argv)


def execute(command, root):
    """Run a command that needs no terminal; (exit code, its last line of output)."""
    try:
        done = subprocess.run(runnable(command.argv, root), input=command.stdin, cwd=str(root),
                              capture_output=True, text=True)
    except OSError as exc:
        return 127, str(exc)
    lines = [l for l in (done.stdout + "\n" + done.stderr).splitlines() if l.strip()]
    return done.returncode, (lines[-1].strip() if lines else "")


def run(root):
    """Open the interactive board on the repo at `root`; returns the exit code."""
    import curses
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")  # Esc answers at once instead of after a second
    return curses.wrapper(lambda scr: Screen(curses, scr, root).main())


class Screen:
    def __init__(self, curses, scr, root):
        self.c = curses
        self.scr = scr
        self.root = Path(root)
        self.watcher = TasksWatcher(self.root)
        self.selection = Selection()
        self.message = ""
        self.first = 0  # leftmost column shown
        self.top = 0    # first task row shown
        self.board = tasks.Board(self.root)
        self.view = tasks.BoardView(self.board)
        self.errors = len(tasks.check(self.board)[0])
        self.cursor = Cursor(self.view)
        self.attrs = self._attrs()
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        scr.keypad(True)
        scr.timeout(POLL_MS)

    # --- state

    def reload(self):
        self.board = tasks.Board(self.root)
        self.view = tasks.BoardView(self.board)
        self.errors = len(tasks.check(self.board)[0])
        self.cursor.reload(self.view)
        self.selection.prune(self.view)
        self.watcher.changed()  # our own writes are not news

    def main(self):
        dirty = True
        while True:
            if dirty:
                self.draw()
            try:
                key = self.scr.get_wch()
            except self.c.error:  # timeout: look at tasks/
                dirty = self.watcher.changed()
                if dirty:
                    self.reload()
                continue
            if key == "\x1b":
                key = self._escape()
            if key in ("q", "Q"):
                return 0
            self.message = ""
            self.handle(key)
            dirty = True

    def handle(self, key):
        c = self.c
        moves = {c.KEY_UP: "up", c.KEY_DOWN: "down", c.KEY_LEFT: "left", c.KEY_RIGHT: "right"}
        if key in moves:
            self.cursor.move(moves[key])
        elif key == c.KEY_RESIZE:
            if hasattr(c, "update_lines_cols"):
                c.update_lines_cols()
        elif key in ("\n", "\r", c.KEY_ENTER):
            self.edit()
        elif key == " ":
            self.selection.toggle(self.cursor.selected_task)
        elif key == "\x1b":
            self.selection.clear()
        elif key == "m":
            self.move()
        elif key == "l":
            self.loop()

    def _escape(self):
        """Esc alone, or an arrow a terminal sent raw (ESC [ A, ESC O A) that curses did not decode."""
        self.scr.nodelay(True)
        try:
            follow_up = []
            for _ in range(2):
                try:
                    follow_up.append(self.scr.get_wch())
                except self.c.error:
                    break
        finally:
            self.scr.nodelay(False)
            self.scr.timeout(POLL_MS)
        arrow = raw_arrow(follow_up)
        if arrow is not None:
            return getattr(self.c, "KEY_" + arrow)
        for key in reversed(follow_up):
            self.c.unget_wch(key)
        return "\x1b"

    # --- actions

    def edit(self):
        task = self.cursor.selected_task
        if task is None:
            return
        argv = runnable(edit_command(task).argv, self.root)
        self.c.def_prog_mode()
        self.c.endwin()
        try:
            code = subprocess.run(argv, cwd=str(self.root)).returncode
            self.message = f"edited Task {task.id}" if code == 0 else f"{argv[0]} exited with {code}"
        except OSError as exc:
            self.message = f"cannot run {argv[0]}: {exc.strerror or exc}"
        finally:
            self.c.reset_prog_mode()
            self.scr.clear()  # the editor drew over everything: repaint it all
        self.reload()

    def move(self):
        targets = self.selection.targets(self.cursor)
        if not targets:
            return
        choices = stage_choices()
        here = targets[0].stage.name
        stage = self.pick(f" Move {', '.join(t.id for t in targets)} to ", choices,
                          choices.index(here) if here in choices else 0)
        if stage is None:
            self.message = "move cancelled"
            return
        note = self.prompt("Note for the Status line (⏎ none, esc cancel): ")
        if note is None:
            self.message = "move cancelled"
            return
        results = []
        for command in move_commands(targets, stage, note or None):
            code, out = execute(command, self.root)
            results.append(out if code == 0 else f"failed: {out}")
        self.message = " · ".join(results)
        self.selection.clear()
        self.reload()

    def loop(self):
        targets = self.selection.targets(self.cursor)
        command = loop_command(self.board, targets)
        if command is None:
            return
        code, out = execute(command, self.root)
        if code == 0:
            self.message = command.note
            self.selection.clear()
        else:
            self.message = f"{command.argv[0]} failed ({out}); the command: {loop_text(self.board, targets)}"

    # --- input

    def pick(self, title, options, index):
        """A centred list; ⏎ or a digit picks, esc or q cancels."""
        c = self.c
        rows, cols = self.scr.getmaxyx()
        width = min(max(len(title), *(len(o) for o in options)) + 8, cols)
        height = min(len(options) + 2, rows)
        win = c.newwin(height, width, max((rows - height) // 2, 0), max((cols - width) // 2, 0))
        win.keypad(True)
        try:
            while True:
                win.erase()
                win.box()
                self._put(win, 0, 2, title, c.A_BOLD)
                for i, option in enumerate(options[: height - 2]):
                    self._put(win, i + 1, 2, f"{i + 1} {option}".ljust(width - 4),
                              c.A_REVERSE if i == index else c.A_NORMAL)
                win.refresh()
                key = win.get_wch()
                if key in (c.KEY_UP, "k"):
                    index = max(index - 1, 0)
                elif key in (c.KEY_DOWN, "j"):
                    index = min(index + 1, len(options) - 1)
                elif key in ("\n", "\r", c.KEY_ENTER):
                    return options[index]
                elif isinstance(key, str) and key.isdigit() and 1 <= int(key) <= len(options):
                    return options[int(key) - 1]
                elif key in ("\x1b", "q"):
                    return None
        finally:
            del win
            self.scr.touchwin()

    def prompt(self, label):
        """A line of text typed on the status line; None on esc."""
        c = self.c
        text = ""
        self.scr.timeout(-1)
        try:
            c.curs_set(1)
        except c.error:
            pass
        try:
            while True:
                rows, cols = self.scr.getmaxyx()
                shown = (label + text)[-(cols - 1):]
                self.scr.move(rows - 1, 0)
                self.scr.clrtoeol()
                self._put(self.scr, rows - 1, 0, shown, c.A_BOLD)
                self.scr.move(rows - 1, min(len(shown), cols - 1))
                self.scr.refresh()
                key = self.scr.get_wch()
                if key in ("\n", "\r", c.KEY_ENTER):
                    return text.strip()
                if key == "\x1b":
                    return None
                if key in (c.KEY_BACKSPACE, "\x7f", "\b"):
                    text = text[:-1]
                elif isinstance(key, str) and key.isprintable():
                    text += key
        finally:
            try:
                c.curs_set(0)
            except c.error:
                pass
            self.scr.timeout(POLL_MS)

    # --- drawing

    def _attrs(self):
        c = self.c
        attrs = {None: c.A_NORMAL, "dim": c.A_DIM, "blocked": c.A_DIM, "id": c.A_BOLD, "head": c.A_BOLD}
        colours = {"loop": c.COLOR_GREEN, "you": c.COLOR_YELLOW, "grill": c.COLOR_MAGENTA,
                   "unlock": c.COLOR_CYAN, "warn": c.COLOR_RED}
        if c.has_colors():
            c.start_color()
            try:
                c.use_default_colors()
                background = -1
            except c.error:
                background = c.COLOR_BLACK
            for pair, (style, colour) in enumerate(colours.items(), 1):
                c.init_pair(pair, colour, background)
                attrs[style] = c.color_pair(pair)
        else:
            attrs.update({style: c.A_BOLD for style in colours})
        return attrs

    def attr(self, style, mode="normal"):
        c = self.c
        if mode == "dim":
            return c.A_DIM
        base = self.attrs.get(style, c.A_NORMAL)
        if mode == "cursor":
            return base | c.A_REVERSE
        if mode == "bright":
            return base | c.A_BOLD
        return base

    def _put(self, win, y, x, text, attr=0):
        rows, cols = win.getmaxyx()
        if y < 0 or y >= rows or x >= cols:
            return
        try:
            win.addstr(y, x, text[: cols - x], attr)
        except self.c.error:  # writing the bottom-right cell moves the cursor off the window
            pass

    def draw(self):
        scr = self.scr
        scr.erase()
        rows, cols = scr.getmaxyx()
        if rows < MIN_SIZE[0] or cols < MIN_SIZE[1]:
            self._put(scr, 0, 0, "terminal too small: enlarge it, or q to quit")
            scr.refresh()
            return
        title, summary, warning = header(self.board, self.view, self.errors)
        self._put(scr, 0, 0, title, self.attr("head"))
        self._put(scr, 0, len(title), summary, self.attr("dim"))
        self._put(scr, 0, len(title) + len(summary), warning, self.attr("warn"))
        detail_height = DETAIL_HEIGHT if rows >= MIN_SIZE[0] + DETAIL_HEIGHT else 0
        self.draw_columns(2, rows - 3 - detail_height, cols)
        if detail_height:
            self.draw_detail(rows - 1 - detail_height, detail_height, cols)
        self.draw_status(rows - 1, cols)
        scr.refresh()

    def draw_columns(self, top, height, width):
        columns = self.cursor.columns
        if not columns:
            self._put(self.scr, top, 0, "Nothing active.")
            return
        shown, cell = fit_columns(len(columns), width)
        self.first = follow(self.first, self.cursor.wave, shown, len(columns))
        visible = max((height - 2) // 2, 1)
        longest = max(len(col) for col in columns[self.first:self.first + shown])
        self.top = follow(self.top, self.cursor.row, visible, longest)
        current = self.cursor.selected_task
        bright = highlight(self.view, current)
        dim = self.attr("dim")
        for k in range(shown):
            index = self.first + k
            col = columns[index]
            x = k * (GUTTER + cell + len(SEP))
            label = f"{column_label(self.view, index)} ({len(col)})"
            if self.top > 0 or len(col) > self.top + visible:
                end = min(len(col), self.top + visible)
                label += f" {min(self.top + 1, len(col))}–{end}" if self.top < len(col) else ""
            if k == 0 and self.first > 0:
                label = "‹ " + label
            if k == shown - 1 and index < len(columns) - 1:
                label = label + " ›"
            self._put(self.scr, top, x + GUTTER, tasks._clip(label, cell), self.attr("head"))
            self._put(self.scr, top + 1, x + GUTTER, "─" * cell, dim)
            if k:
                for y in range(top, top + 2 + 2 * visible):
                    self._put(self.scr, y, x - len(SEP), SEP, dim)
            for r in range(self.top, min(len(col), self.top + visible)):
                task = col[r]
                y = top + 2 + 2 * (r - self.top)
                mode = cell_mode(task, current, bright)
                if task.id in self.selection:
                    self._put(self.scr, y, x, "*", self.c.A_BOLD)
                for i, line in enumerate(cell_lines(self.view, task, cell)):
                    xx = x + GUTTER
                    for text, style in line.pieces:
                        self._put(self.scr, y + i, xx, text, self.attr(style, mode))
                        xx += len(text)

    def draw_detail(self, top, height, width):
        win = self.scr
        self._put(win, top, 0, "┌" + "─" * (width - 2) + "┐", self.attr("dim"))
        lines = detail(self.view, self.cursor.selected_task)
        for i in range(height - 2):
            text = lines[i] if i < len(lines) else ""
            y = top + 1 + i
            self._put(win, y, 0, "│", self.attr("dim"))
            self._put(win, y, 2, tasks._clip(text, width - 4), self.attr("head") if i == 0 else 0)
            self._put(win, y, width - 1, "│", self.attr("dim"))
        self._put(win, top + height - 1, 0, "└" + "─" * (width - 2) + "┘", self.attr("dim"))

    def draw_status(self, y, width):
        picked = len(self.selection.ids)
        extra = f"  · {picked} selected" if picked else ""
        if self.message:
            self._put(self.scr, y, 0, tasks._clip(self.message + extra, width - 1), self.c.A_BOLD)
        else:
            self._put(self.scr, y, 0, tasks._clip(HELP + extra, width - 1), self.attr("dim"))
