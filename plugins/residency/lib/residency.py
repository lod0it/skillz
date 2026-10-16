#!/usr/bin/env python3
"""residency - see and trim what Claude Code keeps resident in context (zero tokens).

Opens a curses screen for the project of the current directory; `--plain` prints the same
content once (also used when stdout is not a terminal).
"""
import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import measure
import model as M
import settings as S
import snapshot
import usage


def version():
    return (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()


@dataclass
class Context:
    """Everything read from disk once at start-up."""
    project_dir: Path
    sett: object
    found: object = None
    here: object = None
    all_: object = None
    learned: dict = field(default_factory=dict)
    predictions: list = field(default_factory=list)
    snaps: list = field(default_factory=list)
    measurer: object = None  # measure.Measurer, None when claude cannot run
    measure_error: str = ""
    version: str = ""


def find_project(cwd, projects_root=None):
    """The project of `cwd`: the nearest directory (cwd or a parent) with transcripts,
    else cwd itself."""
    cwd = Path(cwd).resolve()
    for d in (cwd,) + tuple(cwd.parents):
        if snapshot.transcripts_dir(d, projects_root).is_dir():
            return d
    return cwd


def load(project_dir, projects_root=None, runner=subprocess.run, measures=True):
    """Read snapshot, settings, usage, predictions and learned deltas of a project."""
    project_dir = Path(project_dir)
    ctx = Context(project_dir, S.Settings(project_dir))
    ctx.found = snapshot.latest_snapshot(project_dir, projects_root)
    ctx.here = usage.usage("here", project_dir, projects_root=projects_root)
    ctx.all_ = usage.usage("all", projects_root=projects_root)
    ctx.predictions = M.load_predictions(project_dir=project_dir)
    ctx.snaps = M.interactive_snapshots(project_dir, projects_root)
    new = M.learn(ctx.predictions, ctx.snaps, project_dir)
    known = M.load_learned()
    if any(known.get(k) != v for k, v in new.items()):
        M.save_learned(new)
    ctx.learned = M.load_learned()
    if measures:
        try:
            ctx.version = measure.claude_version(runner)
            ctx.measurer = measure.Measurer(project_dir, effective=ctx.sett.data, runner=runner)
            ctx.measurer._version = ctx.version
        except measure.MeasureError as e:
            ctx.measure_error = str(e)
    return ctx


def render_plain(ctx, width=80, now=None):
    import tui
    state = tui.State(ctx)
    return tui.plain(state.model, ctx.project_dir.name, width, now)


def main(argv=None, runner=subprocess.run, out=None, cwd=None, projects_root=None):
    ap = argparse.ArgumentParser(prog="residency", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version=version())
    ap.add_argument("--plain", action="store_true",
                    help="print the screen once, no curses (for pipes and `! residency --plain`)")
    ap.add_argument("--project", metavar="DIR",
                    help="project directory (default: the project of the current directory)")
    args = ap.parse_args(argv)
    out = out or sys.stdout
    project = Path(args.project).resolve() if args.project else find_project(
        cwd or Path.cwd(), projects_root)
    try:
        ctx = load(project, projects_root, runner)
    except S.SettingsError as e:
        print("residency: %s" % e, file=sys.stderr)
        return 1
    if args.plain or not (out.isatty() and sys.stdin.isatty()):
        try:
            out.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        out.write(render_plain(ctx))
        return 0
    import tui
    return tui.run(ctx)


if __name__ == "__main__":
    sys.exit(main())
