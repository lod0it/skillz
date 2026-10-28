import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import version_check

SKILL = "/x/plugins/cache/skillz/taskflow/0.9.2/skills/loop-it"


class VersionCheckTest(unittest.TestCase):
    def run_check(self, installed, skill=SKILL, write=True):
        with tempfile.TemporaryDirectory() as h:
            if write:
                p = Path(h) / ".claude" / "plugins"
                p.mkdir(parents=True)
                data = {"plugins": {"taskflow@skillz": [{"version": installed}]}}
                if installed == "NOKEY":
                    data = {"plugins": {}}
                (p / "installed_plugins.json").write_text(json.dumps(data), encoding="utf-8")
            with mock.patch.object(Path, "home", return_value=Path(h)):
                return version_check.check(skill)

    def test_same(self):
        self.assertEqual(self.run_check("0.9.2"), "ok 0.9.2")

    def test_installed_newer(self):
        self.assertEqual(self.run_check("0.9.3"), "restart 0.9.2 0.9.3")

    def test_numeric_not_text(self):
        self.assertEqual(self.run_check("0.10.0"), "restart 0.9.2 0.10.0")

    def test_installed_older(self):
        self.assertEqual(self.run_check("0.9.1"), "ok 0.9.2")

    def test_missing_file(self):
        self.assertEqual(self.run_check("", write=False), "unknown")

    def test_missing_key(self):
        self.assertEqual(self.run_check("NOKEY"), "unknown")

    def test_path_without_version(self):
        self.assertEqual(self.run_check("0.9.3", skill="/src/plugins/taskflow/skills/loop-it"), "unknown")


if __name__ == "__main__":
    unittest.main()
