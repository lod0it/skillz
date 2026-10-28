import json
import os
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
        self.assertIn("session 42% · resets ", line)
        self.assertIn("week 18% · resets ", line)
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
        self.assertIn("session 42%", line)
        self.assertNotIn("week", line)
        self.assertFalse(self.file.exists())

    def test_malformed_never_raises(self):
        for raw in ("", "not json", "[1]", "null", '{"rate_limits": 5}',
                    '{"model": 3, "workspace": []}',
                    '{"rate_limits": {"five_hour": {"used_percentage": "x"}}}'):
            self.assertIsInstance(statusline.run(raw), str, raw)
        self.assertFalse(self.file.exists())

    def test_unwritable_dir_still_prints(self):
        with mock.patch.object(statusline, "write_limits", side_effect=OSError):
            self.assertIn("session 42%", statusline.run(json.dumps(FULL)))

    def test_entry_point_process(self):
        r = subprocess.run([sys.executable, str(HERE / "statusline.py")],
                           input=json.dumps(FULL).encode(), capture_output=True,
                           env={**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name})
        self.assertEqual(r.returncode, 0)
        self.assertIn("session 42%", r.stdout.decode("utf-8"))
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
