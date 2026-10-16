## Context Usage

**Model:** claude-opus-5-5  
**Tokens:** 56.1k / 1m (6%)

### Estimated usage by category

| Category | Tokens | Percentage |
|----------|--------|------------|
| System prompt | 2.9k | 0.3% |
| System tools | 20.2k | 2.0% |
| MCP server instructions | 1.4k | 0.1% |
| MCP tools (deferred) | 146.9k | 14.7% |
| System tools (deferred) | 23.5k | 2.4% |
| Custom agents | 58 | 0.0% |
| Memory files | 57 | 0.0% |
| Skills | 3.3k | 0.3% |
| Messages | 28.1k | 2.8% |
| Free space | 910.9k | 91.1% |
| Autocompact buffer | 33k | 3.3% |

### MCP Tools

| Tool | Server | Tokens |
|------|--------|--------|
| mcp__claude_ai_Canva__comment-on-design | claude_ai_Canva | 429 |
| mcp__claude_ai_Canva__copy-design | claude_ai_Canva | 461 |
| mcp__claude_ai_Canva__create-brand-template-draft | claude_ai_Canva | 543 |
| mcp__claude_ai_Canva__create-design | claude_ai_Canva | 1.4k |
| mcp__claude_ai_Canva__create-design-from-brand-template | claude_ai_Canva | 478 |
| mcp__claude_ai_Canva__create-design-from-candidate | claude_ai_Canva | 775 |
| mcp__claude_ai_Canva__create-folder | claude_ai_Canva | 358 |
| mcp__claude_ai_Canva__create-upload-url | claude_ai_Canva | 527 |
| mcp__claude_ai_Canva__edit-design | claude_ai_Canva | 8.5k |
| mcp__claude_ai_Canva__export-design | claude_ai_Canva | 1.1k |
| mcp__claude_ai_Canva__generate-design | claude_ai_Canva | 3.8k |
| mcp__claude_ai_Canva__generate-design-structured | claude_ai_Canva | 2.4k |
| mcp__claude_ai_Canva__generate-image | claude_ai_Canva | 2.5k |
| mcp__claude_ai_Canva__get-assets | claude_ai_Canva | 446 |
| mcp__claude_ai_Canva__get-brand-template-dataset | claude_ai_Canva | 413 |
| mcp__claude_ai_Canva__get-create-design-async-job | claude_ai_Canva | 732 |
| mcp__claude_ai_Canva__get-design-dataset | claude_ai_Canva | 398 |
| mcp__claude_ai_Canva__get-export-formats | claude_ai_Canva | 388 |
| mcp__claude_ai_Canva__get-generate-image-job | claude_ai_Canva | 672 |
| mcp__claude_ai_Canva__get-motion-import-job-status | claude_ai_Canva | 365 |
| mcp__claude_ai_Canva__get-separate-image-layers-job | claude_ai_Canva | 487 |
| mcp__claude_ai_Canva__help | claude_ai_Canva | 618 |
| mcp__claude_ai_Canva__import-claude-motion-from-url | claude_ai_Canva | 620 |
| mcp__claude_ai_Canva__import-design-from-url | claude_ai_Canva | 1.1k |
| mcp__claude_ai_Canva__list-brand-kits | claude_ai_Canva | 530 |
| mcp__claude_ai_Canva__list-comments | claude_ai_Canva | 461 |
| mcp__claude_ai_Canva__list-folder-items | claude_ai_Canva | 580 |
| mcp__claude_ai_Canva__list-replies | claude_ai_Canva | 518 |
| mcp__claude_ai_Canva__merge-designs | claude_ai_Canva | 1.4k |
| mcp__claude_ai_Canva__move-item-to-folder | claude_ai_Canva | 364 |
| mcp__claude_ai_Canva__publish-brand-template | claude_ai_Canva | 361 |
| mcp__claude_ai_Canva__read-design | claude_ai_Canva | 1k |
| mcp__claude_ai_Canva__remove-background | claude_ai_Canva | 709 |
| mcp__claude_ai_Canva__reply-to-comment | claude_ai_Canva | 470 |
| mcp__claude_ai_Canva__request-outline-review | claude_ai_Canva | 1.9k |
| mcp__claude_ai_Canva__resize-design | claude_ai_Canva | 859 |
| mcp__claude_ai_Canva__resolve-shortlink | claude_ai_Canva | 373 |
| mcp__claude_ai_Canva__search-brand-templates | claude_ai_Canva | 825 |
| mcp__claude_ai_Canva__search-designs | claude_ai_Canva | 945 |
| mcp__claude_ai_Canva__search-folders | claude_ai_Canva | 593 |
| mcp__claude_ai_Canva__separate-image-layers | claude_ai_Canva | 851 |
| mcp__claude_ai_Canva__upload-asset-from-url | claude_ai_Canva | 472 |
| mcp__claude_ai_Claude_Docs__batch | claude_ai_Claude_Docs | 151 |
| mcp__claude_ai_Claude_Docs__create | claude_ai_Claude_Docs | 234 |
| mcp__claude_ai_Claude_Docs__delete | claude_ai_Claude_Docs | 314 |
| mcp__claude_ai_Claude_Docs__export | claude_ai_Claude_Docs | 298 |
| mcp__claude_ai_Claude_Docs__guide | claude_ai_Claude_Docs | 191 |
| mcp__claude_ai_Claude_Docs__query | claude_ai_Claude_Docs | 166 |
| mcp__claude_ai_Claude_Docs__read | claude_ai_Claude_Docs | 298 |
| mcp__claude_ai_Claude_Docs__update | claude_ai_Claude_Docs | 273 |
| mcp__claude_ai_Gmail__authenticate | claude_ai_Gmail | 165 |
| mcp__claude_ai_Gmail__complete_authentication | claude_ai_Gmail | 217 |
| mcp__claude_ai_Google_Calendar__authenticate | claude_ai_Google_Calendar | 173 |
| mcp__claude_ai_Google_Calendar__complete_authentication | claude_ai_Google_Calendar | 228 |
| mcp__claude_ai_Google_Drive__authenticate | claude_ai_Google_Drive | 170 |
| mcp__claude_ai_Google_Drive__complete_authentication | claude_ai_Google_Drive | 225 |
| mcp__claude_ai_Notion__notion-calendar-cancel-events | claude_ai_Notion | 479 |
| mcp__claude_ai_Notion__notion-calendar-create-events | claude_ai_Notion | 2.1k |
| mcp__claude_ai_Notion__notion-calendar-list-calendar-resources | claude_ai_Notion | 883 |
| mcp__claude_ai_Notion__notion-calendar-list-calendars | claude_ai_Notion | 302 |
| mcp__claude_ai_Notion__notion-calendar-list-contacts | claude_ai_Notion | 261 |
| mcp__claude_ai_Notion__notion-calendar-list-coworkers-events | claude_ai_Notion | 376 |
| mcp__claude_ai_Notion__notion-calendar-list-events | claude_ai_Notion | 365 |
| mcp__claude_ai_Notion__notion-calendar-update-events | claude_ai_Notion | 2.8k |
| mcp__claude_ai_Notion__notion-check-mcp-next-steps | claude_ai_Notion | 512 |
| mcp__claude_ai_Notion__notion-convert-page-to-skill | claude_ai_Notion | 288 |
| mcp__claude_ai_Notion__notion-create-attachment | claude_ai_Notion | 1.4k |
| mcp__claude_ai_Notion__notion-create-comment | claude_ai_Notion | 4.1k |
| mcp__claude_ai_Notion__notion-create-database | claude_ai_Notion | 1.6k |
| mcp__claude_ai_Notion__notion-create-file-upload | claude_ai_Notion | 663 |
| mcp__claude_ai_Notion__notion-create-folder | claude_ai_Notion | 499 |
| mcp__claude_ai_Notion__notion-create-pages | claude_ai_Notion | 3.5k |
| mcp__claude_ai_Notion__notion-create-view | claude_ai_Notion | 1.4k |
| mcp__claude_ai_Notion__notion-delete-comment | claude_ai_Notion | 335 |
| mcp__claude_ai_Notion__notion-delete-databases | claude_ai_Notion | 595 |
| mcp__claude_ai_Notion__notion-delete-pages | claude_ai_Notion | 543 |
| mcp__claude_ai_Notion__notion-download-attachment | claude_ai_Notion | 512 |
| mcp__claude_ai_Notion__notion-download-skill | claude_ai_Notion | 259 |
| mcp__claude_ai_Notion__notion-duplicate-page | claude_ai_Notion | 364 |
| mcp__claude_ai_Notion__notion-fetch | claude_ai_Notion | 1.5k |
| mcp__claude_ai_Notion__notion-get-async-task | claude_ai_Notion | 433 |
| mcp__claude_ai_Notion__notion-get-comments | claude_ai_Notion | 799 |
| mcp__claude_ai_Notion__notion-get-enabled-skills | claude_ai_Notion | 242 |
| mcp__claude_ai_Notion__notion-get-file-download-urls | claude_ai_Notion | 487 |
| mcp__claude_ai_Notion__notion-get-groups | claude_ai_Notion | 483 |
| mcp__claude_ai_Notion__notion-get-self | claude_ai_Notion | 230 |
| mcp__claude_ai_Notion__notion-get-session-status | claude_ai_Notion | 293 |
| mcp__claude_ai_Notion__notion-get-teams | claude_ai_Notion | 342 |
| mcp__claude_ai_Notion__notion-get-tool-access | claude_ai_Notion | 550 |
| mcp__claude_ai_Notion__notion-get-users | claude_ai_Notion | 593 |
| mcp__claude_ai_Notion__notion-list-favorite-pages | claude_ai_Notion | 273 |
| mcp__claude_ai_Notion__notion-list-page-backlinks | claude_ai_Notion | 535 |
| mcp__claude_ai_Notion__notion-list-private-pages | claude_ai_Notion | 296 |
| mcp__claude_ai_Notion__notion-list-recent-pages | claude_ai_Notion | 353 |
| mcp__claude_ai_Notion__notion-list-session-events | claude_ai_Notion | 459 |
| mcp__claude_ai_Notion__notion-list-shared-pages | claude_ai_Notion | 293 |
| mcp__claude_ai_Notion__notion-memory-search | claude_ai_Notion | 385 |
| mcp__claude_ai_Notion__notion-move-pages | claude_ai_Notion | 860 |
| mcp__claude_ai_Notion__notion-query-data-sources | claude_ai_Notion | 30.9k |
| mcp__claude_ai_Notion__notion-query-meeting-notes | claude_ai_Notion | 8.5k |
| mcp__claude_ai_Notion__notion-query-multiple-data-sources | claude_ai_Notion | 1.2k |
| mcp__claude_ai_Notion__notion-query-sessions | claude_ai_Notion | 6.8k |
| mcp__claude_ai_Notion__notion-read-session-event | claude_ai_Notion | 345 |
| mcp__claude_ai_Notion__notion-restore-pages | claude_ai_Notion | 344 |
| mcp__claude_ai_Notion__notion-search | claude_ai_Notion | 2.5k |
| mcp__claude_ai_Notion__notion-search-agents | claude_ai_Notion | 516 |
| mcp__claude_ai_Notion__notion-search-sessions | claude_ai_Notion | 310 |
| mcp__claude_ai_Notion__notion-send-message-to-session | claude_ai_Notion | 330 |
| mcp__claude_ai_Notion__notion-set-comment-reaction | claude_ai_Notion | 355 |
| mcp__claude_ai_Notion__notion-set-discussion-resolved | claude_ai_Notion | 401 |
| mcp__claude_ai_Notion__notion-show-advanced-analysis-next-steps | claude_ai_Notion | 322 |
| mcp__claude_ai_Notion__notion-spawn-session | claude_ai_Notion | 293 |
| mcp__claude_ai_Notion__notion-stop-session | claude_ai_Notion | 282 |
| mcp__claude_ai_Notion__notion-update-comment | claude_ai_Notion | 449 |
| mcp__claude_ai_Notion__notion-update-data-source | claude_ai_Notion | 5k |
| mcp__claude_ai_Notion__notion-update-enabled-skills | claude_ai_Notion | 427 |
| mcp__claude_ai_Notion__notion-update-folder | claude_ai_Notion | 630 |
| mcp__claude_ai_Notion__notion-update-page | claude_ai_Notion | 3.9k |
| mcp__claude_ai_Notion__notion-update-view | claude_ai_Notion | 815 |
| mcp__claude_ai_Notion__notion-upload-skill | claude_ai_Notion | 988 |
| mcp__claude_ai_Notion__notion-wait-session | claude_ai_Notion | 333 |
| mcp__ide__executeCode | ide | 250 |
| mcp__ide__getDiagnostics | ide | 134 |
| mcp__penpot__execute_code | penpot | 688 |
| mcp__penpot__export_shape | penpot | 365 |
| mcp__penpot__high_level_overview | penpot | 133 |
| mcp__penpot__penpot_api_info | penpot | 139 |

### Custom Agents

| Agent Type | Source | Tokens |
|------------|--------|--------|
| shrike | User | 58 |

### Memory Files

| Type | Path | Tokens |
|------|------|--------|
| AutoMem | /home/user/.claude/projects/-home-user-proj/memory/MEMORY.md | 57 |

### Skills

| Skill | Source | Tokens |
|-------|--------|--------|
| board:board-add | Plugin (board) | ~120 |
| board:board-init | Plugin (board) | ~120 |
| board:board-work | Plugin (board) | ~110 |
| taskflow:now-what | Plugin (taskflow) | ~150 |
| taskflow:task-breakdown | Plugin (taskflow) | ~130 |
| taskflow:task-loop | Plugin (taskflow) | ~90 |
| artifact-design | Built-in | ~70 |
| artifact-diagramming | Built-in | ~70 |
| artifact-capabilities | Built-in | ~250 |
| update-config | Built-in | ~240 |
| keybindings-help | Built-in | ~80 |
| code-review | Built-in | ~330 |
| simplify | Built-in | ~60 |
| fewer-permission-prompts | Built-in | ~60 |
| loop | Built-in | ~120 |
| run | Built-in | ~120 |
| plugin-authoring | Built-in | ~90 |
| init | Built-in | ~20 |
| security-review | Built-in | ~30 |
| built-in-browser | claude.ai sync | ~290 |
| chrome-browser | claude.ai sync | ~260 |
| computer-use | claude.ai sync | ~320 |
| deep-research | claude.ai sync | ~200 |

