---
name: ablate
description: Ablative simplification of one script. Removes one logical block at a time, checks that behaviour is unchanged (tests, a recorded golden output, or static reasoning when neither exists), and keeps a cut only when the check passes. Works on a dedicated git branch and squashes it at the end without merging. Run it only when the user types /refine:ablate.
argument-hint: "<path/to/script>"
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Grep, Glob, AskUserQuestion, Bash(refine *), Bash(git status *), Bash(git rev-parse *), Bash(git switch *), Bash(git add *), Bash(git commit *), Bash(git checkout -- *), Bash(git diff *), Bash(git log *), Bash(git reset --soft *)
---

Make the script `$ARGUMENTS` as short as possible without changing what it does. Brevity (lines and tokens) is the goal. It is limited by three rules: behaviour stays the same, speed does not drop, and the code stays readable (no golf). Report in the language of the conversation.

The `refine` command does the mechanical work: it records and checks outputs, measures, and maps coverage, at zero tokens. Do not recompute what it prints. Your part is the judgement: which cuts to try, in what order, and whether a cut is golf. `refine golden --help`, `refine measure --help` and `refine coverage --help` document the formats and exit codes.

Fixed rules for the whole run:
- **Edit only the target file.** Local modules it imports are read-only. Cuts you see there go in the report as suggestions.
- **Do not touch lines the oracle does not cover** (only when coverage was measured). They go in the report as "unverifiable".
- **The public interface is frozen.** That means exported symbols, signatures, CLI flags, env vars read and the output format. The only exception is symbols the user approves in step 5.
- **Never add code to gain speed.** Such ideas go in the report as suggestions.
- **Keep all working files outside the repo**, in `W = $TMPDIR/refine-ablate/<stem>-<date>/`: cases, recordings, the coverage scratch dir. This way the tree stays clean and `git checkout -- <file>` reverts exactly one cut.

## 1. Preflight

1. `$ARGUMENTS` must name exactly one existing file inside a git repository. If it does not, stop and say why.
2. Run `git status --porcelain`. If it prints anything, stop: the tree must be clean so that every cut can be reverted exactly. Tell the user to commit or stash first.
3. Save the base: `git rev-parse --abbrev-ref HEAD` (the base branch) and `git rev-parse HEAD` (`BASE`).
4. Run `git switch -c ablate/<file-stem>-<YYYYMMDD>`. If that branch already exists, add `-2`, `-3`, and so on.
5. Read the whole target file. Run `refine coverage --probe <file> --scratch W/tools` to get its language and coverage tool.

## 2. Oracle

Choose the first option that works. The result is the oracle **mode** you report.

- **tests.** Some tests exercise the file. Look for test files that import it, call it, or name it, using Grep. Run the test command once. It must pass on the base. If it fails, the tests cannot be the oracle: go to the next option. A cut is verified when the test command exits 0.
- **golden.** The script can run without network, database, or interactive input. Write `W/cases.json` with 3 to 8 cases that exercise its paths: normal input, edge cases, error exits, each flag. Use the format in `refine golden --help`. Rules for the cases:
  - The script goes in `argv` by its **absolute path** in the repo, e.g. `["python3", "/abs/repo/tool.py", "--flag"]`. Coverage only maps cases that name the script that way. Use `{root}` only for fixtures, which live under `W`.
  - Put fixtures under `W` and list them in `files`.
  - Set `env` for anything that changes the output: `LANG`, `TZ`, `NO_COLOR`.

  The user approves the cases in step 5. After that, run `refine golden record W/cases.json W/golden`. It exits 1 when a case is `unstable` or `timeout`. Rewrite those cases to make them deterministic, or drop them, then record again. The record must exit 0. A cut is verified when `refine golden verify W/cases.json W/golden` prints `OK`.
- **static.** Neither option is possible. Only coverage-independent cuts are allowed, and each one must be provably behaviour-preserving just by reading the code. The report says "static" in plain words.

## 3. Coverage

This step needs a `cases.json`. Golden mode has one. In tests mode, write `W/cases.json` with one case per test command. Python and shell need a case whose `argv` names the script by absolute path. If the file is only imported by its tests, add direct CLI cases, or accept conservative mode.

Run `refine coverage <file> W/cases.json --scratch W/tools`:
- **Exit 0, `mode: measured`.** `covered` lists the lines the oracle reaches. If the output lists `unmapped_cases` or `failed_cases`, they reached nothing: mention them in the report.
- **Exit 3, `mode: unavailable`.** If `install_hint` is not null, ask in step 5 whether to run it. The install is local, under `W/tools`, never global. If the user says yes, run it and run coverage again. If they say no, or there is no hint, use **conservative mode**.
- **Exit 2.** No case runs the script, or the cases are invalid. Fix the cases if you can. Otherwise use conservative mode.

In static mode, skip this step: static mode is always conservative.

Conservative mode allows only the coverage-independent kinds in [candidates.md](candidates.md). No conditional branch is ever removed. Line numbers move when you cut. In measured mode, run `refine coverage` again after every kept cut.

## 4. Interface

List the public interface of the file: exported or top-level public symbols with their signatures, CLI flags and subcommands, env vars it reads, files it writes, and the output format. For each exported symbol, grep the whole repo (excluding the file itself). A symbol with no use outside the file is an **interface candidate**: it may be removed or changed, but only with approval. Everything else stays frozen.

## 5. Approvals, in one round

Ask everything in **one** AskUserQuestion call, before any edit. Use one question per topic, and only the topics that apply:
1. **Golden inputs.** Show the cases (name and argv, one line each).
2. **Coverage tool install.** Show the `install_hint` command.
3. **Interface candidates.** One option per symbol, multi-select.

After this round, the loop runs without interruption. If an answer changes the cases, record them again before step 6. Nothing else is asked until the report.

## 6. Baseline

Run `refine measure <file>`. If the oracle is golden and the cases are fast (`record` took a few seconds at most), add `--time W/cases.json`. Keep the JSON: it is the "before" column. With timing on, a kept cut must not raise `time_s` by more than 10%.

## 7. Loop

**Build the candidate list.** Each candidate is one logical block: a function, a branch, a guard, an import, an unused parameter, a single-use abstraction to inline, or a duplication to merge. [candidates.md](candidates.md) lists the kinds, the mode each needs, and the golf test. Remove from the list:
- every candidate that touches a frozen interface item;
- every candidate whose lines are not in `covered` (measured mode only; those lines go to "unverifiable"). Check only the statements that run. Structural lines never appear in `covered`, so do not count them: `else`, `fi`, `done`, closing braces, blank lines, comments, and sometimes a `def` line;
- every candidate whose kind conservative mode does not allow.

Order the rest by expected gain (lines and tokens removed), largest first.

**Process one candidate at a time:**
1. Apply the cut with Edit. Change only that block, plus whatever the cut makes dead in the same step (e.g. the import used only by the removed function).
2. **Golf check.** Read the result. If it is shorter but harder to read (cryptic names, packed expressions, clever tricks, a lost explanatory name), revert it and record it as "golf".
3. **Verify** with the oracle. In golden mode the command is `refine golden verify W/cases.json W/golden`. With timing on, also run `refine measure <file> --time W/cases.json`.
4. **If it passes,** run `git commit -am "ablate: <what was cut>"`. In measured mode, run coverage again.
5. **If it fails,** run `git checkout -- <file>` and record the reason: which case or test failed, or "slower".

**Passes.** A pass ends when the list is empty. Then build a new list from the new code: an earlier cut can expose new dead code. Stop at the fixed point (a pass that keeps no cut), or after **3 passes**.

## 8. Report

Run `refine measure` again, with the same flags as the baseline. Then report:
- **Metrics:** lines, total_lines and tokens before→after, plus `time_s` if measured.
- **Mode:** the oracle (tests / golden / static) and the coverage (measured with which tool / conservative). Add the unmapped and failed cases, if any.
- **Accepted cuts**, one line each. These are the commit subjects.
- **Rejected cuts**, one line each, with the reason: which case or test failed, "golf", "slower", or "frozen interface" for a candidate the user declined.
- **Unverifiable:** line ranges the oracle never reaches, with a word on what would reach them.
- **Suggestions, not applied:** speedups that add code, and cuts in imported local modules (file and block).

## 9. Close

1. Run `git log --oneline BASE..HEAD`.
2. **If no cut was kept:** say so, run `git switch <base branch>`, and leave the empty branch for the user to delete.
3. **Otherwise,** squash the branch: run `git reset --soft BASE`, then `git commit -m "ablate: <file>: <N> cuts, <lines before>→<after> lines"`. Put the accepted cuts in the commit body.
4. **Never merge and never push.** Give the user the branch name and `git diff <base branch>...<branch>` to read before merging. The working files stay in `W`. Say so, so the user can delete them.
