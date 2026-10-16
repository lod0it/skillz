---
name: task-loop
description: Implements the ready tasks of a staged `tasks/` pipeline in order, one fresh subagent per task, until a stop condition. Use only when the user runs /taskflow:task-loop or picks "start the Loop" from the /taskflow:now-what menu; never on your own initiative.
argument-hint: "[max tasks | task ids to run together, default: until a stop condition]"
allowed-tools: Read, Write, Edit, Agent, Bash(git status *), Bash(git log *), Bash(git add *), Bash(git commit *), Bash(git merge *), Bash(git worktree *), Bash(git branch *), Bash(git diff *), Bash(taskflow *), Bash(python3 ${CLAUDE_SKILL_DIR}/subagent_usage.py *)
---

Run the task loop on the current repo. `$ARGUMENTS` is either the maximum number of tasks to complete in this invocation (empty means "until a stop condition"), or a list of task ids to run together, as `/taskflow:now-what` recommends them ("start the Loop on 93b 89 76c"). Several ids, or several candidates with disjoint `Files`, mean the **parallel mode** of section 6; otherwise the serial flow of sections 1–5. Report to the user in the language of the conversation, one short block per task.

This skill runs inline in the current session — deliberately **not** `context: fork`: the session is the orchestrator and has to stay in front of the user between tasks. Each task runs in its own subagent so that it starts from a clean context, like a session after `/clear`. You (the main session) only pick, dispatch, verify and report: never read task files, source files or diffs yourself beyond what the checks below need.

The repo is one set up by `/taskflow:task-breakdown`: its `TASKS.md` has a "Task system" section, and the Tool that section names (`taskflow`) owns the task files' folder, Status mark and the generated index.

## 1. Preflight (stop on failure)

- `git status --porcelain --untracked-files=no`: if the only dirty files are `TASKS.md` and files under `tasks/` (a task closed or moved by hand, a regenerated index), commit them with `Tasks: sync pipeline state` and go on; any other dirty file → stop and list it (it may be the user's work in progress).
- `.claude/worktrees/` must be in `.gitignore`; if not, add it and commit it with the step above.
- `tasks.py check` must print `0 errors`. If not, stop and show its output.
- The `Test` line of "Task system" in `TASKS.md` names the command that runs the full suite. No command there → stop and ask the user for it, then write the line.
- The repo has the profile `.claude/agents/implementer.md`. If it is missing, this is the repo's first loop: write the profile from [implementer-template.md](implementer-template.md), replacing each `{{…}}` with what the repo's `CLAUDE.md` and `TASKS.md` say (project name, Test command, the repo's own hard rules, one line each); set the `Loop` line of "Task system" to `` `/taskflow:task-loop` ``, so that `next` proposes it; show both to the user, and stop. Agent types are read when a session starts and the tree is now dirty, so the loop runs from the next session, after the user commits.
- Serial mode: one subagent at a time, and only while no other session is working in this checkout.

## 2. Pick the next task

Run `tasks.py next`. The loop walks only `tasks/03_ready/` (never `00_backlog`, which holds tasks the user put on hold):

- Lines marked `loop` under "Ready and unblocked" are the candidates (dependencies satisfied, Who is a model, not `interactive`). Take them in the order `TASKS.md` gives when it has a hand-written order section, otherwise top to bottom.
- Lines marked `you` (Who `interactive`), blocked tasks, real checks and pending manual checks are not run: remember them for the closing summary ("needs you").

No `loop` line left → stop.

## 3. Dispatch one subagent

Agent tool, `subagent_type: implementer`, `model` from the task's Who, with this prompt (fill in the placeholders):

> Implement Task <ID>: `tasks/03_ready/<file>`. The repo is at <absolute repo path>.

The profile already holds the reading list, the closing procedure, the hard rules and the shape of the final answer: change them there, keep this prompt to the task. A lean profile starts from about 8k tokens of context instead of the 24k–27k of `general-purpose`.

`Agent type 'implementer' not found` means this session started before the profile existed: stop and tell the user to start a fresh session.

Wait for its completion notification; don't poll and don't start anything else meanwhile.

## 4. Verify (zero-token checks, stop on failure)

- `git log -1 --format=%s` starts with `Task <ID>:` (unless the subagent reported it was blocked → stop and relay its explanation).
- `git status --porcelain --untracked-files=no` is empty.
- The Test command passes: exit status 0. Read only the last 3 lines of its output.
- `tasks.py check` prints `0 errors`, and the task file is now in `tasks/05_to-be-tested/` or `tasks/99_done/`.

## 5. Report and continue

Run `python3 ${CLAUDE_SKILL_DIR}/subagent_usage.py --last 1` (zero tokens: it reads the subagent's transcript). Tell the user: task id and title, commit hash, suite result, where the task went (to be tested, with its Manual check, or done), the subagent's start context, peak context and turns, and its doubts verbatim. A peak over 120k means the task was cut too large: say so, it is the lesson for the next split. Then, if the max number of tasks is not reached and no stop condition fired, go back to step 2.

At the end, a closing summary: tasks completed, tasks now waiting for the user's Manual check (`/taskflow:task-breakdown checks` goes through them in one pass), tasks that need the user (interactive, real checks, to grill, design gate), and the reason the loop stopped. The loop pushes nothing and saves no session recap: both are the user's.

## 6. Parallel mode

Used when the user names several ids or `next` offers several `loop` candidates with disjoint `Files`. Never put two tasks that share a `Files` entry, or one that depends on another of the batch, in the same batch: run them in series (the dependent one in a later round). The preflight above has already committed the pipeline state, so every worktree starts from a HEAD that contains it.

1. **Dispatch** all tasks of the batch in one message: Agent tool, `subagent_type: implementer`, `isolation: worktree`, `run_in_background: true`, `model` from each task's Who, same prompt as section 3. Don't start anything else meanwhile; each completion notification carries the worktree path and branch (if it is missing, `git worktree list`).
2. **Verify** each finished task as in section 4, but inside its worktree (`git -C <path> ...`; run the Test command with that path as working directory).
3. **Merge**, one at a time, in dependency order (otherwise the order of completion), only a task that is in `tasks/99_done/` in its worktree with the suite green there:
   - `git merge --no-ff <branch> -m "Merge Task <ID>: <title>"`.
   - A conflict only in `TASKS.md` or in a generated index: take either side, run the Tool's index regeneration (the `Tool` line of "Task system") and `taskflow check`, then commit the merge. A conflict in any other file: `git merge --abort`, leave the worktree, stop and tell the user which files.
   - Run the Test command on the merged checkout and `taskflow check`. Red → stop, no revert, no further merge: the user decides.
   - On success remove the worktree and delete the branch (`git worktree remove`, `git branch -d`).
4. A task that ended in `to-be-tested` (or with pending steps) is **not merged**: the user has not tried it yet. Keep its worktree and branch, and report the command to merge it after the Manual check (`git merge --no-ff <branch>`). A blocked or failing task is also left in place, with the subagent's explanation.
5. Report as in section 5 for every task (the usage script takes `--last <n>`), plus: merged, left unmerged and why. Same closing summary. Nothing is pushed.
