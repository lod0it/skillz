---
name: loop-it
description: Implements and verifies the ready tasks of a staged `tasks/` pipeline in order, one fresh implementer and one fresh verifier subagent per task, turning each failure into a lesson the next subagent reads, until a stop condition. Use only when the user runs /taskflow:loop-it or picks "start the Loop" from the /taskflow:now-what menu; never on your own initiative.
argument-hint: "[max tasks | task ids to run together | verify, default: until a stop condition]"
allowed-tools: Read, Write, Edit, Agent, TaskStop, SendMessage, Bash(git status *), Bash(git log *), Bash(git show *), Bash(git add *), Bash(git commit *), Bash(git push *), Bash(git merge *), Bash(git worktree *), Bash(git branch *), Bash(git diff *), Bash(git -C *), Bash(git rev-parse *), Bash(head *), Bash(taskflow *), Bash(python3 ${CLAUDE_SKILL_DIR}/subagent_usage.py *), Bash(python3 ${CLAUDE_SKILL_DIR}/version_check.py *)
---

Run the task loop on the current repo. `$ARGUMENTS` is the maximum number of tasks to complete in this invocation (empty means "until a stop condition"), a list of task ids to run together, as `/taskflow:now-what` recommends them ("start the Loop on 93b 89 76c"), or `verify` (only the verification backlog of section 2, no new work). Several ids, or several candidates with disjoint `Files`, mean the **parallel mode** of section 8; otherwise the serial flow of sections 1–7. Report to the user in the language of the conversation.

**Who does what.** The user's part of the pipeline is the grilling, the design gate and the rare real check that needs them; everything from `03_ready` on belongs to the Loop: implement, verify, file the fix, learn. The user starts the Loop and leaves: never ask a question mid-run. What needs them goes into the closing summary, and the Loop moves on to the work that does not.

This skill runs inline in the current session — deliberately **not** `context: fork`: the session is the orchestrator and has to stay in front of the user between tasks. Each task runs in its own subagents so that each starts from a clean context, like a session after `/clear`: an **implementer** writes the code, a separate **verifier** that did not write it checks it by running the product. You (the main session) only pick, dispatch, check and report: never read task files, source files or diffs yourself beyond what the checks below need.

The repo is one set up by `/taskflow:break-it-down`: its `TASKS.md` has a "Task system" section, and the Tool that section names (`taskflow`) owns the task files' folder, Status mark and the generated index.

**One heavy run at a time.** The suite, a verification (server and browser) and a real run (GPU, local services) never overlap, in any checkout of the repo: two at once load the CPU and GPU enough to fail tests that pass alone, and a false failure costs a fix task. Every such command runs as `taskflow exclusive "<command>"`, which waits for the repo-wide lock (worktrees included), runs the command and releases it; exit 75 means the lock stayed busy for 9 minutes: run it again. The profiles say the same to the subagents. Everything that costs no tokens is the Loop's to run, real local services included when the task is about them; only paid tokens and what only the user has stay with the user.

## 1. Preflight (stop on failure)

- `git status --porcelain --untracked-files=no`: if the only dirty files are `TASKS.md` and files under `tasks/` (a task closed or moved by hand, a regenerated index, a lesson), commit them with `Tasks: sync pipeline state` and go on; any other dirty file → stop and list it (it may be the user's work in progress).
- `.claude/worktrees/` must be in `.gitignore`; if not, add it and commit it with the step above.
- `taskflow check` must print `0 errors`. If not, stop and show its output.
- "Task system" in `TASKS.md` names the `Test` command (the full suite) and the `Verify` recipe (how a session runs the product to look at it: the dev server with fake adapters, a headless browser, a CLI on sample data). No `Test` → stop and ask the user for it, then write the line. No `Verify` → write it yourself from what the repo has (README, start scripts, end-to-end tests) and report it under "Process changes" in the closing summary.
- The repo has the profiles `.claude/agents/implementer.md` and `.claude/agents/verifier.md`, and the implementer's closing step writes a `## Verification` (a profile that still writes a `## Manual check` predates the verifier). Missing or outdated: write them from [implementer-template.md](implementer-template.md) and [verifier-template.md](verifier-template.md), replacing each `{{…}}` with what the repo's `CLAUDE.md` and `TASKS.md` say (project name, Test command, Verify recipe, Design refs folder, the repo's own hard rules, one line each; keep the repo-specific lines of an existing profile); set the `Loop` line of "Task system" to `` `/taskflow:loop-it` ``; show the profiles to the user, and stop. Agent types are read when a session starts and the tree is now dirty, so the loop runs from the next session, after the user commits.
- `tasks/LESSONS.md` exists with its two sections, `## Project` and `## General (holds in any project)` (`taskflow check` warns otherwise): missing → `taskflow init` creates it; an old file without the sections → `taskflow migrate-tool` adds them and leaves its bullets, untouched, under Project. Commit it with the first step.
- Serial mode: one subagent at a time, and only while no other session is working in this checkout.

## 2. Pick the next unit of work

**Version check, before each task (serial) and before each batch (parallel), once the previous task is closed and pushed.** Run `python3 ${CLAUDE_SKILL_DIR}/version_check.py ${CLAUDE_SKILL_DIR}` (zero tokens; it always exits 0). `ok <v>` and `unknown` (no installed-plugins file, no version in the path, e.g. the lab run from source): go on. `restart <loaded> <installed>`: the installed taskflow is newer than the procedure this session loaded, so start nothing: leave the checkout clean (commit the pipeline state if needed), and write the closing summary opening with the line `taskflow updated <loaded> → <installed>: restart the session and run /taskflow:loop-it again`, then the usual restart (`/clear`, then `/taskflow:loop-it`). This is a stop condition like the worn context of section 6.

In this order:

1. **Verification backlog:** `taskflow checks` lists `05_to-be-tested`. Every task there not marked `[needs the user]` waits for a verifier: go to section 4 with it, lowest id first. These tasks already count as done for dependencies, so later tasks build on them: an unverified base is the most expensive bug. With `$ARGUMENTS` = `verify`, stop when this list is empty.
2. **Ready work:** `taskflow next`. The loop walks only `tasks/03_ready/` (never `00_backlog`, which holds tasks the user put on hold). Lines marked `loop` under "Ready and unblocked" are the candidates. A `bug` task that says `Fixes Task <id>` goes first: it repairs work that others build on. Then the order `TASKS.md` gives when it has a hand-written order section, otherwise top to bottom.

Lines marked `you` (Who `interactive`), blocked tasks, real checks and verifications handed to the user are not run: remember them for the closing summary. Nothing left in either list → stop.

**General rules, before each task (serial and parallel).** The user approves General Rules in the `agent-rules` repo, a sibling of this repo's main checkout. Read them live, so a rule change needs no release:

- The main checkout is the parent of the path `git rev-parse --path-format=absolute --git-common-dir` prints (from a worktree too: `../agent-rules` does not resolve there). Its parent folder holds `agent-rules`.
- When `<parent>/agent-rules` exists and `git -C <it> status --porcelain` prints nothing, run `git -C <it> pull --ff-only`.
- Collect line 1 of every `<parent>/agent-rules/rules/*.md` (`head -n 1`): each is a LESSONS-style bullet. Never read `rejected/` or the other lines of a rule file.
- Missing repo, dirty tree or failed pull → use what is there (or nothing) and put one line in the closing summary ("agent-rules not found", "agent-rules dirty: not pulled", "agent-rules pull failed: <first line>").

The bullets are pasted into the prompts of sections 3 and 4, because a worktree subagent cannot find the repo itself.

## 3. Implement

Agent tool, `subagent_type: implementer`, `model` from the task's Who, with this prompt:

> Implement Task <ID>: `tasks/03_ready/<file>`. The repo is at <absolute repo path>.
>
> General rules (approved by the user):
> <the collected bullets, one per line; "none yet" when there are none>

The profile already holds the reading list (lessons included), the closing procedure, the hard rules and the shape of the final answer: change them there, keep this prompt to the task. `Agent type 'implementer' not found` means this session started before the profile existed: stop and tell the user to start a fresh session. Wait for the completion notification; don't poll and don't start anything else meanwhile. A notification that says the agent is "waiting on its own background work" while its report is complete (the commit exists) is final: go on, and never wait for that agent again.

Then the zero-token checks:

- **Blocked** (the subagent says a decision only the user can make is missing; nothing committed): `taskflow move <id> to-grill --note "blocked: <the question, one line>"`, commit `Task <id>: back to grill`, and continue with the next task. The user finds the question among the morning's grills.
- `git log -1 --format=%s` starts with `Task <ID>:`, `git status --porcelain --untracked-files=no` is empty, `taskflow exclusive "<Test command>"` exits 0 (read only the last 3 lines of its output), `taskflow check` prints `0 errors`, and the task file is in `tasks/05_to-be-tested/`.
- One of these fails: dispatch **one** repair, `subagent_type: implementer`, same model, prompt `Task <ID> is committed but <what failed: the last lines of the suite, the dirty files, the check error>. Fix it so that the checks pass, and amend nothing: commit the fix as "Task <ID>: fix <what>".` Checks again; still failing → stop: the checkout is not a base the next task can build on.

## 4. Verify

Agent tool, `subagent_type: verifier`, `model` from the task's Who (at least `sonnet`), with this prompt:

> Verify Task <ID>: `tasks/05_to-be-tested/<file>`. The repo is at <absolute repo path>. The work is in the commits whose subject starts with `Task <ID>:`.
>
> General rules (approved by the user):
> <the collected bullets, one per line; "none yet" when there are none>

Its final answer starts with one verdict line:

- `VERDICT: passed` → it moved the task to `99_done` and committed. Then the **push step** (below).
- `VERDICT: failed → Task <new>` → it wrote a `bug` task that `Fixes Task <ID>` (in `03_ready`, so the next pick takes it; in `01_to-grill` when automatic fixes already failed twice) and closed the original with a note. Continue: the fix is the next unit of work.
- `VERDICT: needs the user: <why>` → the task stays in `05_to-be-tested` with that Status; only steps that would spend paid tokens or need what only the user has (another machine, an account, a person's judgement) end up here. Continue.

- `VERDICT: cannot run: <what broke>` → the `Verify` recipe is broken, which is not a verdict on the task: it stays in `05_to-be-tested`. Fix the recipe line if the verifier's report says how, and report it as a process change; otherwise stop and say what broke. Either way no further task is verified with a broken recipe.

Then: `git status --porcelain --untracked-files=no` is empty and `taskflow check` prints `0 errors`; otherwise stop.

**Push step** (serial mode, right after a `VERDICT: passed`; the only moment the Loop pushes, never before verification). Plain `git push`, never `--force` or `--force-with-lease`, and only from the main checkout. It sends the verified task's commits and any earlier unpushed ones (the commits that closed a failed task or filed a fix task are never pushed on their own: they go out with the next verified task). Four cases, each one line for the closing summary, and none of them stops the Loop:

1. **Pushed:** count it.
2. **No upstream** (`git rev-parse --abbrev-ref @{u}` fails): do not push; line "not pushed: no upstream". Do not set one.
3. **Rejected** (the remote is ahead): do not pull, merge or rebase; line "push rejected: pull first". Keep working locally; later tasks try again and meet the same rejection without retrying within a task.
4. **Offline or any other failure:** line "push failed: <first line of git's error>". No retry.

After a case 2, 3 or 4 skip the push step for the rest of the run (one line, not one per task), except that a rejection or failure may be tried once more after the next verified task.

## 5. Learn

The point of this section is that the next subagent does not repeat a failure. After each task, from what the two subagents reported (never from reading diffs), decide whether something cost a retry that one sentence in front of a subagent would have prevented:

| Signal | Lesson for |
|---|---|
| the verifier failed the task: what the implementer missed and why its own checks did not catch it | `implementer` |
| a repair was needed after the implementer (red suite, dirty tree) | `implementer` |
| the verifier struggled to reach a state, or its check was weak and a later fix showed it | `verifier` |
| the implementer was blocked or guessed because the task file left something out | `tasks` (how break-it-down writes them) |
| a subagent's peak context was over 120k | `tasks` (cut smaller) |

A lesson goes in `tasks/LESSONS.md` as one bullet: `- **<implementer | verifier | tasks>** <when this happens> → <do this>. (Task <id>, <date>)`. A rule, not a story, and concrete: it names a file, a tool, a command or a symptom (a generic "test more" teaches nothing). It goes under **General (holds in any project)** when it names nothing of this project (a Windows / Git Bash / uv / Playwright / Electron quirk, a verification method), under **Project** otherwise; a General lesson is as concrete as a Project one, never vague. Both sections are read by every subagent, so the section only says where the lesson would still hold. A lesson under General is a *proposal* to the user, approved or rejected in agentic-control-plane's Rules tab; until the user decides, it holds in this project. It must name no file, task, path or product name of this project (the Task id and date in the closing parenthesis stay). Before adding, look for a lesson that already says it: sharpen that one instead. Past 40 bullets, merge the ones that overlap. Commit `Loop: lesson from Task <id>`. Both profiles read the file before every task, so the very next subagent already applies it; no restart needed.

**Process changes.** A change to how the Loop itself works is of two kinds:

- **Applied without asking:** lessons in `tasks/LESSONS.md`; a `Verify` line written or corrected; a `bug` task, or a ready task that builds a missing verification harness (it is code like any other). Each one is a line in the closing summary.
- **Proposed, never applied by the Loop:** anything that changes what reaches the user or what a run costs: the stages and gates, `Who`, `Test`, the hard rules, the agent profiles, the models, this skill. Write the proposal under "Process changes to review" in the closing summary, with the lessons that motivate it: the user applies it, or asks you to.

## 6. Report each task

Run `python3 ${CLAUDE_SKILL_DIR}/subagent_usage.py --last <n>` for the subagents of this task (zero tokens: it reads their transcripts). Tell the user, in one short block: task id and title, commits, verdict (and the new task id on a failure), the start context, peak context and turns of each subagent, the lesson written if any, and the doubts the subagents reported, verbatim.

The script's last line is this session's own context. Past 150k the session is too worn to orchestrate well (it misreads reports, forgets earlier steps): that is a stop condition. Leave the checkout clean (commit the pipeline state if needed), write the closing summary, and end it with the restart: `/clear`, then `/taskflow:loop-it`. Everything the Loop needs is on disk (task files, lessons, git), so the fresh session resumes where this one stopped.

**No agent outlives its task.** Once a task has its verdict (and its merge, in parallel mode), stop with `TaskStop` every subagent of the task that has not notified "finished" (implementer, repair, verifier), then remove its worktree if it has one. Do the same for any still alive before the closing summary. A stalled agent (no notification, no live process) is stopped if its work is committed; otherwise it gets one `SendMessage` to resume, and is stopped if it stalls again.

Then, if the max number of tasks is not reached and no stop condition fired, go back to step 2.

## 7. Closing summary

- Verified and done; failed and fixed (with the fix's id); still failing.
- **Needs the user:** grills (marking those the Loop sent back as blocked), design gates, real checks, verifications handed to the user. These are the agenda of the next session together.
- **Lessons learned this run**, one line each.
- **Process changes:** applied (one line each) and **to review** (the proposals of section 5).
- The reason the loop stopped (a newer taskflow installed: the `taskflow updated <loaded> → <installed>` line first; a worn session context included, with the restart commands).

- **Pushes:** "pushed n times", or the failure line of the push step (no upstream, push rejected: pull first, push failed). Commits not pushed (grill, break-it-down, failed tasks) remain the user's to push.

The Loop saves no session recap: that is the user's.

## 8. Parallel mode

Used when the user names several ids or `next` offers several `loop` candidates with disjoint `Files`. Never put two tasks that share a `Files` entry, or one that depends on another of the batch, in the same batch: run them in series (the dependent one in a later round). A task that drives real services or the GPU runs alone, never in a batch. In a batch the subagents write code side by side but take turns on the exclusive lock for every suite and check, so a batch saves the writing time, not the testing time. The preflight above has already committed the pipeline state, so every worktree starts from a HEAD that contains it. Run the verification backlog of section 2 first, in serial mode. Run the version check of section 2 before each batch.

1. **Implement** all tasks of the batch in one message: Agent tool, `subagent_type: implementer`, `isolation: worktree`, `run_in_background: true`, `model` from each task's Who, same prompt as section 3. Don't start anything else meanwhile; each completion notification carries the worktree path and branch (if it is missing, `git worktree list`).
2. **Check** each finished task as in section 3, inside its worktree (`git -C <path> ...`; run `taskflow exclusive "<Test command>"` with that path as working directory).
3. **Verify** each task as in section 4, with the worktree path as the repo: **one verifier at a time**, since they start servers and browsers that would fight over ports and files.
4. **Merge**, one at a time, in dependency order (otherwise the order of completion), every task whose verifier gave a verdict, whatever the verdict: the serial flow would have committed the same code and the same fix task.
   - `git merge --no-ff <branch> -m "Merge Task <ID>: <title>"`.
   - A conflict only in `TASKS.md`, `tasks/LESSONS.md` or a generated index: for the index take either side and run `taskflow index`; for the lessons keep both sides' bullets, each in the section it was written in (`## Project` or `## General (holds in any project)`), and both headings once; then `taskflow check` and commit the merge. Two fix tasks that took the same new id: renumber the later one with `taskflow next-id` before committing. A conflict in any other file: `git merge --abort`, leave the worktree, stop and tell the user which files.
   - Run `taskflow exclusive "<Test command>"` on the merged checkout and `taskflow check`. Red → stop, no revert, no further merge: the user decides.
   - On success stop the task's subagents still alive (section 6), then remove the worktree and delete the branch (`git worktree remove`, `git branch -d`).
5. A task blocked or still failing after its repair is left in its worktree, with the subagent's explanation.
6. **Push** once, after step 4 has merged the batch into the main checkout and the suite there is green: the push step of section 4, from the main checkout. Never push from a worktree branch, and never push before a verifier has given a passing verdict (a batch with no `VERDICT: passed` pushes nothing).
7. Learn (section 5) from every task of the batch, report as in section 6, then the closing summary (with the push result).
