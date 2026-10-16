"""The residency screen: renderers (shared by curses and `--plain`), the UI state, the curses loop.

Layout and keys follow decision Q4 of `docs/residency-design.md`. Every number comes from
`model.py`; this module only draws it and turns keys into pending toggles, measures and the
`w` write. A rendered line is a list of `(text, style)` spans; `style` is a name the curses
loop maps to colours (or ignores when the terminal has none) and `--plain` drops.
"""
import datetime
import queue

import measure
import model as M
import settings as S

GLYPH = {"core": "█", "skills": "▓", "mcp": "▒", "memory": "░"}
LEGEND = (("core", "core"), ("skills", "skills"), ("mcp", "mcp"), ("memory", "memory/CLAUDE.md"))
FOOTER = "↑↓ move  ⏎ expand  space state  s scope  o sort  w write  M measure all  q quit"
DEFAULT_OPEN = (M.TOOLS, M.SKILLS)
LABEL_W = 28  # category label column: values start at column 30, as on item rows
ROW_LABEL_W = 22
SORT_NAME = {"cost": "cost", "waste": "cost × unused"}
BASE_JOB = "base"


# ---------------------------------------------------------------- pure renderers


def ago(ts, now=None):
    """`2h ago` for an ISO timestamp; '' when unreadable."""
    t = M.parse_ts(ts)
    if t is None:
        return ""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    s = max(0, int((now - t).total_seconds()))
    if s < 60:
        return "just now"
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return "%d%s ago" % (s // n, unit)
    return ""


def bar_cells(segments, scale, width):
    """[(group, cells)] of a stacked bar: `segments` {group: tokens} on `scale` tokens =
    `width` cells, rounded on the running sum so the cells add up."""
    out, cum, prev = [], 0, 0
    for g, _names in M.GROUPS:
        cum += max(0, segments.get(g, 0))
        end = min(width, int(round(width * cum / scale))) if scale > 0 else 0
        out.append((g, max(0, end - prev)))
        prev = max(prev, end)
    return out


def _bar_spans(segments, scale, width):
    spans = [(GLYPH[g] * n, g) for g, n in bar_cells(segments, scale, width) if n]
    used = sum(len(t) for t, _ in spans)
    return spans + [(" " * (width - used), None)]


def bar_width(width):
    return max(10, min(40, width - 37))


def _pct(x):
    return "%d%%" % round(x)


def header(model, project_name, width=80, now=None):
    """Title, NOW/AFTER bars, legend, stale banner and prediction line, as span lists."""
    f = model.found
    if f is None:
        right = "no /context yet: run claude, /context, /exit"
    elif f.source == "usage":
        right = "first turn %s (session %s, %s)" % (M.fmt(model.now), f.session[:8],
                                                    ago(f.timestamp, now))
    else:
        right = "measured %s (session %s, %s)" % (M.fmt(model.now), f.session[:8],
                                                  ago(f.timestamp, now))
    left = "residency · " + project_name
    gap = max(2, width - len(left) - len(right))
    lines = [[(left, "bold"), (" " * gap + right, None)], []]

    if model.now is None:
        lines.append([("no snapshot of this project: run claude, /context, /exit here", "warn")])
    elif f.source == "usage" or not f.snapshot.categories:
        lines.append([("NOW    %s  (first turn total, no split: run /context)" % M.fmt(model.now),
                       None)])
    else:
        bw = bar_width(width)
        now_s, after_s = model.segments(), model.segments(after=True)
        scale = max(sum(now_s.values()), sum(after_s.values()), 1)
        win = ("  %.1f%% of %s" % (model.window_pct, M.fmt(model.window))
               if model.window_pct is not None else "")
        lines.append([("NOW    ", "bold")] + _bar_spans(now_s, scale, bw)
                     + [("  %s%s" % (M.fmt(model.now), win), None)])
        if model.toggled():
            mark = "" if model.after_origin == M.MEASURED else model.after_origin
            d = -model.saved
            tail = "  %s%s  %s%s (%s%s)" % (mark, M.fmt(model.after), "+" if d > 0 else "",
                                           M.fmt(d), "+" if d > 0 else "-" if d < 0 else "",
                                           _pct(abs(model.saved_pct or 0)))
            lines.append([("AFTER  ", "bold")] + _bar_spans(after_s, scale, bw)
                         + [(tail, "bold")])
        else:
            lines.append([("AFTER  ", "bold"), ("same as now (space toggles an item)", "dim")])
        leg = [("       ", None)]
        for g, name in LEGEND:
            leg += [(GLYPH[g], g), (" %s  " % name, None)]
        lines.append(leg)
    stale = model.stale_line()
    if stale:
        lines.append([(stale, "warn")])
    if model.comparison is not None:
        lines.append([(model.comparison.line(), "dim")])
    lines.append([])
    return lines


def _value(origin, n, k=False, upper=False):
    if n is None or origin == M.UNKNOWN:
        return "?"
    return "%s%s%s" % (origin or "", "<" if upper else "", M.fmt(n, k))


def cat_line(cat, expanded):
    arrow = ("▾ " if expanded else "▸ ") if cat.rows else "  "
    text = arrow + short(cat.label, LABEL_W - 1).ljust(LABEL_W) + _value(cat.origin, cat.resident, k=True)
    if cat.after is not None and cat.resident is not None and cat.after != cat.resident:
        text += " → " + M.fmt(cat.after, True)
    if cat.key == M.MCP and cat.on_load is not None:
        text += "  on-load " + _value(cat.origin, cat.on_load, k=True)
    if cat.note:
        text += "  " + cat.note
    return [(text, "bold")]


def row_mark(row):
    if row.toggled and row.target:
        return S.BADGE[row.target]
    if row.tunable:
        return row.badge
    return "·"


def short(label, width):
    """Fit a label in `width` cells: paths keep their tail, names their head."""
    if len(label) <= width:
        return label
    if label.startswith("/"):
        return "…" + label[-(width - 1):]
    return label[:width - 1] + "…"


def row_line(row, measuring=False):
    label = short(row.label, ROW_LABEL_W)
    val = _value(row.origin, row.resident, k=row.lump, upper=row.upper_bound)
    spans = [("    %s  %s %s" % (row_mark(row), label.ljust(ROW_LABEL_W), val.ljust(6)), None)]
    state = row.state or ""
    if row.toggled:
        spans.append((" %s → %s" % (state, row.after), "bold"))
        if measuring:
            spans.append(("  measuring…", "dim"))
        elif row.delta is None:
            spans.append(("  Δ?", "warn"))
        else:
            spans.append(("  Δ%s%s" % (row.delta_origin or "", M.fmt(-row.delta)), "bold"))
    elif state:
        spans.append((" " + state, None))
    use = []
    if row.here is not None:
        use.append("here %d×" % row.here)
    if row.all is not None:
        use.append("all %d×" % row.all)
    if use:
        spans.append(("  " + " · ".join(use), "dim"))
    notes = []
    if row.on_load is not None:
        notes.append("on-load " + M.fmt(row.on_load))
    if row.note:
        notes.append(row.note)
    if row.lump and not row.note:
        notes.append("tools only interactive sessions load")
    if notes:
        spans.append(("  " + " · ".join(notes), "dim"))
    return spans


def tree(model, expanded, measuring=()):
    """[(key, spans, category, row)] in screen order; row None on category lines."""
    out = []
    for c in model.categories:
        out.append(("cat:" + c.key, cat_line(c, c.key in expanded), c, None))
        if c.key in expanded:
            for r in c.rows:
                busy = r.setting is not None and r.toggled and \
                    M.measure_key(r.setting, r.after) in measuring
                out.append((r.key, row_line(r, busy), c, r))
    return out


def text(spans):
    return "".join(t for t, _ in spans)


def plain(model, project_name, width=80, now=None):
    """The screen as text, every category expanded, no keys line."""
    lines = header(model, project_name, width, now)
    lines += [e[1] for e in tree(model, {c.key for c in model.categories})]
    return "\n".join(text(s).rstrip() for s in lines) + "\n"


def diff_lines(pending):
    """The `w` view: one block per settings file that would change."""
    out = []
    for scope, d in pending.diff().items():
        out.append([("%s scope: %s" % (scope, pending.settings.paths[scope]), "bold")])
        for ln in d.splitlines():
            style = None
            if ln.startswith("+") and not ln.startswith("+++"):
                style = "add"
            elif ln.startswith("-") and not ln.startswith("---"):
                style = "del"
            elif ln.startswith("@@"):
                style = "dim"
            out.append([(ln, style)])
        out.append([])
    return out


# ---------------------------------------------------------------- state (no curses)


class State:
    """What the screen shows and what the keys change.

    `ctx` comes from `residency.load()`. `submit(name, change)` queues a headless measure
    (`change=None`: the base); results come back through `on_result`.
    """

    def __init__(self, ctx, submit=None):
        self.ctx = ctx
        self.pending = ctx.sett.pending()
        self.submit_fn = submit
        self.measures = {}
        self.measuring = set()
        self.failed = set()
        self.expanded = set(DEFAULT_OPEN)
        self.sort = "cost"
        self.cursor = 0
        self.status = ctx.measure_error and "measures off: %s" % ctx.measure_error or ""
        self.gen = 0  # bumped on write: results of older settings are dropped
        self.headless = None
        self.model = None
        self.preload()
        self.rebuild()

    # data ----------------------------------------------------------
    @property
    def measurer(self):
        return self.ctx.measurer

    def preload(self):
        """Cached headless base and per-tool/server deny measures (never runs a measure)."""
        if not self.measurer:
            return
        try:
            self.headless = self.measurer.cached_base()
            sett = self.ctx.sett
            probe = M.build(self.ctx.found, sett, project_dir=self.ctx.project_dir)
            for r in probe.rows():
                if r.setting is not None and r.setting.kind in (S.TOOL, S.MCP) and \
                        r.state != "deny":
                    change = M.change_for(sett, r.setting, "deny")
                    hit = self.measurer.cached(change) if change else None
                    if hit:
                        self.measures[M.measure_key(r.setting, "deny")] = hit
        except measure.MeasureError as e:
            self.ctx.measurer, self.ctx.measure_error = None, str(e)
            self.status = "measures off: %s" % e

    def rebuild(self):
        c = self.ctx
        self.model = M.build(c.found, c.sett, self.pending, self.measures, c.learned, c.here,
                             c.all_, self.headless, c.project_dir, predictions=c.predictions,
                             snapshots=c.snaps, sort=self.sort)
        return self.model

    def entries(self):
        return tree(self.model, self.expanded, self.measuring)

    def selected(self):
        es = self.entries()
        if not es:
            return None
        self.cursor = max(0, min(self.cursor, len(es) - 1))
        return es[self.cursor]

    def _keep(self, key):
        for i, e in enumerate(self.entries()):
            if e[0] == key:
                self.cursor = i
                return

    # measures ------------------------------------------------------
    def start(self):
        """Ask for the headless base when it is not cached (the interactive-only lump)."""
        if self.headless is None and self.measurer and self.submit_fn:
            self.measuring.add(BASE_JOB)
            self.submit_fn((self.gen, BASE_JOB), None)

    def _want(self, item, value):
        """Queue a measure of `item` -> `value` unless known, running or failed."""
        key = M.measure_key(item, value)
        if not self.measurer and self.ctx.measure_error:
            self.status = "measures off (%s): estimate used" % self.ctx.measure_error
        if not self.measurer or not self.submit_fn or key in self.measures or \
                key in self.measuring or key in self.failed or key in self.ctx.learned:
            return False
        change = M.change_for(self.ctx.sett, item, value)
        if change is None:
            self.status = "%s: removing a deny cannot be measured headless, estimate used" % (
                item.name)
            return False
        self.measuring.add(key)
        self.submit_fn((self.gen, key), change)
        return True

    def on_result(self, name, res):
        gen, key = name
        if gen != self.gen:
            return
        self.measuring.discard(key)
        if key == BASE_JOB:
            if isinstance(res, Exception):
                self.status = "base measure failed: %s" % res
            else:
                self.headless = res
        elif isinstance(res, Exception):
            self.failed.add(key)
            self.status = "measure failed: %s" % res
        else:
            self.measures[key] = res
            if not res.ok:
                self.failed.add(key)
        self.rebuild()

    def measure_all(self):
        n = 0
        for r in self.model.rows():
            if not r.tunable:
                continue
            if r.toggled:
                n += self._want(r.setting, r.after)
            target = S.CYCLES[r.setting.kind][-1]
            if r.state != target:
                n += self._want(r.setting, target)
        self.status = "measuring %d item(s) in the background" % n if n else \
            "every item is measured" if self.measurer else "measures off"
        return n

    # keys ----------------------------------------------------------
    def move(self, d):
        n = len(self.entries())
        self.cursor = max(0, min(n - 1, self.cursor + d))

    def enter(self):
        e = self.selected()
        if not e:
            return
        cat = e[2]
        if cat.key in self.expanded:
            self.expanded.discard(cat.key)
        elif cat.rows:
            self.expanded.add(cat.key)
        self._keep("cat:" + cat.key)

    def toggle(self):
        e = self.selected()
        if not e:
            return
        row = e[3]
        if row is None:
            return self.enter()
        if row.setting is not None and row.setting.kind == S.PLUGIN_SKILL:
            self.status = "%s: %s; toggle its plugin" % (row.label, S.NOT_SUPPORTED)
            return
        if not row.tunable:
            self.status = "%s: not tunable" % row.label
            return
        value = self.pending.toggle(row.setting)
        self.status = ""
        if value != self.ctx.sett.effective(row.setting).value:
            self._want(row.setting, value)
        self.rebuild()
        self._keep(row.key)

    def cycle_scope(self):
        e = self.selected()
        row = e[3] if e else None
        if row is None or not row.tunable:
            self.status = "no scope here: select a tunable item"
            return
        cur = self.pending.scope(row.setting)
        nxt = S.SCOPES[(S.SCOPES.index(cur) + 1) % len(S.SCOPES)]
        self.pending.set_scope(row.setting, nxt)
        self.status = "%s writes to %s (%s)" % (row.label, nxt, self.ctx.sett.paths[nxt])
        self.rebuild()
        self._keep(row.key)

    def cycle_sort(self):
        self.sort = "waste" if self.sort == "cost" else "cost"
        key = (self.selected() or (None,))[0]
        self.rebuild()
        self._keep(key)
        self.status = "sorted by " + SORT_NAME[self.sort]

    # write ---------------------------------------------------------
    def write(self, now=None):
        """Record the prediction, back up and write; return [(path, backup)]."""
        c = self.ctx
        M.record_prediction(self.model, self.pending, c.project_dir, c.version or "", now=now)
        done = self.pending.write(now=now.replace(tzinfo=None) if now else None)
        self.gen += 1
        self.measures.clear()
        self.measuring.clear()
        self.failed.clear()
        self.headless = None
        if c.measurer is not None:
            c.measurer = measure.Measurer(c.project_dir, effective=c.sett.data,
                                          runner=c.measurer.runner,
                                          cache_path=c.measurer.cache_path)
            c.measurer._version = c.version or None
        c.predictions = M.load_predictions(project_dir=c.project_dir)
        self.preload()
        self.rebuild()
        self.start()
        self.status = "wrote " + ", ".join(
            "%s (backup %s)" % (p, b.name if b else "none: new file") for p, b in done)
        return done


# ---------------------------------------------------------------- curses


def run(ctx):  # pragma: no cover - drawing is covered by the Manual check
    import curses
    import locale
    import os
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    results = queue.Queue()
    bg = None
    if ctx.measurer is not None:
        bg = measure.Background(_Proxy(ctx), lambda n, r: results.put((n, r)))
    state = State(ctx, bg.submit if bg else None)
    state.start()
    try:
        curses.wrapper(_main, state, results)
    finally:
        if bg:
            bg.cancel()
    return 0


class _Proxy:  # pragma: no cover
    """Lets the background thread follow `ctx.measurer` when `w` replaces it."""

    def __init__(self, ctx):
        self.ctx = ctx

    def delta(self, change):
        return self.ctx.measurer.delta(change)

    def base(self):
        return self.ctx.measurer.base()


def _styles(curses):  # pragma: no cover
    st = {None: 0, "bold": curses.A_BOLD, "dim": curses.A_DIM, "warn": curses.A_BOLD,
          "add": 0, "del": 0, "core": 0, "skills": 0, "mcp": 0, "memory": 0}
    if not curses.has_colors():
        return st
    try:
        curses.start_color()
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    pairs = (("core", curses.COLOR_CYAN), ("skills", curses.COLOR_MAGENTA),
             ("mcp", curses.COLOR_YELLOW), ("memory", curses.COLOR_GREEN),
             ("warn", curses.COLOR_RED), ("add", curses.COLOR_GREEN), ("del", curses.COLOR_RED))
    for i, (name, fg) in enumerate(pairs, 1):
        try:
            curses.init_pair(i, fg, bg)
            st[name] = curses.color_pair(i) | (curses.A_BOLD if name == "warn" else 0)
        except curses.error:
            pass
    return st


def _put(win, y, x, spans, styles, width, extra=0):  # pragma: no cover
    import curses
    for t, style in spans:
        if x >= width:
            break
        t = t[:width - x]
        try:
            win.addstr(y, x, t, styles.get(style, 0) | extra)
        except curses.error:  # writing the bottom-right cell raises after drawing
            pass
        x += len(t)
    if extra and x < width:
        try:
            win.addstr(y, x, " " * (width - x), extra)
        except curses.error:
            pass


def _ask(stdscr, styles, question):  # pragma: no cover
    """Prompt on the last line; True on y."""
    import curses
    h, w = stdscr.getmaxyx()
    stdscr.move(h - 1, 0)
    stdscr.clrtoeol()
    _put(stdscr, h - 1, 0, [(question + "  y/n", "warn")], styles, w - 1)
    stdscr.refresh()
    stdscr.timeout(-1)
    try:
        while True:
            ch = stdscr.getch()
            if ch in (ord("y"), ord("Y")):
                return True
            if ch in (ord("n"), ord("N"), 27, ord("q")):
                return False
            if ch == curses.KEY_RESIZE:
                return False
    finally:
        stdscr.timeout(150)


def _draw(stdscr, state, styles):  # pragma: no cover
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    if h < 8 or w < 30:
        _put(stdscr, 0, 0, [("terminal too small", "warn")], styles, w - 1)
        stdscr.refresh()
        return
    head = header(state.model, state.ctx.project_dir.name, w)
    for y, spans in enumerate(head[:h - 4]):
        _put(stdscr, y, 0, spans, styles, w - 1)
    top = min(len(head), h - 4)
    area = h - 2 - top
    es = state.entries()
    state.selected()
    first = getattr(state, "scroll", 0)
    if state.cursor < first:
        first = state.cursor
    elif state.cursor >= first + area:
        first = state.cursor - area + 1
    first = max(0, min(first, max(0, len(es) - area)))
    state.scroll = first
    import curses
    for i, e in enumerate(es[first:first + area]):
        rev = curses.A_REVERSE if first + i == state.cursor else 0
        _put(stdscr, top + i, 0, e[1], styles, w - 1, rev)
    if first > 0:
        _put(stdscr, top, w - 2, [("↑", "dim")], styles, w)
    if first + area < len(es):
        _put(stdscr, h - 3, w - 2, [("↓", "dim")], styles, w)
    status = state.status
    n = len(state.measuring)
    if n:
        status = ("measuring… %d left" % n) + ("  " + status if status else "")
    _put(stdscr, h - 2, 0, [(status, "warn" if "fail" in status else "dim")], styles, w - 1)
    _put(stdscr, h - 1, 0, [(FOOTER, "dim")], styles, w - 1)
    stdscr.refresh()


def _diff_view(stdscr, state, styles):  # pragma: no cover
    """Show the diff of the settings files; True when the user confirms the write."""
    import curses
    lines = diff_lines(state.pending)
    first = 0
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        area = max(1, h - 2)
        first = max(0, min(first, max(0, len(lines) - area)))
        for i, spans in enumerate(lines[first:first + area]):
            _put(stdscr, i, 0, spans, styles, w - 1)
        n = len(state.pending.changed_scopes())
        _put(stdscr, h - 1, 0, [("write %d file(s), each backed up to <file>.bak-<time>?  "
                                 "y write  n cancel  ↑↓ scroll" % n, "warn")], styles, w - 1)
        stdscr.refresh()
        stdscr.timeout(-1)
        ch = stdscr.getch()
        stdscr.timeout(150)
        if ch in (ord("y"), ord("Y")):
            return True
        if ch in (ord("n"), ord("N"), ord("q"), 27):
            return False
        if ch in (curses.KEY_UP, ord("k")):
            first -= 1
        elif ch in (curses.KEY_DOWN, ord("j")):
            first += 1
        elif ch == curses.KEY_PPAGE:
            first -= area
        elif ch == curses.KEY_NPAGE:
            first += area


def _main(stdscr, state, results):  # pragma: no cover
    import curses
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)
    stdscr.timeout(150)
    styles = _styles(curses)
    while True:
        changed = False
        while True:
            try:
                name, res = results.get_nowait()
            except queue.Empty:
                break
            state.on_result(name, res)
            changed = True
        if changed:
            state.selected()
        _draw(stdscr, state, styles)
        ch = stdscr.getch()
        if ch == -1:
            continue
        h = stdscr.getmaxyx()[0]
        if ch == curses.KEY_RESIZE:
            try:
                curses.update_lines_cols()
            except AttributeError:
                pass
            stdscr.clear()
        elif ch in (curses.KEY_UP, ord("k")):
            state.move(-1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            state.move(1)
        elif ch == curses.KEY_PPAGE:
            state.move(-(h - 10))
        elif ch == curses.KEY_NPAGE:
            state.move(h - 10)
        elif ch in (curses.KEY_HOME, ord("g")):
            state.cursor = 0
        elif ch in (curses.KEY_END, ord("G")):
            state.cursor = len(state.entries()) - 1
        elif ch in (curses.KEY_ENTER, 10, 13):
            state.enter()
        elif ch == ord(" "):
            try:
                state.toggle()
            except (S.SettingsError, OSError) as e:
                state.status = str(e)
        elif ch == ord("s"):
            state.cycle_scope()
        elif ch == ord("o"):
            state.cycle_sort()
        elif ch == ord("M"):
            state.measure_all()
        elif ch == ord("w"):
            if not state.pending:
                state.status = "nothing to write: toggle an item with space"
            elif _diff_view(stdscr, state, styles):
                try:
                    state.write()
                except (OSError, S.SettingsError) as e:
                    state.status = "write failed: %s" % e
            else:
                state.status = "write cancelled"
            stdscr.clear()
        elif ch in (ord("q"), 27):
            n = len(state.pending.changes)
            if not n or _ask(stdscr, styles, "discard %d pending change(s) and quit?" % n):
                return
