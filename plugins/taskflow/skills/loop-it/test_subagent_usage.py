import json
import tempfile
import unittest
from pathlib import Path

import subagent_usage


def write_agent(folder, agent_id, role, prompt):
    sub = folder / "session" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    entry = {"type": "user", "message": {"content": prompt}}
    (sub / f"agent-{agent_id}.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    (sub / f"agent-{agent_id}.meta.json").write_text(json.dumps({"agentType": role}), encoding="utf-8")


class IdsTest(unittest.TestCase):
    def run_ids(self, folder, *extra):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = subagent_usage.main(["--project-dir", str(folder), "--ids", *extra])
        return code, out.getvalue().splitlines()

    def test_task_filter_lists_only_that_tasks_agents(self):
        with tempfile.TemporaryDirectory() as h:
            folder = Path(h)
            write_agent(folder, "a1", "implementer", "Implement Task 1g: `tasks/03_ready/1g.md`")
            write_agent(folder, "a2", "verifier", "Verify Task 1g: `tasks/05/1g.md`")
            write_agent(folder, "a3", "verifier", "Verify Task 1f: `tasks/05/1f.md`")
            code, lines = self.run_ids(folder, "--task", "1g")
            self.assertEqual(code, 0)
            self.assertEqual([line.split()[0] for line in lines], ["a1", "a2"])
            self.assertEqual(lines[0].split()[1], "implementer")

    def test_task_id_is_not_a_prefix_match(self):
        with tempfile.TemporaryDirectory() as h:
            folder = Path(h)
            write_agent(folder, "a1", "verifier", "Verify Task 1g2: x")
            code, lines = self.run_ids(folder, "--task", "1g")
            self.assertEqual(code, 1)

    def test_no_task_filter_lists_the_last_n(self):
        with tempfile.TemporaryDirectory() as h:
            folder = Path(h)
            for i in range(3):
                write_agent(folder, f"a{i}", "verifier", f"Verify Task {i}: x")
            code, lines = self.run_ids(folder, "--last", "2")
            self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
