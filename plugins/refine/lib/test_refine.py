import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refine


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = refine.main(argv)
    return code, out.getvalue(), err.getvalue()


class PluginVersionTest(unittest.TestCase):
    def test_version_file_matches_the_manifest(self):
        plugin = Path(__file__).resolve().parents[1]
        manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual((plugin / "VERSION").read_text(encoding="utf-8").strip(), manifest["version"])


class DispatcherTest(unittest.TestCase):
    def test_version(self):
        code, out, _ = run(["--version"])
        self.assertEqual((code, out.strip()), (0, refine.version()))

    def test_no_args_prints_usage_and_exits_2(self):
        code, out, _ = run([])
        self.assertEqual(code, 2)
        self.assertIn("usage: refine", out)

    def test_unknown_command(self):
        code, _, err = run(["nope"])
        self.assertEqual(code, 2)
        self.assertIn("unknown command", err)

    def test_missing_module_is_not_implemented(self):
        saved = dict(refine.COMMANDS)
        refine.COMMANDS["golden"] = "no_such_module_xyz"
        try:
            code, _, err = run(["golden"])
        finally:
            refine.COMMANDS.clear()
            refine.COMMANDS.update(saved)
        self.assertEqual(code, 2)
        self.assertIn("golden: not implemented yet", err)

    def test_routes_to_a_module_main(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "stub_refine_mod.py").write_text(
                "def main(argv):\n    print('stub', argv)\n    return 3\n", encoding="utf-8")
            sys.path.insert(0, d)
            saved = dict(refine.COMMANDS)
            refine.COMMANDS["measure"] = "stub_refine_mod"
            try:
                code, out, _ = run(["measure", "a", "b"])
            finally:
                refine.COMMANDS.clear()
                refine.COMMANDS.update(saved)
                sys.path.remove(d)
                sys.modules.pop("stub_refine_mod", None)
        self.assertEqual(code, 3)
        self.assertIn("stub ['a', 'b']", out)


if __name__ == "__main__":
    unittest.main()
