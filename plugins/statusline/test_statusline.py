import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import statusline  # noqa: E402

FULL = {
    "session_id": "abc-123",
    "model": {"display_name": "Opus"},
    "workspace": {"current_dir": "C:\\Users\\x\\proj"},
    "rate_limits": {
        "five_hour": {"used_percentage": 42, "resets_at": 1790000000},
        "seven_day": {"used_percentage": 18.4, "resets_at": 1790400000},
    },
}


def plain(s):
    return re.sub(r"\[[0-9;]*m", "", s)


G, Y, R = "[1;32m", "[1;33m", "[1;31m"


class StatuslineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)
        self.file = Path(self.tmp.name) / "statusline" / "rate_limits.json"

    def test_full_prints_line_and_writes_file(self):
        line = statusline.run(json.dumps(FULL))
        self.assertIn("Opus", line)
        self.assertIn("proj", line)
        self.assertRegex(plain(line), r"session 42% ⟳ .+ │ week 18% ⟳ ")
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["session_id"], "abc-123")
        self.assertIsInstance(data["updated_at"], int)
        self.assertEqual(data["five_hour"], {"used_percentage": 42, "resets_at": 1790000000})
        self.assertEqual(data["seven_day"], {"used_percentage": 18.4, "resets_at": 1790400000})
        self.assertEqual(list(self.file.parent.iterdir()), [self.file])

    def test_session_id_null_when_missing(self):
        doc = dict(FULL)
        del doc["session_id"]
        statusline.run(json.dumps(doc))
        self.assertIsNone(json.loads(self.file.read_text(encoding="utf-8"))["session_id"])

    def test_without_rate_limits_file_untouched(self):
        doc = {k: v for k, v in FULL.items() if k != "rate_limits"}
        line = statusline.run(json.dumps(doc))
        self.assertEqual(line, "Opus · proj")
        self.assertFalse(self.file.exists())
        self.file.parent.mkdir(parents=True)
        self.file.write_text("old", encoding="utf-8")
        statusline.run(json.dumps(doc))
        self.assertEqual(self.file.read_text(encoding="utf-8"), "old")

    def test_partial_limits_do_not_write(self):
        doc = dict(FULL, rate_limits={"five_hour": FULL["rate_limits"]["five_hour"]})
        line = statusline.run(json.dumps(doc))
        self.assertIn("session 42%", plain(line))
        self.assertNotIn("week", line)
        self.assertFalse(self.file.exists())

    def test_context_share(self):
        doc = dict(FULL, context_window={"used_percentage": 37.4})
        self.assertIn("Opus · proj │ ctx 37% │ session 42%", plain(statusline.run(json.dumps(doc))))
        derived = dict(FULL, context_window={
            "context_window_size": 200000,
            "current_usage": {"input_tokens": 1000, "cache_creation_input_tokens": 9000,
                              "cache_read_input_tokens": 40000, "output_tokens": 5}})
        self.assertIn("ctx 25%", plain(statusline.run(json.dumps(derived))))
        for cw in (None, {}, {"used_percentage": None}, {"context_window_size": 0, "current_usage": {}}):
            self.assertNotIn("ctx", statusline.run(json.dumps(dict(FULL, context_window=cw))))

    def test_color_thresholds(self):
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        with mock.patch.dict(os.environ, env, clear=True):
            for pct, c in ((0, G), (59, G), (59.4, G), (59.6, Y), (60, Y), (85, Y),
                           (85.4, Y), (85.6, R), (86, R), (100, R)):
                self.assertEqual(statusline.paint(pct), f"{c}{round(pct)}%[0m", pct)

    def test_no_color(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertEqual(statusline.paint(70), "70%")
            doc = dict(FULL, context_window={"used_percentage": 90})
            self.assertNotIn("", statusline.run(json.dumps(doc)))
        with mock.patch.dict(os.environ, {"NO_COLOR": ""}):
            self.assertIn("", statusline.paint(70))

    def test_countdown(self):
        for left, want in ((-500, "0m"), (0, "0m"), (59, "0m"), (59 * 60 + 59, "59m"),
                           (3600, "1h 0m"), (6000, "1h 40m"), (7200, "2h 0m"),
                           (86399, "23h 59m"), (86400, "1d 0h"),
                           (4 * 86400 + 16 * 3600, "4d 16h")):
            self.assertEqual(statusline.countdown(1000 + left, 1000), want, left)

    def test_spec_line(self):
        now = 1_800_000_000
        doc = {"model": {"display_name": "Opus"}, "workspace": {"current_dir": "/a/skillz_lab"},
               "context_window": {"used_percentage": 37},
               "rate_limits": {"five_hour": {"used_percentage": 65, "resets_at": now + 6000},
                               "seven_day": {"used_percentage": 14,
                                             "resets_at": now + 4 * 86400 + 16 * 3600}}}
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        with mock.patch.dict(os.environ, env, clear=True):
            line = statusline.format_line(doc, now)
        self.assertEqual(plain(line), "Opus · skillz_lab │ ctx 37% │ session 65% ⟳ 1h 40m │ week 14% ⟳ 4d 16h")
        self.assertIn(f"ctx {G}37%", line)
        self.assertIn(f"session {Y}65%", line)
        self.assertIn(f"week {G}14%", line)

    def test_file_keys_unchanged(self):
        statusline.run(json.dumps(FULL))
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["schema", "updated_at", "session_id", "five_hour", "seven_day"])

    def test_malformed_never_raises(self):
        for raw in ("", "not json", "[1]", "null", '{"rate_limits": 5}',
                    '{"model": 3, "workspace": []}', '{"context_window": 7}',
                    '{"rate_limits": {"five_hour": {"used_percentage": "x"}}}'):
            self.assertIsInstance(statusline.run(raw), str, raw)
        self.assertFalse(self.file.exists())

    def test_unwritable_dir_still_prints(self):
        with mock.patch.object(statusline, "write_limits", side_effect=OSError):
            self.assertIn("session 42%", plain(statusline.run(json.dumps(FULL))))

    def test_entry_point_process(self):
        r = subprocess.run([sys.executable, str(HERE / "statusline.py")],
                           input=json.dumps(FULL).encode(), capture_output=True,
                           env={**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name})
        self.assertEqual(r.returncode, 0)
        self.assertIn("session 42%", plain(r.stdout.decode("utf-8")))
        self.assertTrue(self.file.exists())
        r = subprocess.run([sys.executable, str(HERE / "statusline.py")],
                           input=b"\xff\xfe garbage", capture_output=True)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.strip())

    def test_version_files_match(self):
        meta = json.loads((HERE / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["version"], (HERE / "VERSION").read_text().strip())


if __name__ == "__main__":
    unittest.main()
