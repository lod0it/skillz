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

Before the first round, sort what the task asks. Whatever needs no decision
from the user (the way is obvious, one area, one or two files, nothing new to
check by eye) is not grilled and not turned into a task: list it and offer to
do it right away, as rule 10 of [task-format.md](task-format.md) says.

Size the work as the decisions settle, not at the end: when the answers add up
to more than 8 files or more than 3 areas, say the task will be split and
what the pieces are, so the user grills each piece's decisions with its
boundaries in view.

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

- **It fits one context window and has one deliverable** (at most 8 `Files`
  and 3 areas, rule 1 of task-format.md): rewrite this same
  file as a full task ([task-format.md](task-format.md)) and `move <id>` to
  the stage it now needs.
- **Otherwise split, always, never a task "to cut later":** write the children per task-format.md, each citing
  the decisions it implements by number. Then re-point every open task that
  depended on the parent to the child that actually unblocks it (`Grep` for
  `Task <id>` under `tasks/`, fix with `set <other> "Depends on" …`), and
  close the parent as rule 8 of task-format.md says.

Done when every decision of the Outcome is implemented by exactly one task
and `check` prints `0 errors`.

## A task in the design gate

The design gate is the one place, with the grilling, where the user works
with you; everything after it runs unattended. Build or revise the design
with the user in the tool the `Design gate` line names, round by round, until
they approve each frame. Then, before closing the task:

1. **Export every approved frame** as a PNG into the folder the `Design refs`
   line of "Task system" names (`<frame id>_<slug>.png`; one image per state
   the frame shows: empty, filled, error). These images are the contract: the
   implementer builds from them, the verifier compares screenshots with
   them, and neither can open the design tool. A frame approved but not
   exported does not exist for the Loop.
2. **Cite them** by path in the Context of each UI task that implements the
   frame, and in its Verification ("compare the Candidates screen with
   `<path>`").
3. `move <id> done --note "approved <date>: <frame ids>, exported to <folder>"`.

No `Design refs` line yet: propose a folder inside the repo (next to the
design docs), write the line, and say so in the report.
