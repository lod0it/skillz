# Branch: a plan document

Turn a design or plan document into tasks.

1. **Read** the document in full, then the repo's `CLAUDE.md` and the
   Conventions of `TASKS.md`: they carry constraints the plan does not
   restate.
2. **Cut** along the plan's deliverable boundaries, by the rules of
   [task-format.md](task-format.md). A part the plan marks exploratory or
   optional becomes its own task at the end and blocks nothing. Size each
   task by rule 1 of task-format.md (8 files, 3 areas) and offer to do the
   decision-free changes right away instead of writing tasks for them
   (rule 10).
3. **Send undecided parts to `01_to-grill`** as stubs: a part where you
   would have to guess what the user wants is a decision, and guesses
   written into Steps read as decisions to the next session.
4. **Write** one file per task, ids from `next-id` counting up, each Context
   naming the plan document by path and section.
5. **On a re-run after the plan changed:** closed tasks are history and stay
   as they are; among the open ones, add the new tasks and update only those
   the change made wrong, keeping the user's own edits.

Done when every deliverable of the plan is covered by a task or a to-grill
stub and `check` prints `0 errors`.
