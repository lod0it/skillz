---
name: now-what
description: Reads the staged `tasks/` pipeline and answers "what makes sense to work on now?": what the Loop can start, what waits for the user (grill, design gate, real checks, manual checks), whether the open grills conflict with the ready tasks, and the recommended order. Read-only. Use when the user runs /taskflow:now-what, or asks what to do next given the backlog and dependencies.
argument-hint: "[focus: a task id or area, optional]"
context: fork
model: sonnet
effort: medium
allowed-tools: Read, Glob, Grep, Bash(taskflow *), Bash(git log *), Bash(git status *)
---

Read-only analysis of the repo's `tasks/` pipeline. It changes nothing: no moves, no edits, no commits. Report in the language of the conversation. `$ARGUMENTS`, if given, narrows the analysis to that task id or area.

The mechanical facts come from the Tool, which costs no tokens; the judgement (contract conflicts, order) is yours. Do not recompute what the Tool prints.

## 1. Facts from the Tool

Run `taskflow check`, `taskflow status`, `taskflow next`, `taskflow checks`. If `check` reports errors, say so first and still go on. Take from `next`: what the Loop can start now, what is blocked and by whom, which loopable tasks have disjoint files.

## 2. What each task unlocks

For every task in `01_to-grill`, `02_design-gate`, `03_ready` and `04_real-check`, read its header only (`Depends on`, `Who`, `Files`, first lines) with Grep or a short Read. Tasks in `00_backlog` are on hold: do not analyse or rank them, only add one line "N in backlog" (and flag a ready task that depends on one). Build the reverse view: for each task that is not done, which blocked tasks does it release? Rank the unblockers by how much they release, directly and through the chain. Tasks on the same `Files` in the same chain run in series, never side by side.

## 3. Open grills against ready work

For each task in `01_to-grill` (all of them, or only those the focus names), decide which of three it is, reading the ready tasks' `Files` and the code they touch (signatures, endpoints, types: Grep, not guesswork):

- **Conflicts:** its possible decisions would change a contract a ready task is about to fix (a port signature, an API body, a type, a state machine). Say which ready task, which contract, and which grill question decides it.
- **Additive:** it could add an optional parameter or field later without redoing the ready task. Say so in one line.
- **Independent:** different files and area; it can be grilled whenever.

Verify a claim in the code before stating it ("`post_batch` already takes `count`"). A grill that already carries a decision in its Outcome counts as decided.

## 4. Report

Short, in this order. No tables over 6 rows; no restating the task files.

1. **Start now with the Loop** — the loopable task(s), the chain behind them and why in series or in parallel. Say if the Loop has only one useful strand.
2. **Needs you, in this session** — design gate frames (group the ones that share one design round), real checks and what they unblock, manual checks waiting, and grills that conflict with ready work (these first).
3. **Can wait** — independent or additive grills, with the one-line reason.
4. **Recommended flow** — numbered, 3 to 6 steps, mixing the Loop (background, fresh contexts) with what the user does here. Name the single bottleneck (usually a design gate or a real check) and what it blocks.
5. **Open question** — only if a decision of the user's changes the order. Otherwise omit.

End by offering the next concrete action (for example "start the Loop on 41a", "grill 35 and 36"). When several loopable tasks have disjoint `Files`, offer them as one command, `/taskflow:task-loop <ids>`: the Loop then runs them in parallel worktrees, commits the pipeline state first and merges the finished `done` tasks back by itself. Never start it yourself.
