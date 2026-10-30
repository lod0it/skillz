---
name: free-my-context
description: Guided trim of what Claude Code keeps resident in context for the current project: built-in tools, MCP servers, skills and plugins. Lists what is active, asks what to switch off round by round with defaults taken from real usage, and writes only the project's `.claude/settings.local.json` after one confirmation. Run with /taskflow:free-my-context.
argument-hint: "[area: tools | mcp | skills | plugins, optional]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, AskUserQuestion, Bash(python3 *), Bash(python *), Bash(git check-ignore *)
---

A conversation, one area at a time, like plan mode: list what is active, ask what to switch off, write once. Report and ask in the language of the conversation. `$ARGUMENTS`, if given, limits the session to that area.

**Writing style (ASD-STE100, in the language you write).** One idea per sentence: about 20 words for a description, 15 for a step. Active voice. Steps in the imperative, one action per step. Common words, one meaning per word, the same term for the same thing. Prose only: headings, field names, ids, commands, code and the parsed header lines stay as their format requires.

Nothing is written until the final confirmation (step 7). Writes go **only** to `<project>/.claude/settings.local.json`; this skill never edits the user or project settings.

The mechanical facts come from the Tool `free_my_context.py` next to this file (zero tokens, no model call): `python3 "${CLAUDE_PLUGIN_ROOT}/skills/free-my-context/free_my_context.py" …` (`python` when there is no `python3`). The judgement is yours.

## 1. Inventory

1. **What is active.** Built-in tools, deferred tools, MCP servers, skills and agents are in your own context: take the lists from there, not from memory. Group MCP tools by server (`mcp__<server>__*`); a connector that exposes only `authenticate` tools counts as one stub.
2. **What is already off.** Read, if they exist, `~/.claude/settings.json`, `<project>/.claude/settings.json`, `<project>/.claude/settings.local.json` and `.mcp.json`. Note `permissions.deny`, `skillOverrides` and `enabledPlugins`. Never offer again what is already switched off.
3. **Usage.** Run `free_my_context.py usage --scope here --project "$PWD"` and `… --scope all`. It prints calls per tool, MCP server and skill over the last 30 sessions.
4. Run `git check-ignore -q .claude/settings.local.json`; if it is **not** ignored, say so before round 1: the file would end up in git.

Show a short list of the active groups with the approximate item count (a tool count per MCP server, a skill count per plugin).

## 2. How to ask

Every round uses `AskUserQuestion`: at most 4 questions per call, 2–4 options each, a `header` of at most 12 characters.

- **Candidates** are the active items with 0 calls here. Items used here are not candidates; say how many were kept ("used here").
- Bundle related items into one option (a tool family, an MCP server, a plugin, a group of skills) so that a round fits the limits. Put the cost and the consequence in the option description.
- Ask "which to **switch off**?" with `multiSelect: true`. An unanswered or unselected item stays on; say so.
- The recommendation goes in the question text: name first what was never used in any project ("never used anywhere: recommended"). `AskUserQuestion` has no pre-selection.
- An area with no candidates is skipped with one line.
- Keep a running list of the chosen changes; do not write yet.

## 3. Round: built-in tools

Change: add the tool name to `permissions.deny`.

Never offer: `Bash`, `PowerShell`, `Read`, `Write`, `Edit`, `Skill`, `ToolSearch`, `AskUserQuestion`. Warn before offering these: `Agent`, `SendMessage`, `TaskStop` and `ListAgents` ("breaks subagents and `/taskflow:loop-it`"); `Artifact`, `ArtifactComments`, `ArtifactData` ("breaks the artifact skills"); `EnterPlanMode`/`ExitPlanMode`. `Glob` and `Grep` are safe while Bash is available.

## 4. Round: MCP servers

Change: add `mcp__<server>` to `permissions.deny` (the whole server). A server the project declares in `.mcp.json` is on purpose: say so and still let the user choose. A browser server also feeds the browser skills; mention it.

## 5. Round: skills

Change: `skillOverrides["<name>"]`. Ask first which skills or groups to trim, then one follow-up for the level, unless only one was chosen:

- `user-invocable-only` (recommended): 0 resident tokens, `/<name>` still works;
- `name-only`: the name stays visible, the description goes;
- `off`: gone, including `/<name>`.

Also offer the opposite, in the same call when it fits: skills that are not `on` but were used here, "turn back on?" (write `"on"`). A skill that ships with a plugin is named `plugin:skill`; if the override does not seem to take, switch the plugin off instead.

## 6. Round: plugins

Change: `enabledPlugins["<plugin>@<marketplace>"] = false`. Say how many skills, commands and agents the plugin brings, since they all go. Never offer `taskflow@skillz` (this skill lives in it).

## 7. Recap and confirmation

A table: area, item, from → to, and a count of what goes. Then one question: **Apply** (write), **Review an area** (repeat that round, recap again) or **Cancel** (write nothing).

## 8. Write

Write the plan to a JSON file in the scratchpad, `{"deny": [], "skills": {"name": "off"}, "plugins_off": []}`, and run `free_my_context.py apply .claude/settings.local.json <plan.json>` (`--dry-run` first when unsure). It merges without touching other keys or duplicating entries, copies the file to `settings.local.json.bak-<time>` first, and refuses the core tools. A deny that comes from the user or project settings cannot be undone from the local file: say so and leave it.

## 9. Close

Say what was written (file, number of changes, backup path) and that the changes apply to **new** sessions: `/clear` is not enough for tools and MCP servers. To undo: delete the entries, or restore the `.bak`. To see the real saving, start a new session and run `/context`.
