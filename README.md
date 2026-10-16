# skillz

My [Claude Code](https://docs.claude.com/en/docs/claude-code) skills, versioned in one repo that is also a plugin marketplace.

## Plugins

### `taskflow`

Three skills that work as a suite: break work down into self-contained tasks, run them one at a time, and ask what to do next.

| Skill | Command | Description |
|---|---|---|
| [`task-breakdown`](plugins/taskflow/skills/task-breakdown/SKILL.md) | `/taskflow:task-breakdown [plan \| id \| notes \| checks]` | One file per task in a staged `tasks/` folder pipeline (to-grill, design-gate, ready, real-check, to-be-tested, done), with built-in grilling, brain-dump sorting and a pass over pending manual checks. Folders, moves and the `TASKS.md` index are handled by `taskflow` (zero tokens). |
| [`task-loop`](plugins/taskflow/skills/task-loop/SKILL.md) | `/taskflow:task-loop [n]` | Runs the tasks in `tasks/03_ready` one at a time, each in a fresh subagent using the repo's `implementer` profile (created on first run from `implementer-template.md`), and verifies each task at zero token cost: commit, test suite, `taskflow check`. Also started from the `now-what` menu. |
| [`now-what`](plugins/taskflow/skills/now-what/SKILL.md) | `/taskflow:now-what [focus]` | Shows the board (below), checks the open grills against the ready work, recommends an order, then offers the next actions as a menu and starts the one you pick. |

The plugin also ships the `taskflow` command (`plugins/taskflow/bin/`, on the Bash tool's `PATH` while the plugin is enabled): the stable entry point for `tasks.py`, which `TASKS.md` and the `implementer` profile name as the Tool. Only `python3` (stdlib) is needed.

`taskflow board` draws the active tasks as waves in the terminal: `NOW` is what can move at once (`●` the Loop, `◆` you, `◇` a grill), `AFTER n` what follows, with what each task waits for (`←`) and how many it releases (`▶n`), plus the Loop command for the disjoint tasks, the bottleneck and the chains held by the backlog. Run it from a shell, or inside Claude Code as `! taskflow board`; `--plain` drops the colours.

`taskflow board -i` is the same board, interactive: run it in a separate terminal or tmux pane, not inside Claude Code (the Bash tool has no keyboard; without a terminal it exits with code 2). `↑↓←→` move between tasks and waves (held tasks are the last column, `HELD`); the selected task's chain is highlighted and the rest dimmed, and a box under the board shows its Who, Files, what it waits for and what it releases. `⏎` opens the task file in `$EDITOR` (default `vi`); `m` moves the task (or the selection) to a stage through `taskflow move`, with an optional Status note; `space` selects several tasks, `esc` clears the selection; `l` launches the Loop on them; `q` quits. The board reloads by itself when files under `tasks/` change, so a running Loop shows live. Tip: inside tmux, `l` opens a new window running `claude "/taskflow:task-loop <ids>"`; outside tmux it copies that command with `pbcopy` for you to paste.

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
