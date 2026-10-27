# Branch: checks

The Loop's verifier checks every implemented task by running the product
(`/taskflow:loop-it`, or `/taskflow:loop-it verify` for the backlog alone).
This branch is the rare rest: the items it handed to the user because
checking them would spend paid tokens or need what only the user has
(another machine, an account, a person's judgement such as an artist review).

1. **Collect:** run `checks`. Tasks marked `[needs the user]` are this
   branch's. Tasks without the mark still wait for the verifier: say so and
   propose `/taskflow:loop-it verify`, do not ask the user about them.
2. **Present one pass, grouped by place:** only the items marked `needs the
   user`, reordered by the screen, page, machine or command where the user
   performs them, so one visit covers every task that needs it. Keep the task
   id on each step, and say in one line what the verifier already proved so
   the user does not repeat it.
3. **Record each answer the user gives:**
   - **passed** → `move <id> done --note "verified; <item> by the user"`.
   - **failed** → write a new `bug` task ([task-format.md](task-format.md))
     whose Context opens with `Fixes Task <id> (attempt 1)`, then the failing
     item and what the user saw; then `move <id> done --note "done;
     verification failed at <item>, fixed by Task <new id>"`. The old task
     stays closed: its code is already under later work.
   - **not tried** → leave it where it is.
4. **Learn:** when the item could have been checked without the user (a
   fake, a scratch copy, a second browser context would have shown it), add
   a `verifier` lesson to `tasks/LESSONS.md` saying how.

Done when every task the user answered about has moved and `check` prints
`0 errors`.
