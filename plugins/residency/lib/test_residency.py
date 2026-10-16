import json
import subprocess
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
BIN = PLUGIN / "bin" / "residency"


class ScaffoldTest(unittest.TestCase):
    def test_version_matches_manifest(self):
        v = (PLUGIN / "VERSION").read_text().strip()
        m = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(v, m["version"])

    def test_version_output(self):
        r = subprocess.run([str(BIN), "--version"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), (PLUGIN / "VERSION").read_text().strip())

    def test_no_args(self):
        r = subprocess.run([str(BIN)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "not implemented yet")

    def test_runs_through_symlink(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "residency")
            os.symlink(BIN, link)
            r = subprocess.run([link, "--version"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)

    def test_no_skills(self):
        self.assertFalse((PLUGIN / "skills").exists())


if __name__ == "__main__":
    unittest.main()
