# skillz

My [Claude Code](https://docs.claude.com/en/docs/claude-code) skills, versioned in one repo that is also a plugin marketplace.

## Plugins

### `taskflow`

Three skills that work as a suite: break work down into self-contained tasks, run them one at a time, and ask what to do next.

| Skill | Command | Description |
|---|---|---|
| [`break-it-down`](plugins/taskflow/skills/break-it-down/SKILL.md) | `/taskflow:break-it-down [plan \| id \| notes \| checks]` | One file per task in a staged `tasks/` folder pipeline (to-grill, design-gate, ready, real-check, to-be-tested, done), with built-in grilling, design gate rounds (approved frames exported as the images the Loop builds against), brain-dump sorting and a pass over the few verifications the Loop hands to you. Folders, moves and the `TASKS.md` index are handled by `taskflow` (zero tokens). |
| [`loop-it`](plugins/taskflow/skills/loop-it/SKILL.md) | `/taskflow:loop-it [n \| ids \| verify]` | Runs unattended. Per task: a fresh `implementer` subagent writes the code, zero-token checks (commit, test suite, `taskflow check`), then a fresh `verifier` subagent that did not write it runs the product (headless browser, fakes) against the acceptance criteria and the approved design images, and either closes the task or files a `bug` task the Loop picks next (from the third attempt it goes to grilling). Every failure becomes a rule in `tasks/LESSONS.md` that the next subagents read; changes to the process itself are proposed in the closing summary, never applied. Profiles are created on first run from `implementer-template.md` and `verifier-template.md`. Also started from the `now-what` menu. |
| [`now-what`](plugins/taskflow/skills/now-what/SKILL.md) | `/taskflow:now-what [focus]` | Shows the board (below), checks the open grills against the ready work, recommends an order, then offers the next actions as a menu and starts the one you pick. |

The plugin also ships the `taskflow` command (`plugins/taskflow/bin/`, on the Bash tool's `PATH` while the plugin is enabled): the stable entry point for `tasks.py`, which `TASKS.md` and the `implementer` profile name as the Tool. Only `python3` (stdlib) is needed.

`taskflow exclusive "<command>"` runs a command under a repo-wide lock shared by every worktree: the Loop runs every suite, verification and real run through it, so two never overlap and a loaded CPU or GPU does not fail tests that pass alone. It waits up to 9 minutes (`--wait`), exits 75 if the lock stays busy, and breaks a lock its holder stopped refreshing.

`taskflow board` draws the active tasks as waves in the terminal: `NOW` is what can move at once (`●` the Loop, `◆` you, `◇` a grill), `AFTER n` what follows, with what each task waits for (`←`) and how many it releases (`▶n`), plus the Loop command for the disjoint tasks, the bottleneck and the chains held by the backlog. Run it from a shell, or inside Claude Code as `! taskflow board`; `--plain` drops the colours.

`taskflow board -i` is the same board, interactive: run it in a separate terminal or tmux pane, not inside Claude Code (the Bash tool has no keyboard; without a terminal it exits with code 2). `↑↓←→` move between tasks and waves (held tasks are the last column, `HELD`); the selected task's chain is highlighted and the rest dimmed, and a box under the board shows its Who, Files, what it waits for and what it releases. `⏎` opens the task file in `$EDITOR` (default `vi`); `m` moves the task (or the selection) to a stage through `taskflow move`, with an optional Status note; `space` selects several tasks, `esc` clears the selection; `l` launches the Loop on them; `q` quits. The board reloads by itself when files under `tasks/` change, so a running Loop shows live. Tip: inside tmux, `l` opens a new window running `claude "/taskflow:loop-it <ids>"`; outside tmux it copies that command with `pbcopy` for you to paste.

### `residency`

A terminal command to see and trim what Claude Code keeps resident in context. It ships no skills, so it adds 0 resident tokens, and it does its work without calling the model. `./skillz install --plugins residency` links it into `~/.local/bin`, so `residency` runs from any terminal. `./skillz uninstall` removes the link.

Run it in a separate terminal or tmux pane, from inside a project:

```sh
residency                  # curses screen for the project of the current directory
residency --plain          # the same content printed once (also used when piped)
residency --project DIR    # another project
```

The screen shows the resident total of the latest `/context` (NOW), the total after the changes you toggle (AFTER) as stacked bars (core, skills, mcp, memory/CLAUDE.md), and a tree of categories and items. Each number carries its origin: `=` measured, `~` estimated, `?` unknown. Items show their state, the scope it comes from (`U` user, `P` project, `L` local; on a toggled item, the scope `w` writes to) and how often they were used, here and in all projects.

| Key | Action |
|---|---|
| `↑` `↓` | move (also `j` `k`, PgUp/PgDn, Home/End) |
| `⏎` | expand or collapse a category |
| `space` | next state of the item (skills: on, name-only, user-invocable-only, off; tools and MCP: deny; plugins: off); its delta is measured in the background |
| `s` | scope the item is written to (user, project, local) |
| `o` | sort by cost or by cost × unused |
| `w` | show the diff of the settings files, confirm, back each file up as `<file>.bak-<time>`, write, record the prediction |
| `M` | measure every item in the background |
| `q` | quit (asks first when toggles are not written) |

Deltas come from headless `claude -p "/context"` runs, which cost 0 tokens and write no transcript; they are cached in `~/.claude/residency-cache.json`. Plugin skills cannot be switched one by one: toggle their plugin.

**Refresh for free.** The totals come from the last interactive `/context` in the project's transcripts. After a write the screen says the snapshot is stale: run `claude`, type `/context`, then `/exit`. Neither command reaches the model, so it costs 0 tokens; `residency` then shows the new totals and `last change  predicted … actual … error …`.

## Install

```
/plugin marketplace add lod0it/skillz
/plugin install taskflow@skillz
/plugin install residency@skillz
```

Update with `/plugin update taskflow@skillz`. On every release bump `plugins/taskflow/VERSION` and `version` in `plugins/taskflow/.claude-plugin/plugin.json` together (a test fails when they differ): the manifest version pins what users get.

A project set up before the plugin names the old Tool path: `taskflow migrate-tool` rewrites it in `TASKS.md` and `.claude/agents/implementer.md` (`taskflow check` reports `OLD-TOOL` until then). The same command also renames the commands of taskflow before 0.5.0 (`/taskflow:task-breakdown`, `/taskflow:task-loop`) to `/taskflow:break-it-down` and `/taskflow:loop-it`.

### With the `skillz` CLI

`./skillz` wraps the same commands (stdlib-only Python 3): it registers this repo as the `skillz` marketplace and runs `claude plugin install` for you, and can also symlink standalone skills (top-level `<name>/SKILL.md`) and merge `skill-overrides.json`.

```sh
./skillz status
./skillz install                      # interactive
./skillz install --plugins taskflow
./skillz install --plugins residency   # also links ~/.local/bin/residency
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
cd plugins/taskflow/skills/break-it-down && python3 -m unittest test_tasks
```
