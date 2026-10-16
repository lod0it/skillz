import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path

import measure
import model as M
import settings as S
import snapshot
import usage

FIX = Path(__file__).resolve().parent / "fixtures"
UTC = datetime.timezone.utc


def interactive():
    return snapshot.parse_context((FIX / "context_interactive.md").read_text())


def headless_base():
    """The headless base; System tools set to the design's 4.9k (the fixture says 5k)."""
    s = snapshot.read_headless((FIX / "context_headless.json").read_text())
    s.categories["System tools"] = 4900
    return s


def found(snap, ts="2026-10-16T10:00:00.000Z"):
    return snapshot.Found(snap, "89d7d1d1", ts, "context")


def ctx_md(total, messages="1k", skills="3.3k"):
    return ("## Context Usage\n\n**Tokens:** %s / 1m (1%%)\n\n### Estimated usage by category\n\n"
            "| Category | Tokens | Percentage |\n|---|---|---|\n| System prompt | 2.9k | 0%% |\n"
            "| Skills | %s | 0%% |\n| Messages | %s | 0%% |\n" % (total, skills, messages))


def D(total):
    return measure.Delta(True, total)


class Base(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        self.home = self.tmp / "home"
        self.proj = self.tmp / "proj"
        (self.home / ".claude").mkdir(parents=True)
        (self.proj / ".claude").mkdir(parents=True)
        self.set_user({})
        old = datetime.datetime(2026, 1, 1, tzinfo=UTC).timestamp()
        os.utime(self.home / ".claude" / "settings.json", (old, old))

    def set_user(self, data):
        (self.home / ".claude" / "settings.json").write_text(json.dumps(data))

    def plugins_file(self, plugins):
        p = self.home / ".claude" / "plugins"
        p.mkdir(parents=True, exist_ok=True)
        (p / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": plugins}))

    def settings(self):
        return S.Settings(self.proj, self.home)

    def build(self, sett=None, pending=None, snap=None, **kw):
        sett = sett or self.settings()
        kw.setdefault("project_dir", self.proj)
        kw.setdefault("home", self.home)
        return M.build(found(snap or interactive()), sett, pending, **kw)


class Format(unittest.TestCase):
    def test_fmt(self):
        cases = [(330, False, "330"), (1200, False, "1.2k"), (146900, False, "146.9k"),
                 (57, True, "0.1k"), (2950, True, "3.0k"), (-6700, False, "-6.7k"),
                 (1000000, False, "1m"), (None, False, "?"), (0, False, "0")]
        for n, k, want in cases:
            self.assertEqual(M.fmt(n, k), want, (n, k))


class Mockup(Base):
    """The numbers of the mockup in docs/residency-design.md (Q4), from the fixtures."""

    def setUp(self):
        super().setUp()
        self.plugins_file({
            "board@launchpad": [{"scope": "user", "installPath": "/nowhere/board"}],
            "taskflow@skillz": [{"scope": "user", "installPath": "/nowhere/taskflow"}],
        })

    def test_tree(self):
        sett = self.settings()
        p = sett.pending()
        agent, review = S.Item(S.TOOL, "Agent"), S.Item(S.SKILL, "code-review")
        p.set(agent, "deny")
        p.set(review, "name-only")
        measures = {M.measure_key(agent, "deny"): D(1200),
                    # fake headless delta, chosen so skills read 3.3k -> 2.9k as in the mockup
                    M.measure_key(review, "name-only"): D(400)}
        here = usage.Counts(skills={"code-review": 4}, tools={"Agent": 0})
        all_ = usage.Counts(skills={"code-review": 9}, tools={"Agent": 3})
        m = self.build(sett, p, measures=measures, here=here, all_=all_, headless=headless_base())
        k = lambda n: M.fmt(n, True)

        core = m.category(M.CORE)
        self.assertEqual((k(core.resident), core.origin, core.note), ("2.9k", "=", "not tunable"))

        tools = m.category(M.TOOLS)
        self.assertEqual((k(tools.resident), k(tools.after)), ("20.2k", "19.0k"))
        a = next(r for r in tools.rows if r.label == "Agent")
        self.assertEqual((M.fmt(a.resident), a.origin, a.badge, a.state, a.after, a.target),
                         ("1.2k", "=", " ", "allow", "deny", "local"))
        self.assertEqual((a.here, a.all), (0, 3))
        self.assertEqual(tools.rows[0].label, "Agent")  # sorted by cost, unknowns sink
        lump = tools.rows[-1]
        self.assertTrue(lump.lump)
        self.assertEqual((k(lump.resident), lump.origin), ("15.3k", "="))

        skills = m.category(M.SKILLS)
        self.assertEqual((skills.label, k(skills.resident), k(skills.after)),
                         ("skills (23)", "3.3k", "2.9k"))
        cr = next(r for r in skills.rows if r.label == "code-review")
        self.assertEqual((cr.resident, cr.origin, cr.state, cr.after, cr.badge, cr.target),
                         (330, "=", "on", "name-only", " ", "user"))
        self.assertEqual((cr.here, cr.all, cr.delta, cr.delta_origin), (4, 9, 400, "="))
        pb = next(r for r in skills.rows if r.label == "board:board-add")
        self.assertFalse(pb.tunable)
        self.assertEqual(pb.note, S.NOT_SUPPORTED)

        plugins = m.category(M.PLUGINS)
        self.assertEqual(plugins.label, "plugins (2)")
        self.assertEqual(plugins.resident, 720)  # the fixture's 6 plugin skills (mockup: 0.8k)
        self.assertEqual(sorted(r.label for r in plugins.rows),
                         ["board@launchpad", "taskflow@skillz"])

        mcp = m.category(M.MCP)
        self.assertEqual((k(mcp.resident), k(mcp.on_load)), ("1.4k", "146.9k"))
        self.assertEqual(mcp.label, "mcp (8)")  # the fixture has 8 servers (mockup: 6)
        notion = next(r for r in mcp.rows if r.label == "claude_ai_Notion")
        self.assertEqual((notion.resident, notion.origin), (None, "?"))

        self.assertEqual(k(m.category(M.MEMORY).resident), "0.1k")
        self.assertEqual(m.after, m.now - 1600)
        self.assertEqual(m.after_origin, "=")

    def test_totals(self):
        snap = interactive()
        snap.total = 66200  # Messages 28.1k: the resident total is the mockup's 38.1k
        sett = self.settings()
        p = sett.pending()
        items = {S.Item(S.TOOL, "Agent"): ("deny", 1200),
                 S.Item(S.SKILL, "code-review"): ("name-only", 400),
                 S.Item(S.MCP, "penpot"): ("deny", 5100)}
        measures = {}
        for it, (v, d) in items.items():
            p.set(it, v)
            measures[M.measure_key(it, v)] = D(d)
        m = self.build(sett, p, snap=snap, measures=measures)
        self.assertEqual((M.fmt(m.now), M.fmt(m.after), M.fmt(-m.saved)),
                         ("38.1k", "31.4k", "-6.7k"))
        self.assertEqual(round(m.saved_pct), 18)
        self.assertEqual("%.1f%%" % m.window_pct, "3.8%")
        now, after = m.segments(), m.segments(after=True)
        self.assertEqual(sum(now.values()), 2900 + 20200 + 3300 + 1400 + 57 + 58)
        self.assertEqual(now["core"] - after["core"], 1200)
        self.assertEqual(now["mcp"] - after["mcp"], 5100)


class Origins(Base):
    def test_unmeasured_toggle_uses_own_size(self):
        sett = self.settings()
        p = sett.pending()
        p.set(S.Item(S.SKILL, "code-review"), "off")
        p.set(S.Item(S.SKILL, "loop"), "name-only")
        p.set(S.Item(S.TOOL, "Bash"), "deny")
        m = self.build(sett, p)
        rows = {r.label: r for r in m.rows()}
        self.assertEqual((rows["code-review"].delta, rows["code-review"].delta_origin), (330, "~"))
        self.assertEqual((rows["loop"].delta, rows["loop"].delta_origin), (100, "~"))
        self.assertEqual((rows["Bash"].delta, rows["Bash"].delta_origin), (None, "?"))
        self.assertEqual(m.after, m.now - 430)
        self.assertEqual(m.after_origin, "?")

    def test_negative_measured_delta(self):
        sett = self.settings()
        p = sett.pending()
        bash = S.Item(S.TOOL, "Bash")
        p.set(bash, "deny")
        m = self.build(sett, p, measures={M.measure_key(bash, "deny"): D(-500)})
        self.assertEqual(m.after, m.now + 500)

    def test_learned_beats_headless(self):
        sett = self.settings()
        p = sett.pending()
        it = S.Item(S.SKILL, "code-review")
        p.set(it, "off")
        key = M.measure_key(it, "off")
        m = self.build(sett, p, measures={key: D(300)}, learned={key: 350})
        self.assertEqual(m.after, m.now - 350)

    def test_failed_measure_is_ignored(self):
        sett = self.settings()
        p = sett.pending()
        it = S.Item(S.SKILL, "code-review")
        p.set(it, "off")
        m = self.build(sett, p, measures={M.measure_key(it, "off"): measure.Delta(False)})
        self.assertEqual(next(r for r in m.rows() if r.label == "code-review").delta_origin, "~")

    def test_items_missing_from_snapshot(self):
        sk = self.home / ".claude" / "skills" / "fresh"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: fresh\ndescription: >\n  " + "x" * 75
                                     + "\n---\nbody\n")
        self.set_user({"skillOverrides": {"gone": "off", "mystery": "name-only"},
                       "enabledPlugins": {"old@mk": False}})
        rows = {r.label: r for r in self.build().rows()}
        self.assertEqual((rows["fresh"].resident, rows["fresh"].origin), (20, "~"))  # 80/4
        self.assertEqual((rows["gone"].resident, rows["gone"].origin, rows["gone"].badge),
                         (0, "=", "U"))
        self.assertEqual((rows["mystery"].resident, rows["mystery"].origin), (None, "?"))
        self.assertEqual((rows["old@mk"].state, rows["old@mk"].resident), ("off", 0))

    def test_plugin_estimate_from_skill_files(self):
        inst = self.tmp / "plug"
        for name, desc in (("a", "y" * 39), ("b", "z" * 7)):
            (inst / "skills" / name).mkdir(parents=True)
            (inst / "skills" / name / "SKILL.md").write_text(
                "---\nname: %s\ndescription: \"%s\"\n---\n" % (name, desc))
        self.plugins_file({"new@mk": [{"scope": "user", "installPath": str(inst)}],
                           "elsewhere@mk": [{"scope": "project", "projectPath": "/x",
                                             "installPath": str(inst)}]})
        rows = {r.label: r for r in self.build().rows()}
        self.assertEqual((rows["new@mk"].resident, rows["new@mk"].origin), (12, "~"))
        self.assertNotIn("elsewhere@mk", rows)

    def test_denied_tool_and_server(self):
        (self.proj / ".claude" / "settings.local.json").write_text(json.dumps(
            {"permissions": {"deny": ["WebSearch", "mcp__penpot__*", "Bash(rm:*)"]}}))
        old = datetime.datetime(2026, 1, 1, tzinfo=UTC).timestamp()
        os.utime(self.proj / ".claude" / "settings.local.json", (old, old))
        m = self.build()
        rows = {r.label: r for r in m.rows()}
        self.assertEqual((rows["WebSearch"].state, rows["WebSearch"].badge,
                          rows["WebSearch"].resident), ("deny", "L", 0))
        self.assertEqual(rows["penpot"].state, "deny")
        self.assertNotIn("Bash(rm:*)", rows)

    def test_usage_adds_tools(self):
        here = usage.Counts(tools={"AskUserQuestion": 2, "mcp__x__y": 1}, mcp={"penpot": 5},
                            skills={"board:board-add": 2, "board:board-work": 1})
        rows = {r.label: r for r in self.build(here=here, all_=here).rows()}
        self.assertEqual(rows["AskUserQuestion"].here, 2)
        self.assertNotIn("mcp__x__y", rows)
        self.assertEqual(rows["penpot"].here, 5)
        self.assertEqual(rows["board"].here, 3)  # no marketplace known: plain name
        self.assertEqual(rows["board"].note, "marketplace unknown")

    def test_no_snapshot(self):
        m = M.build(None, self.settings(), project_dir=self.proj, home=self.home)
        self.assertIsNone(m.now)
        self.assertIsNone(m.after)
        self.assertEqual(m.category(M.CORE).origin, "?")


class Sorting(unittest.TestCase):
    def test_cost_and_waste(self):
        rows = [M.Row("a", "a", resident=300, here=10), M.Row("b", "b", resident=200, here=0),
                M.Row("c", "c"), M.Row("l", "l", resident=9999, lump=True)]
        self.assertEqual([r.key for r in M.sort_rows(rows, "cost")], ["a", "b", "c", "l"])
        self.assertEqual([r.key for r in M.sort_rows(rows, "waste")], ["b", "a", "c", "l"])
        with self.assertRaises(ValueError):
            M.sort_rows(rows, "x")


class Stale(Base):
    def test_stale_when_settings_newer(self):
        m = self.build()
        self.assertIsNone(m.stale_since)
        self.assertEqual(m.stale_line(), "")
        self.set_user({"x": 1})  # mtime now, after the 2026-10-16 snapshot? set explicitly
        t = datetime.datetime(2026, 10, 16, 12, 0, tzinfo=UTC).timestamp()
        os.utime(self.home / ".claude" / "settings.json", (t, t))
        m = self.build()
        self.assertEqual(m.stale_since.timestamp(), t)
        self.assertTrue(m.stale_line().startswith("snapshot stale: settings changed since 2026-10-16"))


class Predictions(Base):
    def transcript(self, entries):
        d = snapshot.transcripts_dir(self.proj, self.tmp / "projects")
        d.mkdir(parents=True, exist_ok=True)
        recs = [{"type": "user", "isMeta": True, "timestamp": ts,
                 "message": {"content": md}} for ts, md in entries]
        recs.insert(1, {"type": "assistant", "message": {"content": []}})
        (d / "s.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        return M.interactive_snapshots(self.proj, self.tmp / "projects")

    def test_record_compare_learn(self):
        path = self.tmp / "pred.jsonl"
        sett = self.settings()
        p = sett.pending()
        p.set(S.Item(S.SKILL, "code-review"), "off")
        m = self.build(sett, p)
        t1 = datetime.datetime(2026, 10, 16, 11, 0, tzinfo=UTC)
        rec = M.record_prediction(m, p, self.proj, "2.1.301", path, now=t1)
        self.assertEqual(rec.changes, [{"kind": "skill", "name": "code-review", "from": "on",
                                        "to": "off", "scope": "user"}])
        self.assertEqual(rec.predicted_after, m.after)
        preds = M.load_predictions(path, self.proj)
        self.assertEqual(len(preds), 1)
        self.assertEqual(M.load_predictions(path, "/other"), [])

        snaps = self.transcript([("2026-10-16T10:00:00.000Z", ctx_md("30k", "2k")),
                                 ("2026-10-16T12:00:00.000Z", ctx_md("29.7k", "2k"))])
        self.assertEqual(len(snaps), 2)
        c = M.compare(preds, snaps, self.proj)
        self.assertEqual((c.predicted, c.actual), (m.after, 27700))
        self.assertEqual(c.error, 27700 - m.after)
        self.assertIn("actual 27.7k", c.line())
        self.assertEqual(M.learn(preds, snaps, self.proj), {"skill|code-review|off": 300})

        m2 = self.build(sett, None, predictions=preds, snapshots=snaps)
        self.assertEqual(m2.comparison.actual, 27700)

    def test_waiting_and_ambiguous(self):
        path = self.tmp / "pred.jsonl"
        sett = self.settings()
        p = sett.pending()
        p.set(S.Item(S.SKILL, "code-review"), "off")
        m = self.build(sett, p)
        for h in (11, 11.5):
            M.record_prediction(m, p, self.proj, "v", path,
                                now=datetime.datetime(2026, 10, 16, int(h), int(h % 1 * 60),
                                                      tzinfo=UTC))
        preds = M.load_predictions(path)
        snaps = self.transcript([("2026-10-16T10:00:00.000Z", ctx_md("30k"))])
        c = M.compare(preds, snaps, self.proj)
        self.assertIsNone(c.actual)
        self.assertIn("predicted", c.line())
        snaps = self.transcript([("2026-10-16T10:00:00.000Z", ctx_md("30k")),
                                 ("2026-10-16T12:00:00.000Z", ctx_md("29k"))])
        self.assertEqual(M.learn(preds, snaps, self.proj), {})  # two writes in between

    def test_learned_file(self):
        path = self.tmp / "learned.json"
        self.assertEqual(M.load_learned(path), {})
        M.save_learned({"skill|a|off": 300}, path)
        M.save_learned({"tool|Agent|deny": 1200}, path)
        self.assertEqual(M.load_learned(path), {"skill|a|off": 300, "tool|Agent|deny": 1200})


class Helpers(Base):
    def test_change_for(self):
        sett = self.settings()
        self.assertEqual(M.change_for(sett, S.Item(S.TOOL, "Agent"), "deny"),
                         {"permissions": {"deny": ["Agent"]}})
        self.set_user({"permissions": {"deny": ["Agent"]}})
        self.assertIsNone(M.change_for(self.settings(), S.Item(S.TOOL, "Agent"), "allow"))

    def test_frontmatter(self):
        f = self.tmp / "S.md"
        f.write_text("---\nname: ab\ndescription: cdef\n---\n")
        self.assertEqual(M.frontmatter_tokens(f), 2)
        f.write_text("no frontmatter")
        self.assertIsNone(M.frontmatter_tokens(f))
        self.assertIsNone(M.frontmatter_tokens(self.tmp / "missing"))


if __name__ == "__main__":
    unittest.main()
