import datetime
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import measure
import model as M
import residency
import settings as S
import snapshot
import tui

PLUGIN = Path(__file__).resolve().parent.parent
BIN = PLUGIN / "bin" / "residency"
FIX = Path(__file__).resolve().parent / "fixtures"
UTC = datetime.timezone.utc
SNAP_TS = "2026-10-16T10:00:00.000Z"
NOW = datetime.datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


class ScaffoldTest(unittest.TestCase):
    def test_version_matches_manifest(self):
        v = (PLUGIN / "VERSION").read_text().strip()
        m = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(v, m["version"])

    def test_version_output(self):
        r = subprocess.run([str(BIN), "--version"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), (PLUGIN / "VERSION").read_text().strip())

    def test_runs_through_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "residency")
            os.symlink(BIN, link)
            r = subprocess.run([link, "--version"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)

    def test_no_skills(self):
        self.assertFalse((PLUGIN / "skills").exists())


def no_claude(cmd, **kw):
    raise FileNotFoundError("claude")


class FakeClaude:
    """`claude --version` only: measures are queued, never run, in these tests."""

    def __call__(self, cmd, **kw):
        if cmd[1:] == ["--version"]:
            return subprocess.CompletedProcess(cmd, 0, "2.1.301\n", "")
        raise AssertionError("no headless run expected: %r" % cmd)


class Env(unittest.TestCase):
    """A temp HOME with the fixture snapshot in the project's transcripts."""

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name).resolve()  # macOS: /var is a link to /private/var
        self.home = self.tmp / "home"
        self.proj = self.tmp / "skillz"
        (self.home / ".claude").mkdir(parents=True)
        (self.proj / ".claude").mkdir(parents=True)
        p = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        p.start()
        self.addCleanup(p.stop)
        self.root = self.home / ".claude" / "projects"
        d = snapshot.transcripts_dir(self.proj, self.root)
        d.mkdir(parents=True)
        recs = [{"type": "user", "isMeta": True, "timestamp": SNAP_TS,
                 "message": {"content": (FIX / "context_interactive.md").read_text()}},
                {"type": "assistant", "timestamp": SNAP_TS, "message": {"content": [
                    {"type": "tool_use", "id": "t1", "name": "Skill",
                     "input": {"skill": "code-review"}}]}}]
        (d / "89d7d1d1-aaaa.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        old = datetime.datetime(2026, 1, 1, tzinfo=UTC).timestamp()
        self.user_settings = self.home / ".claude" / "settings.json"
        self.user_settings.write_text(json.dumps({"skillOverrides": {"pdf": "off"}}) + "\n")
        os.utime(self.user_settings, (old, old))

    def ctx(self, runner=no_claude):
        return residency.load(self.proj, self.root, runner)


class Plain(Env):
    def test_render(self):
        out = residency.render_plain(self.ctx(), now=NOW)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("residency · skillz"))
        self.assertTrue(lines[0].endswith("measured 28.0k (session 89d7d1d1, 2h ago)"))
        self.assertTrue(lines[2].startswith("NOW    █"))
        self.assertIn("28.0k  2.8% of 1m", lines[2])
        self.assertIn("AFTER  same as now", lines[3])
        self.assertIn("█ core  ▓ skills  ▒ mcp  ░ memory/CLAUDE.md", lines[4])
        self.assertIn("▾ built-in tools              =20.2k", out)
        self.assertIn("  core (system prompt)        =2.9k  not tunable", out)
        self.assertIn("▾ mcp (8)                     =1.4k  on-load =146.9k", out)
        cr = next(l for l in lines if "code-review" in l)
        self.assertEqual(cr.split(), ["code-review", "=330", "on", "here", "1×", "·", "all",
                                      "1×"])
        pdf = next(l for l in lines if " pdf " in l)
        self.assertEqual(pdf.split()[:4], ["U", "pdf", "=0", "off"])
        self.assertIn("needs the headless base", out)
        self.assertNotIn("snapshot stale", out)
        self.assertNotIn(tui.FOOTER, out)

    def test_main_plain_and_pipe(self):
        for argv in (["--plain"], []):  # a pipe falls back to plain
            buf = io.StringIO()
            rc = residency.main(argv, runner=no_claude, out=buf, cwd=self.proj / "sub",
                                projects_root=self.root)
            self.assertEqual(rc, 0)
            self.assertIn("residency · skillz", buf.getvalue())

    def test_bad_settings(self):
        self.user_settings.write_text("{nope")
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            rc = residency.main(["--plain"], runner=no_claude, out=io.StringIO(),
                                projects_root=self.root, cwd=self.proj)
        self.assertEqual(rc, 1)
        self.assertIn("not valid JSON", err.getvalue())

    def test_no_snapshot(self):
        other = self.tmp / "other"
        other.mkdir()
        buf = io.StringIO()
        residency.main(["--plain", "--project", str(other)], runner=no_claude, out=buf,
                       projects_root=self.root)
        self.assertIn("no /context yet", buf.getvalue())
        self.assertIn("no snapshot of this project", buf.getvalue())

    def test_find_project(self):
        (self.proj / "a" / "b").mkdir(parents=True)
        self.assertEqual(residency.find_project(self.proj / "a" / "b", self.root), self.proj)
        self.assertEqual(residency.find_project(self.tmp, self.root), self.tmp.resolve())


class Renderers(unittest.TestCase):
    def test_ago(self):
        self.assertEqual(tui.ago(SNAP_TS, NOW), "2h ago")
        self.assertEqual(tui.ago("2026-10-16T11:59:30Z", NOW), "just now")
        self.assertEqual(tui.ago("2026-10-13T12:00:00Z", NOW), "3d ago")
        self.assertEqual(tui.ago("", NOW), "")

    def test_bar_cells(self):
        segs = {"core": 23100, "skills": 3300, "mcp": 1400, "memory": 115}
        cells = tui.bar_cells(segs, sum(segs.values()), 24)
        self.assertEqual(sum(n for _, n in cells), 24)
        self.assertEqual([g for g, _ in cells], ["core", "skills", "mcp", "memory"])
        self.assertEqual(dict(cells)["core"], 20)
        half = tui.bar_cells({"core": 50}, 100, 24)
        self.assertEqual(sum(n for _, n in half), 12)
        self.assertEqual(sum(n for _, n in tui.bar_cells({}, 0, 10)), 0)

    def test_short(self):
        self.assertEqual(tui.short("abc", 5), "abc")
        self.assertEqual(tui.short("abcdefgh", 5), "abcd…")
        self.assertEqual(tui.short("/a/b/MEMORY.md", 6), "…RY.md")

    def test_row_line(self):
        r = M.Row("tool:Agent", "Agent", setting=S.Item(S.TOOL, "Agent"), resident=1200,
                  origin="=", state="allow", after="deny", target="local", here=0, all=3,
                  delta=1200, delta_origin="=")
        line = tui.text(tui.row_line(r))
        self.assertEqual(line.split(), ["L", "Agent", "=1.2k", "allow", "→", "deny", "Δ=-1.2k",
                                        "here", "0×", "·", "all", "3×"])
        self.assertIn("measuring…", tui.text(tui.row_line(r, measuring=True)))
        r.delta, r.delta_origin = None, "?"
        self.assertIn("Δ?", tui.text(tui.row_line(r)))
        lump = M.Row("lump", "interactive-only", resident=15300, origin="=", lump=True)
        self.assertEqual(tui.text(tui.row_line(lump)).split()[:3],
                         ["·", "interactive-only", "=15.3k"])

    def test_header_after_line(self):
        snap = snapshot.parse_context((FIX / "context_interactive.md").read_text())
        snap.total = 66200  # resident 38.1k as in the mockup
        with tempfile.TemporaryDirectory() as d:
            home, proj = Path(d) / "h", Path(d) / "p"
            (home / ".claude").mkdir(parents=True)
            proj.mkdir()
            sett = S.Settings(proj, home)
            p = sett.pending()
            items = {S.Item(S.TOOL, "Agent"): ("deny", 1200),
                     S.Item(S.SKILL, "code-review"): ("name-only", 400),
                     S.Item(S.MCP, "penpot"): ("deny", 5100)}
            ms = {}
            for it, (v, n) in items.items():
                p.set(it, v)
                ms[M.measure_key(it, v)] = measure.Delta(True, n)
            m = M.build(snapshot.Found(snap, "89d7d1d1", SNAP_TS, "context"), sett, p, ms,
                        project_dir=proj, home=home)
        lines = [tui.text(l) for l in tui.header(m, "skillz", 80, NOW)]
        self.assertIn("38.1k  3.8% of 1m", lines[2])
        self.assertTrue(lines[3].startswith("AFTER  █"))
        self.assertTrue(lines[3].rstrip().endswith("31.4k  -6.7k (-18%)"))
        self.assertEqual(lines[2].index("38.1k"), lines[3].index("31.4k"))  # bars aligned


class StateTest(Env):
    def state(self):
        jobs = []
        ctx = self.ctx(FakeClaude())
        ctx.measurer.cache_path = self.tmp / "cache.json"
        st = tui.State(ctx, lambda name, change: jobs.append((name, change)))
        return st, jobs

    def select(self, st, label):
        for i, e in enumerate(st.entries()):
            if e[3] is not None and e[3].label == label:
                st.cursor = i
                return e[3]
        raise AssertionError(label)

    def test_start_asks_base(self):
        st, jobs = self.state()
        st.start()
        self.assertEqual(jobs, [((0, tui.BASE_JOB), None)])
        base = snapshot.Snapshot(total=20000, categories={"System tools": 4900})
        st.on_result(jobs[0][0], base)
        lump = next(r for r in st.model.rows() if r.lump)
        self.assertEqual(lump.resident, 20200 - 4900)

    def test_toggle_measure_result(self):
        st, jobs = self.state()
        self.select(st, "code-review")
        st.toggle()
        key = "skill|code-review|name-only"
        self.assertEqual(jobs, [((0, key), {"skillOverrides": {"code-review": "name-only"}})])
        self.assertIn(key, st.measuring)
        row = self.select(st, "code-review")
        self.assertIn("measuring…", tui.text(tui.row_line(row, True)))
        self.assertEqual(st.model.after_origin, "~")
        st.on_result((0, key), measure.Delta(True, 310))
        self.assertEqual(st.model.saved, 310)
        self.assertEqual(st.model.after_origin, "=")
        self.assertFalse(st.measuring)
        # back to `on` after the full cycle: no change pending
        for _ in range(3):
            self.select(st, "code-review")
            st.toggle()
        self.assertFalse(st.pending)
        self.assertEqual(st.model.saved, 0)

    def test_stale_and_failed_results(self):
        st, jobs = self.state()
        self.select(st, "code-review")
        st.toggle()
        st.on_result((0, "skill|code-review|name-only"), measure.MeasureError("boom"))
        self.assertIn("boom", st.status)
        st.on_result((-1, "skill|x|off"), measure.Delta(True, 1))  # older generation
        self.assertNotIn("skill|x|off", st.measures)

    def test_not_tunable_and_plugin_skill(self):
        st, jobs = self.state()
        st.expanded.add(M.MEMORY)
        self.select(st, "board:board-add")
        st.toggle()
        self.assertIn(S.NOT_SUPPORTED, st.status)
        self.assertFalse(jobs)

    def test_scope_sort_enter(self):
        st, jobs = self.state()
        self.select(st, "Agent")
        st.cycle_scope()
        self.assertEqual(st.pending.scope(S.Item(S.TOOL, "Agent")), "user")
        self.assertIn("writes to user", st.status)
        st.cycle_sort()
        self.assertEqual(st.sort, "waste")
        self.assertEqual(st.selected()[3].label, "Agent")
        st.cursor = 0
        self.assertNotIn(M.CORE, st.expanded)
        st.move(1)
        self.assertEqual(st.selected()[0], "cat:" + M.TOOLS)
        st.enter()
        self.assertNotIn(M.TOOLS, st.expanded)
        st.enter()
        self.assertIn(M.TOOLS, st.expanded)

    def test_measure_all(self):
        st, jobs = self.state()
        n = st.measure_all()
        self.assertEqual(n, len(jobs))
        keys = {name[1] for name, _ in jobs}
        self.assertIn("tool|Agent|deny", keys)
        self.assertIn("mcp|penpot|deny", keys)
        self.assertIn("skill|code-review|off", keys)
        self.assertNotIn("skill|pdf|off", keys)  # already off
        self.assertEqual(st.measure_all(), 0)  # all in flight

    def test_measures_off_without_claude(self):
        ctx = self.ctx(no_claude)
        jobs = []
        st = tui.State(ctx, lambda *a: jobs.append(a))
        self.select(st, "code-review")
        st.toggle()
        self.assertFalse(jobs)
        self.assertIn("measures off", st.status)
        self.assertEqual(st.model.saved, 330 - 20)  # estimate from its own size

    def test_write(self):
        st, jobs = self.state()
        self.select(st, "code-review")
        st.toggle()
        self.select(st, "Agent")
        st.toggle()
        diff = "\n".join(tui.text(l) for l in tui.diff_lines(st.pending))
        self.assertIn("user scope: %s" % self.user_settings, diff)
        self.assertIn('+    "code-review": "name-only"', diff)
        self.assertIn("local scope:", diff)
        predicted = st.model.after
        done = st.write(now=NOW)
        self.assertEqual(len(done), 2)
        self.assertTrue(any(b and b.name.startswith("settings.json.bak-") for _, b in done))
        self.assertEqual(json.loads(self.user_settings.read_text())["skillOverrides"],
                         {"pdf": "off", "code-review": "name-only"})
        preds = M.load_predictions(project_dir=self.proj)
        self.assertEqual(preds[-1].predicted_after, predicted)
        self.assertEqual(preds[-1].claude_version, "2.1.301")
        self.assertFalse(st.pending)
        self.assertEqual(st.gen, 1)
        self.assertIn("wrote", st.status)
        self.assertIn("predicted", st.model.comparison.line())
        self.assertEqual(jobs[-1], ((1, tui.BASE_JOB), None))  # new base for new settings


if __name__ == "__main__":
    unittest.main()
