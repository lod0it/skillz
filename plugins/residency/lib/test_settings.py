import datetime
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import settings as S

SK = S.Item(S.SKILL, "code-review")
AGENT = S.Item(S.TOOL, "Agent")
BASH = S.Item(S.TOOL, "Bash")
PENPOT = S.Item(S.MCP, "penpot")
BOARD = S.Item(S.PLUGIN, "board@launchpad")


class Base(unittest.TestCase):
    """Every test works in a temp home and project: the real ~/.claude is never read."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.proj = self.tmp / "proj"
        self.paths = S.scope_paths(self.proj, self.home)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def put(self, scope, data, raw=None):
        p = self.paths[scope]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(raw if raw is not None else json.dumps(data, indent=2) + "\n")

    def load(self):
        return S.Settings(self.proj, self.home)

    def read(self, scope):
        return json.loads(self.paths[scope].read_text())


class Paths(Base):
    def test_scope_paths(self):
        self.assertEqual(self.paths[S.USER], self.home / ".claude" / "settings.json")
        self.assertEqual(self.paths[S.PROJECT], self.proj / ".claude" / "settings.json")
        self.assertEqual(self.paths[S.LOCAL], self.proj / ".claude" / "settings.local.json")

    def test_missing_files_are_empty(self):
        st = self.load()
        self.assertEqual(st.data, {S.USER: {}, S.PROJECT: {}, S.LOCAL: {}})
        self.assertEqual(st.effective(SK), S.State("on"))
        self.assertEqual(st.effective(AGENT), S.State("allow"))
        self.assertEqual(st.effective(SK).badge, " ")

    def test_bad_json(self):
        self.put(S.PROJECT, None, raw="{oops")
        with self.assertRaises(S.SettingsError):
            self.load()
        self.put(S.PROJECT, None, raw="[]")
        with self.assertRaises(S.SettingsError):
            self.load()


class Effective(Base):
    def test_precedence_local_project_user(self):
        self.put(S.USER, {"skillOverrides": {"code-review": "off", "a": "name-only"},
                          "enabledPlugins": {"board@launchpad": True}})
        self.put(S.PROJECT, {"skillOverrides": {"code-review": "name-only"},
                             "enabledPlugins": {"board@launchpad": False}})
        self.put(S.LOCAL, {"skillOverrides": {"code-review": "user-invocable-only"}})
        st = self.load()
        self.assertEqual(st.effective(SK), S.State("user-invocable-only", S.LOCAL))
        self.assertEqual(st.effective(SK).badge, "L")
        self.assertEqual(st.effective(S.Item(S.SKILL, "a")), S.State("name-only", S.USER))
        self.assertEqual(st.effective(BOARD), S.State("off", S.PROJECT))

    def test_deny_merges_across_scopes(self):
        self.put(S.USER, {"permissions": {"deny": ["Agent"]}})
        self.put(S.PROJECT, {"permissions": {"allow": ["Bash"], "deny": ["mcp__penpot__*"]}})
        self.put(S.LOCAL, {"permissions": {"deny": ["Bash"]}})
        st = self.load()
        self.assertEqual(st.effective(AGENT), S.State("deny", S.USER))
        self.assertEqual(st.effective(PENPOT), S.State("deny", S.PROJECT))
        self.assertEqual(st.effective(BASH), S.State("deny", S.LOCAL))
        self.assertEqual(st.effective(S.Item(S.MCP, "notion")), S.State("on"))

    def test_bare_server_pattern_counts_as_deny(self):
        self.put(S.USER, {"permissions": {"deny": ["mcp__penpot"]}})
        self.assertEqual(self.load().effective(PENPOT), S.State("deny", S.USER))

    def test_cycles(self):
        self.assertEqual(S.next_state(SK, "on"), "name-only")
        self.assertEqual(S.next_state(SK, "name-only"), "user-invocable-only")
        self.assertEqual(S.next_state(SK, "user-invocable-only"), "off")
        self.assertEqual(S.next_state(SK, "off"), "on")
        self.assertEqual(S.next_state(AGENT, "deny"), "allow")
        self.assertEqual(S.next_state(PENPOT, "on"), "deny")
        self.assertEqual(S.next_state(BOARD, "on"), "off")

    def test_plugin_skill_refused(self):
        ps = S.Item(S.PLUGIN_SKILL, "board:board-add")
        st = self.load()
        p = st.pending()
        for call in (lambda: st.effective(ps), lambda: p.toggle(ps),
                     lambda: p.set(ps, "off"), lambda: p.set_scope(ps, S.LOCAL)):
            with self.assertRaises(S.NotSupported) as cm:
                call()
            self.assertEqual(str(cm.exception), S.NOT_SUPPORTED)


class Toggles(Base):
    def test_default_scopes(self):
        p = self.load().pending()
        for item in (SK, AGENT, PENPOT, BOARD):
            p.toggle(item)
        self.assertEqual(p.changes, {SK: ("name-only", S.USER), AGENT: ("deny", S.LOCAL),
                                     PENPOT: ("deny", S.LOCAL), BOARD: ("off", S.USER)})
        frags = p.fragments()
        self.assertEqual(frags[S.USER], {"skillOverrides": {"code-review": "name-only"},
                                         "enabledPlugins": {"board@launchpad": False}})
        self.assertEqual(frags[S.LOCAL], {"permissions": {"deny": ["Agent", "mcp__penpot__*"]}})
        self.assertNotIn(S.PROJECT, frags)

    def test_full_cycle_returns_to_no_change(self):
        p = self.load().pending()
        for _ in range(4):
            p.toggle(SK)
        self.assertFalse(p)
        self.assertEqual(p.diff(), {})

    def test_scope_change(self):
        p = self.load().pending()
        p.set_scope(AGENT, S.PROJECT)  # chosen before the toggle: kept
        p.toggle(AGENT)
        self.assertEqual(p.changes[AGENT], ("deny", S.PROJECT))
        p.set_scope(AGENT, S.USER)
        self.assertEqual(list(p.fragments()), [S.USER])
        with self.assertRaises(ValueError):
            p.set_scope(AGENT, "managed")

    def test_removing_inherited_deny_edits_the_scope_that_holds_it(self):
        self.put(S.USER, {"permissions": {"deny": ["Agent", "Read"]}})
        p = self.load().pending()
        self.assertEqual(p.toggle(AGENT), "allow")
        self.assertEqual(p.scope(AGENT), S.LOCAL)  # target local, but the deny is in user
        self.assertEqual(p.changed_scopes(), [S.USER])
        self.assertEqual(p.fragments(), {S.USER: {"permissions": {"deny": ["Read"]}}})
        self.assertEqual(p.effective_after(AGENT), S.State("allow"))

    def test_deny_already_inherited_is_not_duplicated(self):
        self.put(S.USER, {"permissions": {"deny": ["Agent"]}})
        p = self.load().pending()
        p.set(AGENT, "deny", S.LOCAL)
        self.assertFalse(p)

    def test_higher_scope_override_is_dropped_so_target_wins(self):
        self.put(S.PROJECT, {"skillOverrides": {"code-review": "off"}})
        p = self.load().pending()
        p.set(SK, "name-only")  # target user, project would win
        self.assertEqual(p.effective_after(SK), S.State("name-only", S.USER))
        self.assertEqual(p.after()[S.PROJECT], {"skillOverrides": {}})

    def test_skill_back_on_drops_every_override(self):
        self.put(S.USER, {"skillOverrides": {"code-review": "off"}})
        self.put(S.LOCAL, {"skillOverrides": {"code-review": "name-only"}})
        p = self.load().pending()
        p.set(SK, "on")
        self.assertEqual(p.effective_after(SK), S.State("on"))
        self.assertEqual(p.changed_scopes(), [S.USER, S.LOCAL])

    def test_cli_settings(self):
        self.put(S.USER, {"permissions": {"deny": ["Bash"]}})
        p = self.load().pending()
        p.toggle(SK)
        p.toggle(AGENT)
        p.toggle(PENPOT)
        p.toggle(BOARD)
        p.toggle(BASH)  # removal: not expressible as a layered settings file
        self.assertEqual(p.as_cli_settings(), {
            "skillOverrides": {"code-review": "name-only"},
            "permissions": {"deny": ["Agent", "mcp__penpot__*"]},
            "enabledPlugins": {"board@launchpad": False}})
        self.assertEqual(p.unexpressible(), [BASH])
        json.dumps(p.as_cli_settings())


class DiffWrite(Base):
    NOW = datetime.datetime(2026, 10, 16, 9, 5, 7)

    def test_unknown_keys_and_order_kept(self):
        raw = ('{\n  "zeta": 1,\n  "model": "opus",\n  "skillOverrides": {"b": "off", "a": "off"},'
               '\n  "hooks": {"x": [1, 2]},\n  "alpha": "è"\n}\n')
        self.put(S.USER, None, raw=raw)
        st = self.load()
        p = st.pending()
        p.toggle(SK)
        p.write(now=self.NOW)
        text = self.paths[S.USER].read_text()
        data = json.loads(text)
        self.assertEqual(list(data), ["zeta", "model", "skillOverrides", "hooks", "alpha"])
        self.assertEqual(list(data["skillOverrides"]), ["b", "a", "code-review"])
        self.assertEqual(data["hooks"], {"x": [1, 2]})
        self.assertEqual(data["alpha"], "è")
        self.assertTrue(text.endswith("}\n"))
        self.assertIn('\n  "zeta": 1,\n', text)

    def test_diff_is_unified_per_file(self):
        self.put(S.USER, {"model": "opus"})
        p = self.load().pending()
        p.toggle(SK)
        p.toggle(AGENT)
        d = p.diff()
        self.assertEqual(set(d), {S.USER, S.LOCAL})
        self.assertIn("--- %s" % self.paths[S.USER], d[S.USER])
        self.assertIn('+  "skillOverrides": {', d[S.USER])
        self.assertIn("--- /dev/null", d[S.LOCAL])  # new file
        self.assertIn('+      "Agent"', d[S.LOCAL])
        self.assertFalse(self.paths[S.LOCAL].exists())  # diff writes nothing

    def test_write_backs_up_then_writes(self):
        self.put(S.USER, {"model": "opus"})
        before = self.paths[S.USER].read_text()
        st = self.load()
        p = st.pending()
        p.toggle(BOARD)
        p.toggle(AGENT)
        done = dict(p.write(now=self.NOW))
        bak = self.paths[S.USER].with_name("settings.json.bak-20261016-090507")
        self.assertEqual(done[self.paths[S.USER]], bak)
        self.assertEqual(bak.read_text(), before)
        self.assertIsNone(done[self.paths[S.LOCAL]])  # did not exist: no backup
        self.assertEqual(self.read(S.USER),
                         {"model": "opus", "enabledPlugins": {"board@launchpad": False}})
        self.assertEqual(self.read(S.LOCAL), {"permissions": {"deny": ["Agent"]}})
        self.assertFalse(self.paths[S.PROJECT].exists())
        self.assertFalse(p)  # cleared, settings reloaded
        self.assertEqual(st.effective(BOARD), S.State("off", S.USER))
        self.assertEqual(p.diff(), {})

    def test_no_pending_writes_nothing(self):
        p = self.load().pending()
        self.assertEqual(p.write(now=self.NOW), [])
        self.assertFalse((self.home / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
