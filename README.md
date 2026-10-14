# skillz

My [Claude Code](https://docs.claude.com/en/docs/claude-code) skills, versioned in one repo that is also a plugin marketplace.

## Plugins

### `taskflow`

Two skills that work as a suite: break work down into self-contained tasks, then run them one at a time.

| Skill | Command | Description |
|---|---|---|
| [`task-breakdown`](plugins/taskflow/skills/task-breakdown/SKILL.md) | `/taskflow:task-breakdown [plan \| id \| notes \| checks]` | One file per task in a staged `tasks/` folder pipeline (to-grill, design-gate, ready, real-check, to-be-tested, done), with built-in grilling, brain-dump sorting and a pass over pending manual checks. Folders, moves and the `TASKS.md` index are handled by `taskflow` (zero tokens). |
| [`task-loop`](plugins/taskflow/skills/task-loop/SKILL.md) | `/taskflow:task-loop [n]` | Runs the tasks in `tasks/03_ready` one at a time, each in a fresh subagent using the repo's `implementer` profile (created on first run from `implementer-template.md`), and verifies each task at zero token cost: commit, test suite, `taskflow check`. |

The plugin also ships the `taskflow` command (`plugins/taskflow/bin/`, on the Bash tool's `PATH` while the plugin is enabled): the stable entry point for `tasks.py`, which `TASKS.md` and the `implementer` profile name as the Tool. Only `python3` (stdlib) is needed.

## Install

```
/plugin marketplace add lod0it/skillz
/plugin install taskflow@skillz
```

Update with `/plugin update taskflow@skillz`. On every release bump `plugins/taskflow/VERSION` and `version` in `plugins/taskflow/.claude-plugin/plugin.json` together (a test fails when they differ): the manifest version pins what users get.

A project set up before the plugin names the old Tool path: `taskflow migrate-tool` rewrites it in `TASKS.md` and `.claude/agents/implementer.md` (`taskflow check` reports `OLD-TOOL` until then).

### With the `skillz` CLI

`./skillz` wraps the same commands (stdlib-only Python 3): it registers this repo as the `skillz` marketplace and runs `claude plugin install` for you, and can also symlink standalone skills (top-level `<name>/SKILL.md`) and merge `skill-overrides.json`.

```sh
./skillz status
./skillz install                      # interactive
./skillz install --plugins taskflow
./skillz uninstall
```

## Develop

```sh
claude --plugin-dir ./plugins/taskflow   # load from the working tree, no cache
claude plugin validate .
```

New plugins go under `plugins/<name>/` and get an entry in `.claude-plugin/marketplace.json`.

## Tests

```sh
cd plugins/taskflow/skills/task-breakdown && python3 -m unittest test_tasks
```
