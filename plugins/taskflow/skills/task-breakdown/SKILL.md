---
name: task-breakdown
description: Turns a plan document, an undecided task or raw notes into self-contained task files in a staged `tasks/` pipeline (backlog, to-grill, design-gate, ready, real-check, to-be-tested, done) with a generated index. Use when the user runs /taskflow:task-breakdown, asks to plan, grill or split a task, to sort their notes into tasks, or to go through the pending manual checks.
argument-hint: "[plan-doc path | task id | notes | checks]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(taskflow *)
---

This skill runs inline in the current session — deliberately **not**
`context: fork` / no cheap-model delegation. Choosing task boundaries,
dependencies and the stage of a task is judgement about the domain, and
grilling needs the user's answers in this conversation. Everything mechanical
(moving files, Status marks, the index, consistency) belongs to the Tool,
which costs zero tokens:

```
taskflow <command>
```

`check` · `migrate-tool` · `init` · `status` · `next` · `next-id` · `move <id> <stage> [--note TEXT] [--rejected]` ·
`set <id> <field> <value>` · `checks` · `adopt <path> <stage>` · `index`

The task files are the single source of truth: a task's stage is the folder
it sits in, its metadata is the header under its title. The index in
`TASKS.md` is generated, so change a task through its file or the Tool and
let the Tool rewrite the index.

## 1. Preflight (every run)

Run `check` and act on what it prints:

- **`tasks/ is missing` or a stage folder is missing** → run `init` and tell
  the user what it created. A `TASKS.md` created from the template has two
  sections to fill now, `Task system` and `Conventions`: take them from the
  repo's `CLAUDE.md`, README and layout, and ask the user only what the repo
  cannot tell you.
- **`LEGACY` lines, or a `TASKS.md` that holds task bodies** → follow
  [migrate.md](migrate.md) before any branch.
- **`OLD-TOOL` lines** → run `migrate-tool`, tell the user which files it
  changed, then `check` again. The full migration of [migrate.md](migrate.md)
  is not needed.
- **Any other error** → fix the mechanical ones (`index`, `move <id> <its
  stage>`, a header field with `set`) and report the rest to the user.

Done when `check` prints `0 errors`, or every remaining error is in front of
the user.

## 2. Take the branch the argument names

| Argument | Branch |
|---|---|
| none | Run `status` and `next`, report them in a few lines, ask which branch the user wants. |
| a path to an existing document | [plan.md](plan.md): a plan becomes tasks. |
| a task id (`94`, `70b`) | [split.md](split.md): grill it if its decisions are open, then make it ready or split it into children. |
| `notes`, or a raw idea in the argument or the conversation | [notes.md](notes.md): the inbox is sorted into tasks. |
| `checks`, or the user reports how a manual check went | [checks.md](checks.md): one pass over every pending Manual check. |

Every branch that writes or rewrites a task file follows
[task-format.md](task-format.md).

## 3. Close

Run `check` until it prints `0 errors`, then `next`. Report: each task
written or moved (id, title, stage), what stayed where it was and why, and
every warning `check` printed. When `next` says several tasks fit the Loop,
propose the Loop as the way to run them. Leave committing to the user.
