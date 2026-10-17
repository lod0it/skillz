# Task format

How to write a task file, where it goes, and how to cut work into tasks. The
template is in the repo's `TASKS.md` ("Task template"); the repo's own values
(Who, Types, Design gate, Loop) are in its "Task system" section.

Write tasks in the language of the repo's docs, whatever language the notes
or the conversation are in.

## Stage: what does this task need next?

| The task needs | Folder |
|---|---|
| nothing yet: the user put it on hold, out of the Loop (only the user decides this; `move <id> backlog`, any stage in and out) | `00_backlog` |
| a decision only the user can make | `01_to-grill` |
| a design the user approves before code (only when Task system declares a Design gate) | `02_design-gate` |
| nothing but implementing | `03_ready` |
| real resources: paid tokens, a second machine, an account, a download (it is a check, planned in advance) | `04_real-check` |

`05_to-be-tested` and `99_done` are reached only through `move`, when work
closes.

A **to-grill stub** is short: Goal (what the user wants and why), Context
(what is known, the files and tasks to read), and under Steps the questions
the grilling has to settle. `Files` is `—` until the decisions exist.

## Header

- **Id and file:** a new top-level task takes the number `next-id` prints;
  the children of Task N are `Na`, `Nb`, … in dependency order. File:
  `tasks/<folder>/<id>_<slug>.md`, slug short, lower case, underscores.
- **Status:** `[ ]` plus a few words; `move` owns the mark afterwards.
- **Type:** one of the Types.
- **Depends on:** the ids this task needs first, because of order **or
  because both edit the same file**; a note goes in brackets
  (`Task 54 (same file)`). `—` when free. This line is parsed: ids and
  bracketed notes only.
- **Who:** `interactive` when the user must be in the session (grilling,
  design approval, real checks, a judgement about look and feel); otherwise
  the model that fits the difficulty.
- **Files:** every file the task will edit, tests and docs included, each in
  backticks. Read the code to find them: `check` warns when two tasks that
  could start now collide on a file, and `next` groups the ones that do not. Work outside the repo is said in
  words (`design file only`).

## Body

The reader is a fresh session with no memory of this conversation. Each
section gives it something it cannot get by looking:

- **Goal:** one paragraph, the deliverable in concrete terms.
- **Context:** the decisions it implements, by task id and decision number
  ("Outcome of Task 93: Q4, Q9"); the files and functions to read, with what
  to look for in each; the traps you found while reading the code.
- **Steps:** numbered, each one a change the session can finish and verify.
- **Acceptance criteria:** checkable: a command that passes, an output that
  exists, a behaviour that can be observed.
- **Manual check:** what the user will have to try by hand because tests
  cannot prove it, as far as it can be foreseen (the implementing session
  rewrites it at closing); `Nothing to check by hand.` when tests prove
  everything.
- **Outcome:** `(to fill in)`. Decisions of a grilling and results of the
  work land here.
- **When done:** the template's line, unchanged.

## Cutting work into tasks

1. **One context window, one verifiable deliverable** per task.
2. **Design first for UI:** when the repo declares a Design gate and the
   work changes what the user sees, a design task comes first and the UI
   task depends on it.
3. **Backend work starts without the design:** it depends on the decisions,
   never on the design task.
4. **Real resources get their own task:** anything that spends paid tokens
   or needs hardware or accounts is a `04_real-check` task at the end of the
   chain, so every code task can finish unattended.
5. **Docs travel with the behaviour:** the task that changes a behaviour
   updates its docs and vocabulary; a hard-to-reverse decision gets its own
   decision-record task at the head of the chain.
6. **`Depends on`, `Who` and `Files` on every task** (`Files` may be `—`
   only in `01_to-grill`).
7. **Every task ends with `## Manual check`.**
8. **The parent closes at the split:** a task that was grilled and split has
   delivered its decisions. `move <id> done --note "closed <date>: decisions
   in Outcome, split into <id>a–<id>f"`, and its children cite its Outcome
   by id.
