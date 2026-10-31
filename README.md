# skillz

My [Claude Code](https://docs.claude.com/en/docs/claude-code) skills, versioned in one repo that is also a plugin marketplace.

## Plugins

### `taskflow`

Five skills that work as a suite: break work down into self-contained tasks, run them one at a time, ask what to do next, bring repos with an older layout up to date, and keep the resident context small.

| Skill | Command | Description |
|---|---|---|
| [`break-it-down`](plugins/taskflow/skills/break-it-down/SKILL.md) | `/taskflow:break-it-down [plan \| id \| notes \| checks]` | One file per task in a staged `tasks/` folder pipeline (to-grill, design-gate, ready, real-check, to-be-tested, done), with built-in grilling, design gate rounds (approved frames exported as the images the Loop builds against), brain-dump sorting and a pass over the few verifications the Loop hands to you. Folders, moves and the `TASKS.md` index are handled by `taskflow` (zero tokens). |
| [`loop-it`](plugins/taskflow/skills/loop-it/SKILL.md) | `/taskflow:loop-it [n \| ids \| verify]` | Runs unattended. Per task: a fresh `implementer` subagent writes the code, zero-token checks (commit, test suite, `taskflow check`), then a fresh `verifier` subagent that did not write it runs the product (headless browser, fakes) against the acceptance criteria and the approved design images, and either closes the task or files a `bug` task the Loop picks next (from the third attempt it goes to grilling). Every failure becomes a rule in `tasks/LESSONS.md` that the next subagents read, under `Project` or, when it holds in any repo, `General`. Before each task the Loop reads the approved General Rules live from the sibling `agent-rules` repo (`pull --ff-only`, line 1 of each rule) and pastes them into the implementer and verifier prompts; a General lesson is written project-agnostic and is only a proposal to the user for those rules, never applied by the Loop. Changes to the process itself are proposed in the closing summary, never applied. After each verified task the Loop pushes the current branch (plain `git push`, never forced, only with an upstream, from the main checkout after the merge in the parallel mode); a rejected, offline or upstream-less push is a line in the closing summary, never a stop. No subagent outlives its task: once a task has its verdict, the Loop stops (`TaskStop`) every subagent of it still alive and removes its worktree. Before each task (each batch in the parallel mode) the Loop compares the taskflow version it loaded with the installed one (`version_check.py`, zero tokens); when a newer one is installed it starts nothing and ends with `taskflow updated <loaded> → <installed>: restart the session and run /taskflow:loop-it again`. Profiles are created on first run from `implementer-template.md` and `verifier-template.md`. Also started from the `now-what` menu. |
| [`now-what`](plugins/taskflow/skills/now-what/SKILL.md) | `/taskflow:now-what [focus]` | Shows the board (below), checks the open grills against the ready work, recommends an order, then offers the next actions as a menu and starts the one you pick. |
| [`free-my-context`](plugins/taskflow/skills/free-my-context/SKILL.md) | `/taskflow:free-my-context [tools \| mcp \| skills \| plugins]` | Guided trim of what Claude Code keeps resident in context. Lists the active built-in tools, MCP servers, skills and plugins, asks round by round what to switch off (`AskUserQuestion`, defaults from the calls counted in your transcripts), and writes only the project's `.claude/settings.local.json` after one confirmation, with a `.bak` copy. User-invocable only, so it costs 0 resident tokens; the counting and the merge are `free_my_context.py` (zero tokens). Core tools are never offered. Changes apply to new sessions. |
| [`upgrade-repos`](plugins/taskflow/skills/upgrade-repos/SKILL.md) | `/taskflow:upgrade-repos [folder]` | Brings taskflow repos with an older layout up to the installed version in one pass: `init`, `migrate-tool`, `check`, one local commit per repo (zero tokens, `upgrade_repos.py`), never a push; repos with uncommitted changes are skipped, pre-pipeline layouts (`LEGACY`) are pointed to the migrate branch of `break-it-down`. A `SessionStart` hook scans the session's repo, its children and its siblings and, when one is old, makes Claude offer the upgrade (upgrade, dry run, not now: a snoozed repo stays quiet until the next taskflow version). |

The plugin also ships the `taskflow` command (`plugins/taskflow/bin/`, on the Bash tool's `PATH` while the plugin is enabled): the stable entry point for `tasks.py`, which `TASKS.md` and the `implementer` profile name as the Tool. Only `python3` (stdlib) is needed.

`taskflow exclusive "<command>"` runs a command under a repo-wide lock shared by every worktree: the Loop runs every suite, verification and real run through it, so two never overlap and a loaded CPU or GPU does not fail tests that pass alone. It waits up to 9 minutes (`--wait`), exits 75 if the lock stays busy, and breaks a lock its holder stopped refreshing.

`taskflow board` draws the active tasks as waves in the terminal: `NOW` is what can move at once (`●` the Loop, `◆` you, `◇` a grill), `AFTER n` what follows, with what each task waits for (`←`) and how many it releases (`▶n`), plus the Loop command for the disjoint tasks, the bottleneck and the chains held by the backlog. Run it from a shell, or inside Claude Code as `! taskflow board`; `--plain` drops the colours. `status`, `board`, `next` and `checks` take `--json` for programs (one JSON document, `schema` 1).

`taskflow board -i` is the same board, interactive: run it in a separate terminal or tmux pane, not inside Claude Code (the Bash tool has no keyboard; without a terminal it exits with code 2). `↑↓←→` move between tasks and waves (held tasks are the last column, `HELD`); the selected task's chain is highlighted and the rest dimmed, and a box under the board shows its Who, Files, what it waits for and what it releases. `⏎` opens the task file in `$EDITOR` (default `vi`); `m` moves the task (or the selection) to a stage through `taskflow move`, with an optional Status note; `space` selects several tasks, `esc` clears the selection; `l` launches the Loop on them; `q` quits. The board reloads by itself when files under `tasks/` change, so a running Loop shows live. Tip: inside tmux, `l` opens a new window running `claude "/taskflow:loop-it <ids>"`; outside tmux it copies that command with `pbcopy` for you to paste.

**Upgrading old repos.** `upgrade_repos.py` (stdlib, zero tokens) finds the taskflow repos (`TASKS.md` with `## Task system`) in a folder, its children and its siblings, and sorts each one: `ok`; `auto` (old Tool paths, missing `tasks/LESSONS.md` or its sections, missing stage folders: `init` + `migrate-tool` fix it); `manual` (a pre-pipeline layout with `LEGACY` folders or files: the migrate branch of `/taskflow:break-it-down`). `scan [dir] [--json]` only reports; `apply <repo>... [--commit]` runs `init`, `migrate-tool` and `check` and, with `--commit`, makes one local commit per repo (`taskflow: upgrade to <version> ...`); it skips a repo with uncommitted changes and never pushes. A `SessionStart` hook runs `hint` at every session start: when an `auto` or `manual` repo is near, Claude is told to offer the upgrade (upgrade, dry run, not now) before anything else; `snooze` (the "not now" answer) keeps a repo quiet until the next taskflow version, in `~/.claude/taskflow/upgrade_snooze.json`. Tests: `cd plugins/taskflow/skills/upgrade-repos && python3 -m unittest`.

### `statusline`

The command Claude Code runs for its status line, zero tokens, no skills. It shows the git branch of the current directory, the share of the context window in use, and the Pro/Max usage of the 5-hour session and of the week with the time left to each reset. **24 styles** draw the same four values; you pick one (or several, with rules) and switch with one command.

```
Branch: main | CTX 37% | Session 65% ⟳ 1h 40m | Weekly 14% ⟳ 4d 16h      (the default style, plain)
```

#### Choose a style

```sh
statusline style list              # the 24 styles, * marks the one in use
statusline style preview all       # draw every style on sample data (or: preview tree)
statusline style set tree          # save your choice
statusline style next              # or prev, random: step through the styles
statusline style show              # which layer wins, and why
statusline style color gray        # grayscale mode (also: on, off)
```

Inside Claude Code type `! statusline style set tree`: the `!` runs it in your shell without using tokens (the plugin's `bin/` is on the PATH while it is enabled; after `./skillz install` the command is also in `~/.local/bin`). The line changes at the next answer. Add `--project` to `set`, `next`, `prev`, `random`, `fit` and `alert` to write the current project's file instead of your user config.

| Style | Look | Needs |
|---|---|---|
| `plain` | Branch: main | CTX 4% | Session 12% ⟳ 4h | Weekly 14% ⟳ 4d | - |
| `dim` | Faded labels, bold values | - |
| `segments` | Ten ▰▱ cells per metric | - |
| `solid` | Full block over light shade | - |
| `smooth` | Eighth-block edge on a tinted track (80 steps) | colors |
| `gradient` | Green to red hue along the bar | truecolor |
| `heat` | Cells turn yellow past 60, red past 85 | - |
| `dots` | Filled and hollow circles | - |
| `pie` | One ○◔◑◕● glyph per metric | - |
| `gauge` | One rising block per metric | - |
| `spark` | Last eight readings (history file) | - |
| `pace` | White ┃ marks how much of the window has passed | - |
| `lights` | Only a dot carries the color | - |
| `chips` | Gray label tile, colored value tile | colors |
| `brackets` | [main] [CTX 4%] [Session 12% ⟳ 4h] | - |
| `pills` | Rounded capsules | Nerd/Powerline font |
| `powerline` | Arrow-joined colored segments | Nerd/Powerline font |
| `emoji` | 🌿 main 🧠 4% ⏱ 12% 📅 14% | emoji |
| `symbols` | Monochrome symbols instead of emoji | - |
| `tree` | Four aligned lines with bars | - |
| `dash` | Two lines: branch and context, then the two limits | - |
| `circuit` | Boxes joined by lines in phosphor green | - |
| `whisper` | Everything dim except what needs attention | - |
| `inbar` | Label and value inside the bar | colors |

Every style prints the metrics it has: a missing session or weekly limit (before the first answer, other plans) is left out, never shown as zero. Styles marked "colors" fall back to `brackets` under `NO_COLOR`. `gradient` uses 24-bit color when `COLORTERM` says `truecolor` or `24bit`, plain ANSI otherwise. `powerline` and `pills` draw with glyphs of a Powerline or Nerd Font: without one you see boxes, so pick another style. Emoji width differs between terminals; `symbols` is the fixed-width alternative.

#### Where the choice lives

Strongest first; the first layer that names a valid style wins, an unknown name is skipped, the default is `plain`.

| Layer | Where | Set with |
|---|---|---|
| Environment | `STATUSLINE_STYLE=pie` (also under `env` in a `settings.json`) | by hand |
| Project | `<project>/.claude/statusline.json`: `{"style": "solid"}` | `statusline style set solid --project` |
| User | `~/.claude/statusline/config.json` (`CLAUDE_CONFIG_DIR` is honoured) | `statusline style set solid` |

Two optional rules sit on top of the chosen style, in the user or project file (the project value wins):

- **Alert:** `{"alert": {"at": 85, "style": "heat"}}` switches to `heat` when any value reaches 85 percent. Set with `statusline style alert 85 heat`; `alert off` removes it.
- **Fit:** `{"fit": ["pie", "whisper"]}` walks the list when the style is wider than the terminal and uses the first that fits (the last one, clipped, if none does). Set with `statusline style fit pie,whisper`; `fit off` removes it. The width comes from `"columns": 100` in the file, else the terminal, else `$COLUMNS`; when none is known the rule does nothing. Widths count emoji as two columns.

Order of the rules: layers, then alert, then fit. A broken or unreadable config file is ignored and the default style is drawn.

#### Colors, grayscale, none

```sh
statusline style color gray        # no hue: severity by brightness; also: on, off
statusline style preview all --gray   # try a mode without saving it (or --off)
```

- `on` (default): green, yellow and red like a traffic light.
- `gray`: no hue at all. Values go from gray to white to bold white as they grow, and a value above 85 is shown in reverse video; bars, tiles, `powerline` and `pills` use gray shades. Same text as `on`, so any style works.
- `off`: no escape sequence at all. Styles that need background colors (`smooth`, `chips`, `pills`, `powerline`, `inbar`) draw as `brackets`.

Strongest first: `NO_COLOR` set and not empty (always `off`), `STATUSLINE_COLOR=on|gray|off`, `"color"` in the project file, `"color"` in the user file. `statusline style color on` removes the key. `statusline style show` prints the mode in use.

#### Details

The percentages are bold and colored like a traffic light on the rounded number: green under 60, yellow 60 to 85, red above 85; with `NO_COLOR` set (not empty) no escape sequence is printed (see above for `gray` and `off`). The countdown reads `Nm` under an hour, `Hh Mm` under a day, `Dd Hh` from a day (`0m` once the reset has passed). `CTX` comes from `context_window.used_percentage` (or, without it, current usage over the window size). The `pace` style marks with a white `┃` how much of the 5-hour or 7-day window has already passed: fill left of it means you use less than time allows. The `spark` style shows the last eight readings; the plugin keeps them in `~/.claude/statusline/history.json` (a reading is added when it changes, the context history restarts with each session).

The plugin also saves the latest limits for other tools (the Agentic Control Plane app) to `~/.claude/statusline/rate_limits.json` (`CLAUDE_CONFIG_DIR` is honoured), written atomically; the file does not depend on the style:

```json
{"schema": 1, "updated_at": 1790000000, "session_id": "abc", "five_hour": {"used_percentage": 42, "resets_at": 1790000000}, "seven_day": {"used_percentage": 18, "resets_at": 1790400000}}
```

When stdin has no `rate_limits` the line is printed without limits and the file is not touched; any error prints a minimal line, never a traceback. The newest write wins when several terminals are open. It runs in the terminal CLI (also in VS Code's integrated terminal), not in the VS Code native panel. Stdlib Python 3 only. Tests: `cd plugins/statusline && python3 -m unittest discover`.

`./skillz install --plugins statusline` links `~/.local/bin/statusline` (on Windows the plugin's `bin/statusline.cmd` is used in place) and sets `statusLine` in `~/.claude/settings.json` after a backup (`settings.json.bak-<time>`). On Windows the command is written with forward slashes (`C:/Users/you/.../statusline.cmd`): Claude Code runs it through bash, which eats backslashes, so a `C:\Users\...` path ends in "command not found" and no line is shown. If you set `statusLine` by hand, use forward slashes too. A different `statusLine` already there is kept unless you pass `--force`; `./skillz uninstall --plugins statusline` removes it (or restores the previous one).

## Install

```
/plugin marketplace add lod0it/skillz
/plugin install taskflow@skillz
/plugin install statusline@skillz
```

Update with `/plugin update taskflow@skillz`. After a taskflow update, a session started near a repo with an older layout offers `/taskflow:upgrade-repos`. On every release bump `plugins/taskflow/VERSION` and `version` in `plugins/taskflow/.claude-plugin/plugin.json` together (a test fails when they differ): the manifest version pins what users get.

A project set up before the plugin names the old Tool path: `taskflow migrate-tool` rewrites it in `TASKS.md` and `.claude/agents/implementer.md` (`taskflow check` reports `OLD-TOOL` until then). The same command also renames the commands of taskflow before 0.5.0 (`/taskflow:task-breakdown`, `/taskflow:task-loop`) to `/taskflow:break-it-down` and `/taskflow:loop-it`.

### With the `skillz` CLI

`./skillz` wraps the same commands (stdlib-only Python 3): it registers this repo as the `skillz` marketplace and runs `claude plugin install` for you, and can also symlink standalone skills (top-level `<name>/SKILL.md`) and merge `skill-overrides.json`.

```sh
./skillz status
./skillz install                      # interactive
./skillz install --plugins taskflow
./skillz install --plugins statusline  # also sets statusLine in ~/.claude/settings.json
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
