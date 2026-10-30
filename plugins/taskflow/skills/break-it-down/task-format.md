# Task format

How to write a task file, where it goes, and how to cut work into tasks. The
template is in the repo's `TASKS.md` ("Task template"); the repo's own values
(Who, Types, Design gate, Loop) are in its "Task system" section.

Write tasks in the language of the repo's docs, whatever language the notes
or the conversation are in, in the style of [writing-style.md](writing-style.md)
(ASD-STE100: short sentences, active voice, imperative steps, one term per
thing).

## Stage: what does this task need next?

| The task needs | Folder |
|---|---|
| nothing yet: the user put it on hold, out of the Loop (only the user decides this; `move <id> backlog`, any stage in and out) | `00_backlog` |
| a decision only the user can make | `01_to-grill` |
| a design the user approves before code (only when Task system declares a Design gate) | `02_design-gate` |
| nothing but implementing | `03_ready` |
| something only the user has or pays for: paid tokens, a second machine, an account, hardware this machine lacks, a person's judgement (it is a check, planned in advance). What runs free on this machine (a local server, a local GPU, a download from a public mirror) is not a real check: it is ready work the Loop runs | `04_real-check` |

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
- **Who:** `interactive` only when the user must be in the session:
  grilling, design approval, a real check. Look and feel is settled at the
  design gate, so a UI task is not interactive: the Loop's verifier compares
  it with the approved design. Otherwise the model that fits the difficulty.
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
  to look for in each; the traps you found while reading the code. A task
  that changes what the user sees cites its approved design images by path
  (under `Design refs`): implementer and verifier both work from them.
- **Steps:** numbered, each one a change the session can finish and verify.
- **Acceptance criteria:** checkable: a command that passes, an output that
  exists, a behaviour that can be observed.
- **Verification:** what the Loop's verifier must see with the product
  running, beyond what the suite proves: per acceptance criterion the state
  to reach and the result to observe, the design images to compare. The
  implementer rewrites it at closing, the verifier turns it into evidence.
  Never steps for the user: what only the user could check is a real check
  task of its own.
- **Outcome:** `(to fill in)`. Decisions of a grilling and results of the
  work land here.
- **When done:** the template's line, unchanged.

## Cutting work into tasks

1. **One context window, one verifiable deliverable** per task. A subagent
   that runs past 150k of context is a rare event, and when it happens the
   cut was wrong: size the work while you grill, not after. More than 8
   `Files`, or more than 3 distinct areas (a screen, a service, the IPC
   layer, the tests, the docs), is too much for one task: split it now, along
   seams that keep each piece verifiable alone (data and service first, the
   UI on top) and its `Files` disjoint from the others where possible. Never
   write an oversized task meaning to cut it later.
2. **Design first for UI:** when the repo declares a Design gate and the
   work changes what the user sees, a design task comes first and the UI
   task depends on it.
3. **Backend work starts without the design:** it depends on the decisions,
   never on the design task.
4. **Real resources get their own task:** anything that spends paid tokens
   or needs what only the user has (another machine, an account, missing
   hardware) is a `04_real-check` task at the end of the chain, so every code
   task can finish, and be verified, unattended.
5. **Docs travel with the behaviour:** the task that changes a behaviour
   updates its docs and vocabulary; a hard-to-reverse decision gets its own
   decision-record task at the head of the chain.
6. **`Depends on`, `Who` and `Files` on every task** (`Files` may be `—`
   only in `01_to-grill`).
7. **Every task ends with `## Verification`** (`## Manual check` in tasks
   written before it, still accepted).
8. **The parent closes at the split:** a task that was grilled and split has
   delivered its decisions. `move <id> done --note "closed <date>: decisions
   in Outcome, split into <id>a–<id>f"`, and its children cite its Outcome
   by id.
9. **Learn from the Loop:** before writing tasks, read `tasks/LESSONS.md`;
   a lesson marked `tasks` is a rule for how you cut and write them.
10. **Not everything is a task:** a change with no open decision (the way
    is obvious, nothing to design, one area, one or two files, nothing new to
    check by eye) costs more as a task (file, implementer, verifier) than as
    the change itself. Do not write it: offer the user to do it right away,
    inline or by handing it to the Loop, and write a task only when they
    decline. Say so once per round, listing the candidates, so the pipeline
    does not fill with tiny tasks.
