---
name: task-loop
description: Implements the ready tasks of a staged `tasks/` pipeline in order, one fresh subagent per task, until a stop condition. Use when the user runs /taskflow:task-loop.
argument-hint: "[max tasks, default: until a stop condition]"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Agent, Bash(git status *), Bash(git log *), Bash(taskflow *), Bash(python3 ${CLAUDE_SKILL_DIR}/subagent_usage.py *)
---

Run the task loop on the current repo. `$ARGUMENTS` is the maximum number of tasks to complete in this invocation; empty means "until a stop condition". Report to the user in the language of the conversation, one short block per task.

This skill runs inline in the current session — deliberately **not** `context: fork`: the session is the orchestrator and has to stay in front of the user between tasks. Each task runs in its own subagent so that it starts from a clean context, like a session after `/clear`. You (the main session) only pick, dispatch, verify and report: never read task files, source files or diffs yourself beyond what the checks below need.

The repo is one set up by `/taskflow:task-breakdown`: its `TASKS.md` has a "Task system" section, and the Tool that section names (`taskflow`) owns the task files' folder, Status mark and the generated index.

## 1. Preflight (stop on failure)

- `git status --porcelain --untracked-files=no` must be empty. If not, stop and list the dirty files.
- `tasks.py check` must print `0 errors`. If not, stop and show its output.
- The `Test` line of "Task system" in `TASKS.md` names the command that runs the full suite. No command there → stop and ask the user for it, then write the line.
- The repo has the profile `.claude/agents/implementer.md`. If it is missing, this is the repo's first loop: write the profile from [implementer-template.md](implementer-template.md), replacing each `{{…}}` with what the repo's `CLAUDE.md` and `TASKS.md` say (project name, Test command, the repo's own hard rules, one line each); set the `Loop` line of "Task system" to `` `/taskflow:task-loop` ``, so that `next` proposes it; show both to the user, and stop. Agent types are read when a session starts and the tree is now dirty, so the loop runs from the next session, after the user commits.
- One subagent at a time, and only while no other session is working in this checkout.

## 2. Pick the next task

Run `tasks.py next`. The loop walks only `tasks/03_ready/`:

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
