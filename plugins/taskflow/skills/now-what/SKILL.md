---
name: now-what
description: Reads the staged `tasks/` pipeline and answers "what makes sense to work on now?": the board of waves (what the Loop can start, what waits for the user, who blocks what), whether the open grills conflict with the ready tasks, and the recommended order; then offers the next actions as a menu and starts the one the user picks. Use when the user runs /taskflow:now-what, or asks what to do next given the backlog and dependencies.
argument-hint: "[focus: a task id or area, optional]"
allowed-tools: Read, Glob, Grep, AskUserQuestion, Bash(taskflow *), Bash(git log *), Bash(git status *)
---

Analysis of the repo's `tasks/` pipeline, ending in a menu of next actions. Up to the menu it changes nothing: no moves, no edits, no commits. Report in the language of the conversation. `$ARGUMENTS`, if given, narrows the analysis to that task id or area.

**Writing style (ASD-STE100, in the language you write).** One idea per sentence: about 20 words for a description, 15 for a step. Active voice. Steps in the imperative, one action per step. Common words, one meaning per word, the same term for the same thing. Prose only: headings, field names, ids, commands, code and the parsed header lines stay as their format requires.

This skill runs inline — deliberately **not** `context: fork`: the menu needs the user, and the action they pick (the Loop, a grill) runs in this session.

The mechanical facts come from the Tool, which costs no tokens; the judgement (contract conflicts, order) is yours. Do not recompute what the Tool prints.

## 1. Facts from the Tool

Run `taskflow board --plain`. It gives, without reading any task file:

- the active tasks in **waves**: `NOW` can move at once, `AFTER n` once the waves before are through; inside a wave the task that releases the most work comes first;
- per task, its role (`●` the Loop can start it, `◆` needs the user, `◇` to grill, `○` waits), what it waits for (`←`) and how many tasks it releases, directly and down the chain (`▶n`);
- `Loop now:` the loopable tasks of `NOW` with disjoint `Files`, already as one command; `(then …: same files)` the ones that must follow them;
- `Needs you:`, `Bottleneck:` (the user's task that holds the most), `Held:` (chains stuck on the backlog, a missing task or a cycle), `To test:`.

If the board says there are errors, run `taskflow check` and report them first, then go on. `To test:` counts tasks waiting for the Loop's verifier (the Loop runs them first) and names the few handed to the user; run `taskflow checks` only when you need their content for the order.

## 2. Open grills against ready work

For each task in `01_to-grill` (all of them, or only those the focus names), decide which of three it is, reading the grill's header and the ready tasks' `Files` and the code they touch (signatures, endpoints, types: Grep, not guesswork):

- **Conflicts:** its possible decisions would change a contract a ready task is about to fix (a port signature, an API body, a type, a state machine). Say which ready task, which contract, and which grill question decides it.
- **Additive:** it could add an optional parameter or field later without redoing the ready task. Say so in one line.
- **Independent:** different files and area; it can be grilled whenever.

Verify a claim in the code before stating it ("`post_batch` already takes `count`"). A grill that already carries a decision in its Outcome counts as decided. A conflicting grill outranks the Loop: starting the ready task first means redoing it.

## 3. Report

Open with the board, verbatim, in a ```` ```text ```` block: it is the picture, the rest is the commentary. Then, short, in this order. No tables; no restating the board or the task files.

1. **Start now with the Loop** — the `Loop now` group and why; say if the Loop has only one useful strand, or if a conflicting grill should go first.
2. **Needs you** — conflicting grills first, then the bottleneck and what it releases, design gate frames (group the ones that share one design round), grills the Loop sent back as blocked, other real checks, verifications handed to the user.
3. **Can wait** — independent or additive grills, with the one-line reason.
4. **Recommended flow** — numbered, 3 to 6 steps. The shape of a day: the user's part first, while they are here (grills, design gates: each one releases Loop work), then the Loop unattended until a stop condition. Put a Loop step earlier only when it has work no grill or design changes.
5. **Open question** — only if a decision of the user's changes the order. Otherwise omit.

## 4. Menu

End with AskUserQuestion: one question ("What do we do now?" in the conversation's language), 2 to 4 options, the next concrete actions in the order of the recommended flow, the first marked "(Recommended)". Each label names the action and the ids; each description says what it releases. Pick from:

| Action | Runs, once chosen |
|---|---|
| Start the Loop, unattended | Skill `taskflow:loop-it` with no argument: it verifies the backlog, then implements and verifies until a stop condition |
| Start the Loop on the `Loop now` group | Skill `taskflow:loop-it` with the ids, as the board prints them |
| Grill a task | Skill `taskflow:break-it-down` with the task id |
| A design gate round on its frames | Skill `taskflow:break-it-down` with the task id(s) |
| A real check, with the user here | read the task's real check and walk the user through it |
| The verifications handed to the user | Skill `taskflow:break-it-down` with `checks` |

Then do exactly the chosen action, and nothing before the choice. If the user writes their own answer, follow it; if they dismiss the menu, stop. Do not chain a second action after the first: when it is over, the user can run `/taskflow:now-what` again.
