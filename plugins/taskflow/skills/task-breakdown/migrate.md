# Branch: migrate an older layout

Reached from the preflight when `check` prints `LEGACY` lines or `TASKS.md`
holds task bodies. Propose, wait, then move: the user sees every change
before a file is touched.

## 1. Inventory

List every task file outside the six pipeline folders, every task written
inside `TASKS.md`, and every hand-written index table.

## 2. Propose the plan and wait

One table, a row per open task: current path → stage folder → new name, plus
the header fields it lacks (Type, Who, Files) with the value you propose.
The stage comes from "Stage" in [task-format.md](task-format.md); a task
whose code is done and only the user's check is missing goes to
`05_to-be-tested`. Closed tasks go to `99_done` exactly as they are: name,
header and body untouched. Say what becomes of `TASKS.md` and which other
files name the old paths (`Grep` the repo: docs, `CLAUDE.md`, skills).

Wait for the user's yes.

## 3. Execute

1. `init`, when stage folders are missing.
2. Preserve history first: copy any hand-written index table verbatim into
   `tasks/archive.md` under a dated heading; closed tasks that live only as
   bodies inside `TASKS.md` move there verbatim too.
3. `adopt <path> <stage>` for each file (it renames to `<id>_<slug>.md` and
   keeps the Status text). An open task that lives inside `TASKS.md` becomes
   its own file.
4. Bring every open header to the format: `set` the missing fields, rewrite
   `Depends on` as ids with notes in brackets, add `## Manual check` to
   tasks in `03_ready` (expected check) and `05_to-be-tested` (the concrete
   steps, from the Status line and Outcome).
5. Give `TASKS.md` the sections of
   `${CLAUDE_SKILL_DIR}/TASKS-TEMPLATE.md` (Task system, Pipeline, Workflow,
   Task template, the two index markers), keeping the repo's own Conventions
   and notes.
6. Fix the old paths found in step 2 of this file.
7. `index`, then `check`.

Done when `check` prints `0 errors` and no file in the repo names a folder
that no longer exists. Leave committing to the user.

## An `OLD-TOOL` error instead

`check` prints `OLD-TOOL` when `TASKS.md` or `.claude/agents/implementer.md`
still names the pre-plugin Tool (`python3 ~/.claude/skills/task-breakdown/tasks.py`)
or the un-namespaced commands (`/task-breakdown`, `/task-loop`). That is not a
layout migration: run `migrate-tool` (zero tokens, no proposal needed), then
`check`. Tell the user which files changed; leave committing to them.
