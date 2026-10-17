# Branch: a task id

Take one task from undecided to buildable: grill it if its decisions are
open, then either make it ready or split it into children.

## 1. Read before asking

Open the task (`tasks/*/<id>_*.md`) and everything its Context names: docs,
decision records, the Outcome of the tasks it cites, the code it will touch.
Every fact the repo can give you is yours to find; note the ones that
surprise you, they open the Outcome.

## 2. Grill, when decisions are open

Decisions are open when the task sits in `01_to-grill`, or its Outcome is
empty and its Steps still ask questions. Otherwise go to step 3 with the
Outcome it has.

Work in rounds. A round is every question whose prerequisites are already
settled, numbered across rounds (Q1, Q2, …), each with the options, your
recommended answer and the reason for it. Then wait for the answers; they
decide which questions the next round can ask.

Be blunt. Say what the plan gets wrong, what it duplicates, what it will
cost to maintain, and the obvious thing the user may have stopped seeing.
A recommendation that only agrees is worth nothing to them.

Done when no question is left open and the user confirms the shared
understanding.

## 3. Write the Outcome first

Before any other file changes, write the decisions into the task's
`## Outcome`: the date, the facts found in step 1, then one line per
decision (`- **Q4 Same Call.** <the decision and its reason>`). A session
that drops after this point has lost nothing.

## 4. One task or several

- **It fits one context window and has one deliverable:** rewrite this same
  file as a full task ([task-format.md](task-format.md)) and `move <id>` to
  the stage it now needs.
- **Otherwise split:** write the children per task-format.md, each citing
  the decisions it implements by number. Then re-point every open task that
  depended on the parent to the child that actually unblocks it (`Grep` for
  `Task <id>` under `tasks/`, fix with `set <other> "Depends on" …`), and
  close the parent as rule 8 of task-format.md says.

Done when every decision of the Outcome is implemented by exactly one task
and `check` prints `0 errors`.
