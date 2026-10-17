# Branch: checks --auto

The same sitting as [checks.md](checks.md), but the steps a shell can do are
run by you first. The user only sees what is left.

1. **Collect:** run `checks`. A task without a `## Manual check` section is
   handled as in `checks.md` step 1.
2. **Classify every step** of every task as one of:
   - **runnable:** a command with an observable result (exit code, output,
     a file that exists or not, a count), a TUI driven through `tmux`, a
     headless `claude -p` call.
   - **human-only:** how something *looks* (colours, layout), a step that
     needs the user's real terminal, editor, sign-in or `$SHELL`, or that
     writes to the user's real state (`~/.claude/settings.json`,
     `~/.local/bin`, the installed plugins). Run such a step only against a
     copy: a temporary `HOME`, a scratch repo. If a copy cannot show it,
     it is human-only.
   - The task's "Not verified" line names what its author could not check:
     start from it, it is usually the human-only part.
3. **Run the runnable steps** in a scratch directory (never in the working
   tree), with a temporary `HOME` when the step installs or writes config.
   - TUI: `tmux new-session -d -x 120 -y 40`, keys with `send-keys`, the
     screen with `capture-pane -p` (add `-e` to see colour codes), resize
     with `resize-window`. Kill the session afterwards.
   - Stop, do not retry, a step that would spend tokens or cost money
     (a non-headless `claude` run): treat it as human-only.
   - Keep per step: the command, and the output or screen that decided it.
4. **Decide per task:**
   - **every step runnable and passed** → `move <id> done --note "done;
     manual check run automatically (<one line of evidence>)"`.
   - **a step failed** → write the `bug` task exactly as in `checks.md`
     step 3, citing the command and what it printed; then close the old task
     with the same note.
   - **some steps human-only** → the task stays. Record nothing yet.
5. **Present what is left** as in `checks.md` step 2: only the human-only
   steps, grouped by place, each with the task id and, in one line, what was
   already verified automatically so the user does not repeat it. Record the
   user's answers as in `checks.md` step 3.
6. Report in a table: id, steps run, passed, failed, left to the user.

Done when every task is moved, has a bug task, or has its human-only steps in
front of the user, and `check` prints `0 errors`.
