# skillz

Two [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills) that work as a suite: break work down into self-contained tasks, then run them one at a time.

| Skill | Command | Description |
|---|---|---|
| [`task-breakdown`](task-breakdown/SKILL.md) | `/task-breakdown [plan \| id \| notes \| checks]` | One file per task in a staged `tasks/` folder pipeline (to-grill, design-gate, ready, real-check, to-be-tested, done), with built-in grilling, brain-dump sorting and a pass over pending manual checks. Folders, moves and the `TASKS.md` index are handled by `tasks.py` (zero tokens). |
| [`task-loop`](task-loop/SKILL.md) | `/task-loop [n]` | Runs the tasks in `tasks/03_ready` one at a time, each in a fresh subagent using the repo's `implementer` profile (created on first run from `implementer-template.md`), and verifies each task at zero token cost: commit, test suite, `tasks.py check`. Requires `task-breakdown`. |

Both skills must be installed together: `task-loop` calls `~/.claude/skills/task-breakdown/tasks.py`. Only `python3` (stdlib) is needed.

## Install with the `skillz` CLI

`./skillz` is a stdlib-only Python 3 script that symlinks each skill directory into `~/.claude/skills/`, so the scripts a skill ships with (`tasks.py`, `subagent_usage.py`) arrive together with its `SKILL.md`.

```sh
git clone https://github.com/lod0it/skillz.git && cd skillz
./skillz status                     # show what is installed, and any conflicts
./skillz install                    # interactive: choose which skills to install
./skillz install --skills task-breakdown,task-loop
./skillz install --dry-run          # print the plan without changing anything
./skillz install --force            # replace conflicting existing entries
./skillz uninstall                  # revert exactly what the CLI installed
```

- Selectors are interactive when omitted; `--skills LIST` takes comma-separated names.
- Everything the CLI changes is recorded in `~/.claude/skillz-state.json`, so `uninstall` reverts exactly that.
- Skills are discovered from the directory layout (`<name>/SKILL.md`), so no CLI change is needed when one is added.
- The `--plugins` and `--overrides` options of the CLI apply to the full collection and do nothing here.

Without the CLI, link manually:

```sh
ln -s "$PWD/task-breakdown" ~/.claude/skills/task-breakdown
ln -s "$PWD/task-loop" ~/.claude/skills/task-loop
```

## Tests

```sh
cd task-breakdown && python3 -m unittest test_tasks
```
