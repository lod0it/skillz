import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import statusline  # noqa: E402
import statusline_config as cfg  # noqa: E402
import statusline_styles as styles  # noqa: E402

ESC = re.compile(r"\x1b\[[0-9;]*m")


def plain(s):
    return ESC.sub("", s)


def data(ctx=37, ses=65, wk=14, branch="main"):
    d = styles.Data(branch)
    if ctx is not None:
        d.metrics.append(styles.Metric("ctx", "CTX", ctx, hist=[8, 20, ctx]))
    if ses is not None:
        d.metrics.append(styles.Metric("ses", "Session", ses, "1h 40m", 0.67, [20, 40, ses]))
    if wk is not None:
        d.metrics.append(styles.Metric("wk", "Weekly", wk, "4d 16h", 0.33, [2, 8, wk]))
    return d


class StylesTest(unittest.TestCase):
    def test_there_are_24_styles(self):
        self.assertEqual(len(styles.NAMES), 24)
        self.assertEqual(styles.DEFAULT, "plain")
        self.assertIn(styles.DEFAULT, styles.NAMES)

    def test_every_style_shows_all_four_values(self):
        for name in styles.NAMES:
            for colors in (True, False):
                out = plain(styles.render(name, data(), styles.Paint(colors, True)))
                self.assertIn("37", out, name)
                self.assertIn("65", out, name)
                self.assertIn("14", out, name)
                self.assertIn("main", out, name)
                self.assertTrue(out.strip(), name)

    def test_every_style_survives_missing_values(self):
        for name in styles.NAMES:
            for d in (data(ses=None), data(ctx=None, wk=None), data(branch=""), styles.Data()):
                out = styles.render(name, d, styles.Paint(True, False))
                self.assertIsInstance(out, str, name)

    def test_unknown_name_falls_back_to_default(self):
        d = data()
        self.assertEqual(styles.render("nope", d, styles.Paint(False)),
                         styles.render("plain", d, styles.Paint(False)))

    def test_no_color_has_no_escape(self):
        for name in styles.NAMES:
            self.assertNotIn("\x1b", styles.render(name, data(), styles.Paint(False)), name)

    def test_background_styles_fall_back_without_color(self):
        P = styles.Paint(False)
        for name in ("chips", "pills", "powerline", "smooth", "inbar"):
            self.assertEqual(styles.render(name, data(), P), styles.render("brackets", data(), P), name)

    def test_plain_line(self):
        self.assertEqual(plain(styles.render("plain", data(), styles.Paint(True))),
                         "Branch: main | CTX 37% | Session 65% ⟳ 1h 40m | Weekly 14% ⟳ 4d 16h")

    def test_traffic_light_cells(self):
        P = styles.Paint(True)
        self.assertIn("\x1b[1;32m14%", styles.render("solid", data(), P))
        self.assertIn("\x1b[1;33m65%", styles.render("solid", data(), P))
        self.assertIn("\x1b[1;31m91%", styles.render("solid", data(ctx=91), P))

    def test_multi_line_styles(self):
        self.assertEqual(len(styles.render("tree", data(), styles.Paint(False)).split("\n")), 4)
        self.assertEqual(len(styles.render("dash", data(), styles.Paint(False)).split("\n")), 2)
        self.assertEqual(len(styles.render("solid", data(), styles.Paint(False)).split("\n")), 1)

    def test_bar_fill_counts(self):
        out = plain(styles.render("solid", data(ctx=40, ses=100, wk=0), styles.Paint(True)))
        self.assertIn("████░░░░░░ 40%", out)
        self.assertIn("██████████ 100%", out)
        self.assertIn("░░░░░░░░░░ 0%", out)

    def test_smooth_bar_width_is_constant(self):
        for p in (0, 1, 4, 12.5, 37, 50, 99, 100):
            out = plain(styles.smooth(styles.Paint(True), p, 10))
            self.assertEqual(len(out), 10, p)

    def test_pace_marker_position(self):
        out = plain(styles.pace(styles.Paint(True), 10, 0.5, 16))
        self.assertEqual(out.index("┃"), 8)
        self.assertEqual(len(out), 16)
        self.assertEqual(plain(styles.pace(styles.Paint(True), 10, 1.0, 16)).index("┃"), 15)

    def test_gradient_without_truecolor_uses_ansi(self):
        out = styles.render("gradient", data(), styles.Paint(True, False))
        self.assertNotIn("38;2;", out)
        self.assertIn("38;2;", styles.render("gradient", data(), styles.Paint(True, True)))

    def test_visible_width(self):
        self.assertEqual(styles.visible_width("\x1b[1;32mabc\x1b[0m\nde"), 3)
        self.assertEqual(styles.visible_width("🌿ab"), 4)
        self.assertEqual(styles.visible_width(""), 0)

    def test_describe_names_the_requirement(self):
        self.assertIn("Nerd", styles.describe("powerline"))
        self.assertIn("emoji", styles.describe("emoji"))
        self.assertNotIn("needs", styles.describe("plain"))


class GrayTest(unittest.TestCase):
    HUE_FG = re.compile(r"\x1b\[(?:[0-9;]*;)?(?:3[1-6]|9[1-6]|4[1-6])(?:;[0-9;]*)?m")

    def codes(self, out):
        return [c for grp in re.findall(r"\x1b\[([0-9;]*)m", out) for c in [grp]]

    def test_no_hue_in_gray_mode(self):
        P = styles.Paint(True, True, gray=True)
        for name in styles.NAMES:
            for d in (data(), data(ctx=91, ses=94, wk=88)):
                out = styles.render(name, d, P)
                for grp in self.codes(out):
                    parts = grp.split(";")
                    i = 0
                    while i < len(parts):
                        c = parts[i]
                        if c in ("38", "48") and parts[i + 1:i + 2] == ["5"]:
                            n = int(parts[i + 2])
                            self.assertTrue(n >= 232 or n in (15, 16), (name, grp))
                            i += 3
                            continue
                        self.assertNotIn(c, ("31", "32", "33", "34", "35", "36", "41", "42", "43", "44",
                                             "45", "46", "92"), (name, grp))
                        i += 1
                self.assertNotIn("38;2;", out, name)

    def test_gray_keeps_severity_visible(self):
        P = styles.Paint(True, False, gray=True)
        low, mid, high = (styles.render("plain", data(ses=v, ctx=None, wk=None), P) for v in (10, 70, 95))
        self.assertEqual(len({low, mid, high}), 3)
        self.assertIn("\x1b[1;7;97m95%", high)
        self.assertNotIn(";7;", low)

    def test_gray_matches_color_text(self):
        for name in styles.NAMES:
            a = plain(styles.render(name, data(), styles.Paint(True, False)))
            b = plain(styles.render(name, data(), styles.Paint(True, False, gray=True)))
            self.assertEqual(a, b, name)

    def test_color_mode_precedence(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": t}):
                os.environ.pop("NO_COLOR", None)
                os.environ.pop("STATUSLINE_COLOR", None)
                self.assertEqual(cfg.color_mode(t), "on")
                cfg.write(cfg.user_path(), {"color": "gray"})
                self.assertEqual(cfg.color_mode(t), "gray")
                cfg.write(cfg.user_path(), {"color": "bogus"})
                self.assertEqual(cfg.color_mode(t), "on")
                cfg.write(cfg.user_path(), {"color": "gray"})
                self.assertEqual(cfg.color_mode(t, {"STATUSLINE_COLOR": "off"}), "off")
                self.assertEqual(cfg.color_mode(t, {"STATUSLINE_COLOR": "on"}), "on")
                self.assertEqual(cfg.color_mode(t, {"NO_COLOR": "1", "STATUSLINE_COLOR": "on"}), "off")

    def test_run_uses_the_configured_mode(self):
        doc = RunTest.DOC
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": t}):
                for k in ("NO_COLOR", "STATUSLINE_COLOR", "STATUSLINE_STYLE"):
                    os.environ.pop(k, None)
                cfg.write(cfg.user_path(), {"color": "gray"})
                gray = statusline.run(json.dumps(doc))
                self.assertIn("\x1b[", gray)
                self.assertNotIn("\x1b[1;32m", gray)
                cfg.write(cfg.user_path(), {"color": "off"})
                self.assertNotIn("\x1b", statusline.run(json.dumps(doc)))
                cfg.write(cfg.user_path(), {"color": None})
                self.assertIn("\x1b[1;32m", statusline.run(json.dumps(doc)))


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proj = Path(self.tmp.name) / "proj"
        self.proj.mkdir()
        p = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(Path(self.tmp.name) / "cfg")})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("STATUSLINE_STYLE", None)

    def user(self, doc):
        cfg.write(cfg.user_path(), doc)

    def project(self, doc):
        cfg.write(cfg.project_path(self.proj), doc)

    def test_default_without_files(self):
        self.assertEqual(cfg.requested(str(self.proj)), ("plain", "default"))

    def test_layer_order(self):
        self.user({"style": "dim"})
        self.assertEqual(cfg.requested(str(self.proj)), ("dim", "user config"))
        self.project({"style": "solid"})
        self.assertEqual(cfg.requested(str(self.proj)), ("solid", "project file"))
        env = {"STATUSLINE_STYLE": "pie"}
        self.assertEqual(cfg.requested(str(self.proj), env), ("pie", "env STATUSLINE_STYLE"))

    def test_invalid_layer_is_skipped(self):
        self.user({"style": "dim"})
        self.project({"style": "bogus"})
        self.assertEqual(cfg.requested(str(self.proj), {"STATUSLINE_STYLE": "zzz"}), ("dim", "user config"))

    def test_broken_files_do_not_raise(self):
        cfg.user_path().parent.mkdir(parents=True)
        cfg.user_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(cfg.requested(str(self.proj))[0], "plain")
        cfg.user_path().write_text("[1]", encoding="utf-8")
        self.assertEqual(cfg.requested(str(self.proj))[0], "plain")

    def test_alert_rule(self):
        self.user({"style": "dash", "alert": {"at": 85, "style": "heat"}})
        P = styles.Paint(False)
        self.assertEqual(cfg.choose(data(ctx=4, ses=12, wk=14), P, str(self.proj))[0], "dash")
        self.assertEqual(cfg.choose(data(ctx=4, ses=94, wk=14), P, str(self.proj))[0], "heat")
        self.assertEqual(cfg.choose(data(ctx=4, ses=85, wk=14), P, str(self.proj))[0], "heat")
        self.assertEqual(cfg.choose(styles.Data(), P, str(self.proj))[0], "dash")

    def test_alert_with_bad_settings_is_ignored(self):
        P = styles.Paint(False)
        for bad in ({"at": "x", "style": "heat"}, {"at": 50, "style": "nope"}, 7, "x"):
            self.user({"style": "dash", "alert": bad})
            self.assertEqual(cfg.choose(data(ses=94), P, str(self.proj))[0], "dash", bad)

    def test_fit_rule_walks_the_fallbacks(self):
        self.user({"style": "dash", "fit": ["pie", "whisper"]})
        P = styles.Paint(False)
        d = data()
        w = {n: styles.visible_width(styles.render(n, d, P)) for n in ("dash", "pie", "whisper")}
        self.assertTrue(w["whisper"] < w["pie"])
        self.assertEqual(cfg.choose(d, P, str(self.proj), cols=w["dash"])[0], "dash")
        self.assertEqual(cfg.choose(d, P, str(self.proj), cols=w["pie"])[0], "pie" if w["dash"] > w["pie"] else "dash")
        self.assertEqual(cfg.choose(d, P, str(self.proj), cols=w["whisper"])[0], "whisper")
        name, trace = cfg.choose(d, P, str(self.proj), cols=5)
        self.assertEqual(name, "whisper")
        self.assertIn("clipped", trace[-1])

    def test_fit_needs_known_columns(self):
        self.user({"style": "dash", "fit": ["whisper"]})
        self.assertEqual(cfg.choose(data(), styles.Paint(False), str(self.proj), cols=None)[0], "dash")

    def test_project_overrides_fit_and_alert(self):
        self.user({"style": "dash", "alert": {"at": 85, "style": "heat"}})
        self.project({"alert": {"at": 50, "style": "tree"}})
        self.assertEqual(cfg.choose(data(ses=60), styles.Paint(False), str(self.proj))[0], "tree")

    def test_columns_setting_wins(self):
        self.user({"columns": 77})
        self.assertEqual(cfg.terminal_columns(str(self.proj)), 77)
        self.user({"columns": "wide"})
        with mock.patch.dict(os.environ, {"COLUMNS": "91"}), \
                mock.patch("os.open", side_effect=OSError):
            self.assertEqual(cfg.terminal_columns(str(self.proj)), 91)

    def test_write_merges_and_drops_none(self):
        self.user({"style": "dim", "fit": ["pie"]})
        self.user({"style": "tree", "fit": None})
        self.assertEqual(cfg.read(cfg.user_path()), {"style": "tree"})
        self.assertEqual([p.name for p in cfg.user_path().parent.iterdir()], ["config.json"])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proj = Path(self.tmp.name) / "proj"
        self.proj.mkdir()
        for p in (mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(Path(self.tmp.name) / "cfg"),
                                               "NO_COLOR": "1"}),
                  mock.patch("os.getcwd", return_value=str(self.proj))):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("STATUSLINE_STYLE", None)
        self.lines = []

    def cli(self, *args):
        self.lines = []
        code = statusline.cli(list(args), out=lambda s="": self.lines.append(s))
        return code, "\n".join(self.lines)

    def test_list_marks_the_style_in_use(self):
        code, text = self.cli("style", "list")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.lines), 24)
        self.assertTrue(self.lines[0].startswith("* plain"))
        self.cli("style", "set", "tree")
        self.assertIn("* tree", self.cli("style", "list")[1])

    def test_set_writes_user_config(self):
        code, text = self.cli("style", "set", "heat")
        self.assertEqual(code, 0)
        self.assertEqual(cfg.read(cfg.user_path())["style"], "heat")

    def test_set_project(self):
        self.cli("style", "set", "solid", "--project")
        self.assertEqual(cfg.read(cfg.project_path(self.proj))["style"], "solid")
        self.assertFalse(cfg.user_path().exists())
        self.cli("style", "set", "dim")
        self.assertIn("note: solid still wins", self.lines[-1])

    def test_set_unknown_style_fails_and_writes_nothing(self):
        code, text = self.cli("style", "set", "nope")
        self.assertEqual(code, 1)
        self.assertIn("unknown style", text)
        self.assertFalse(cfg.user_path().exists())
        self.assertEqual(self.cli("style", "set")[0], 1)

    def test_next_and_prev_wrap_around(self):
        names = styles.NAMES
        self.cli("style", "next")
        self.assertEqual(cfg.read(cfg.user_path())["style"], names[1])
        self.cli("style", "prev")
        self.cli("style", "prev")
        self.assertEqual(cfg.read(cfg.user_path())["style"], names[-1])
        self.cli("style", "next")
        self.assertEqual(cfg.read(cfg.user_path())["style"], names[0])

    def test_random_changes_the_style(self):
        self.cli("style", "set", "dim")
        self.cli("style", "random")
        self.assertNotEqual(cfg.read(cfg.user_path())["style"], "dim")

    def test_preview_one_and_all(self):
        code, text = self.cli("style", "preview", "plain")
        self.assertEqual(code, 0)
        self.assertIn("Branch: main | CTX 37% | Session 65% ⟳ 1h 40m", text)
        self.assertEqual(self.cli("style", "preview", "zzz")[0], 1)
        code, text = self.cli("style", "preview", "all")
        for n in styles.NAMES:
            self.assertIn(n + "  ", text)

    def test_fit_and_alert_commands(self):
        self.cli("style", "fit", "pie,whisper")
        self.assertEqual(cfg.read(cfg.user_path())["fit"], ["pie", "whisper"])
        self.assertEqual(self.cli("style", "fit", "pie,zzz")[0], 1)
        self.cli("style", "alert", "85", "heat")
        self.assertEqual(cfg.read(cfg.user_path())["alert"], {"at": 85, "style": "heat"})
        self.assertEqual(self.cli("style", "alert", "x", "heat")[0], 2)
        self.cli("style", "fit", "off")
        self.cli("style", "alert", "off")
        self.assertNotIn("fit", cfg.read(cfg.user_path()))
        self.assertNotIn("alert", cfg.read(cfg.user_path()))

    def test_show_names_the_winning_layer(self):
        self.cli("style", "set", "tree")
        code, text = self.cli("style", "show")
        self.assertEqual(code, 0)
        self.assertIn("user config", text)
        self.assertIn("shown: tree", text)

    def test_color_command(self):
        os.environ.pop("NO_COLOR")
        self.assertEqual(self.cli("style", "color", "gray")[0], 0)
        self.assertEqual(cfg.read(cfg.user_path())["color"], "gray")
        self.cli("style", "color", "off", "--project")
        self.assertEqual(cfg.read(cfg.project_path(self.proj))["color"], "off")
        self.assertEqual(self.cli("style", "color", "on")[0], 0)
        self.assertIn("note: off still wins", "\n".join(self.lines))
        self.assertNotIn("color", cfg.read(cfg.user_path()))
        self.assertEqual(self.cli("style", "color", "pink")[0], 2)
        self.assertEqual(self.cli("style", "color")[0], 2)

    def test_preview_modes_do_not_save(self):
        os.environ.pop("NO_COLOR")
        code, text = self.cli("style", "preview", "plain", "--gray")
        self.assertIn("\x1b[", text)
        self.assertNotIn("\x1b[1;32m", text)
        code, text = self.cli("style", "preview", "plain", "--off")
        self.assertNotIn("\x1b", text)
        self.assertFalse(cfg.user_path().exists())

    def test_usage(self):
        self.assertEqual(self.cli()[0], 2)
        self.assertEqual(self.cli("style")[0], 2)
        self.assertEqual(self.cli("style", "bogus")[0], 2)
        self.assertEqual(self.cli("style", "--help")[0], 0)


class RunTest(unittest.TestCase):
    DOC = {"session_id": "s1", "workspace": {"current_dir": "/nonexistent"},
           "context_window": {"used_percentage": 30},
           "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": 1790000000},
                           "seven_day": {"used_percentage": 18, "resets_at": 1790400000}}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.tmp.name, "NO_COLOR": "1"})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("STATUSLINE_STYLE", None)

    def test_history_appends_changes_only_and_caps(self):
        for v in (10, 10, 20, 30):
            doc = json.loads(json.dumps(self.DOC))
            doc["context_window"]["used_percentage"] = v
            statusline.run(json.dumps(doc))
        self.assertEqual(statusline.read_history()["ctx"], [10, 20, 30])
        for v in range(40, 90, 5):
            doc = json.loads(json.dumps(self.DOC))
            doc["context_window"]["used_percentage"] = v
            statusline.run(json.dumps(doc))
        self.assertEqual(len(statusline.read_history()["ctx"]), 8)
        self.assertEqual(statusline.read_history()["ctx"][-1], 85)

    def test_context_history_restarts_with_a_new_session(self):
        statusline.run(json.dumps(self.DOC))
        doc = dict(self.DOC, session_id="s2")
        doc["context_window"] = {"used_percentage": 5}
        statusline.run(json.dumps(doc))
        self.assertEqual(statusline.read_history()["ctx"], [5])
        self.assertEqual(statusline.read_history()["ses"], [42])

    def test_spark_style_reads_the_history(self):
        cfg.write(cfg.user_path(), {"style": "spark"})
        for v in (10, 50, 90):
            doc = json.loads(json.dumps(self.DOC))
            doc["context_window"]["used_percentage"] = v
            line = statusline.run(json.dumps(doc))
        self.assertIn("CTX ▁▅█ 90%", line)

    def test_configured_style_is_used(self):
        cfg.write(cfg.user_path(), {"style": "whisper"})
        self.assertRegex(statusline.run(json.dumps(self.DOC)), r"^ctx 30% · 5h 42% ⟳ .+ · 7d 18% ⟳ ")

    def test_env_beats_config(self):
        cfg.write(cfg.user_path(), {"style": "whisper"})
        with mock.patch.dict(os.environ, {"STATUSLINE_STYLE": "plain"}):
            self.assertTrue(statusline.run(json.dumps(self.DOC)).startswith("CTX 30%"))

    def test_bad_config_still_prints(self):
        cfg.user_path().parent.mkdir(parents=True)
        cfg.user_path().write_text("{broken", encoding="utf-8")
        self.assertIn("Weekly 18%", statusline.run(json.dumps(self.DOC)))

    def test_every_style_through_run(self):
        for name in styles.NAMES:
            cfg.write(cfg.user_path(), {"style": name})
            self.assertIn("30", statusline.run(json.dumps(self.DOC)), name)


if __name__ == "__main__":
    unittest.main()
