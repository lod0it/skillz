# Branch: notes

Sort the inbox into tasks. The inbox is the file `Inbox` names in the Task
system section of `TASKS.md`: free text in any language, no format. An idea
given in the argument or in the conversation is one more entry.

## 1. Read the inbox against the board

Split the inbox into entries (one idea each, however the user separated
them). For each entry look for a task that already covers it: the Index of
`TASKS.md` for open tasks, `Grep` over `tasks/99_done/` for closed ones.

## 2. Propose one outcome per entry

Show one table, every entry on a row, with one of three outcomes:

- **New task:** stage, Type, title, Depends on. Small and already clear
  goes to `03_ready`; anything with a decision in it is a to-grill stub.
- **Add to Task N:** the entry is a detail or a constraint of an open task.
- **Stays in the inbox:** with the reason.

An entry becomes a task only when the user would grill or build it in the
coming weeks. A dream stays in the inbox: `01_to-grill` holds work waiting
for decisions, and it stops being readable the day it also holds wishes.
Recommend "stays" whenever you would not bet on the entry being picked up.

Wait for the user's corrections.

## 3. Write

- **New task:** per [task-format.md](task-format.md). A ready task needs the
  code read first (Files, Steps); a stub keeps the user's idea in its
  Context, translated, without losing a detail.
- **Addition:** a dated bullet in the Context of the open task. When the
  task that covers it is closed, write a new task that cites it by id.

## 4. Empty what was sorted

Remove from the inbox exactly the entries that became a task or an
addition, and leave every other character as it was. When the inbox is
tracked by git, tell the user once: it is meant to stay out of the repo.

Done when every entry has its confirmed outcome and `check` prints
`0 errors`.
