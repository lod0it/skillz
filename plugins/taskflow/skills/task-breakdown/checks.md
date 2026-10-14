# Branch: checks

One sitting in which the user clears the Manual checks waiting in
`05_to-be-tested`.

1. **Collect:** run `checks`. A task it prints without a `## Manual check`
   section predates the format: write the section now from its Status line,
   Steps and Outcome (at most 5 steps: what to open, what to do, what the
   user should see).
2. **Present one pass, grouped by place:** reorder the steps by the screen,
   page or command where the user performs them, so one visit covers every
   task that needs it. Keep the task id on each step.
3. **Record each answer the user gives:**
   - **passed** → `move <id> done`.
   - **failed** → write a new `bug` task ([task-format.md](task-format.md))
     whose Context cites the task, the failing step and what the user saw;
     then `move <id> done --note "done; manual check failed at <step>, fixed
     by Task <new id>"`. The old task stays closed: its code is already
     under later work.
   - **not tried** → leave it where it is.

Done when every task the user answered about has moved and `check` prints
`0 errors`.
