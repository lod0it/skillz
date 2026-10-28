---
name: upgrade-repos
description: Brings taskflow repos with an older layout up to the installed taskflow (current Tool paths, tasks/LESSONS.md with Project and General sections), several repos in one pass, never pushing. Use when the user runs /taskflow:upgrade-repos, or when the session start hint says repos near this session use an older taskflow and the user agrees to upgrade.
argument-hint: "[folder holding the repos, default: the current folder]"
allowed-tools: AskUserQuestion, Bash(python3 ${CLAUDE_SKILL_DIR}/upgrade_repos.py *), Bash(python ${CLAUDE_SKILL_DIR}/upgrade_repos.py *)
---

Upgrade old taskflow repos. The script does the work at zero tokens (`init`, `migrate-tool`, `check`, one local commit per repo); you scan, ask, run it and report. Report in the language of the conversation. `$ARGUMENTS`, if given, is the folder to scan.

## 1. Scan

Run `python3 ${CLAUDE_SKILL_DIR}/upgrade_repos.py scan [folder]` (`python` on Windows when `python3` is missing). It lists the taskflow repos at the folder, in its children and in its siblings, as:

- `ok`: nothing to do;
- `auto`: `init` + `migrate-tool` fix it;
- `manual`: a pre-pipeline layout (`LEGACY`): the script does not touch it, it needs `/taskflow:break-it-down` in that repo (migrate branch).

When no repo needs work, say so and stop.

## 2. Ask

One `AskUserQuestion`, repos named with their reasons: **Upgrade all** (`auto` repos, with a commit each), **Dry run only** (show what each needs, change nothing), **Choose repos**, **Not now** (run `snooze` for them so the session hint stops until the next taskflow version). A repo with uncommitted changes is skipped by the script and reported as such.

## 3. Apply

`python3 ${CLAUDE_SKILL_DIR}/upgrade_repos.py apply <repo>... --commit` (without `--commit` when the user wants to review the diff first). Report one line per repo from its output: `upgraded`, `skipped`, `manual`, `check-failed`.

## 4. Push

The script never pushes. List the upgraded repos and ask whether to push each; pushing is outward-facing, so only the ones the user names, with plain `git push`, never forced.
