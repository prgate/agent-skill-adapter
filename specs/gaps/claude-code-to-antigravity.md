# What google/antigravity does not reproduce from anthropic/claude-code

This list is computed, not written: it is the output of comparing the two environment descriptions in `specs/`, entry by entry, matched by id. Only this paragraph is written by hand. `reproduced` means the target's own documentation says it supports the entry; `missing` means that documentation says, in words, that it does not; `unknown` means the documentation is silent or carries no such entry -- silence is never read as a denial. An empty list -- nothing missing and nothing unknown -- would mean the transfer is a file copy and this product is not needed. The last column splits `unknown` in two: an entry the target description does not carry at all is evidence about the target, while an entry it carries without a verdict is the limit of our reading of its documentation -- adding the two together would let our own incompleteness pass for a finding.

- Source: `anthropic/claude-code` >=2.1.0,<2.2.0, checked 2026-09-14
- Target: `google/antigravity` >=2.0.0,<3.0.0, checked 2026-09-14

| outcome | entries | of which absent from the target description |
| --- | --- | --- |
| reproduced | 22 | 0 |
| missing | 0 | 0 |
| unknown | 73 | 8 |

## Entries

| id | kind | source | target | outcome | what each side documents |
| --- | --- | --- | --- | --- | --- |
| agent-memory.project | layout | supported | unknown | unknown | .claude/agent-memory/<name>/ -> (no matching entry in the target description) |
| agent-memory.user | layout | supported | unknown | unknown | ~/.claude/agent-memory/<name>/ -> (no matching entry in the target description) |
| agents.project | layout | supported | supported | reproduced | .claude/agents/*.md -> .agents/agents/ |
| agents.user | layout | supported | supported | reproduced | ~/.claude/agents/*.md -> ~/.gemini/config/agents/ |
| commands.project | layout | supported | unknown | unknown | .claude/commands/*.md -> (no matching entry in the target description) |
| commands.user | layout | supported | unknown | unknown | ~/.claude/commands/*.md -> (no matching entry in the target description) |
| hook.event.ConfigChange | hook-event | supported | unknown | unknown | when a configuration file changes during a session -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.CwdChanged | hook-event | supported | unknown | unknown | when the working directory changes -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.DirectoryAdded | hook-event | supported | unknown | unknown | when a working directory is added mid-session via /add-dir -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.Elicitation | hook-event | supported | unknown | unknown | when an MCP server requests user input during a tool call -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.ElicitationResult | hook-event | supported | unknown | unknown | after a user responds to an MCP elicitation, before the reply reaches the server -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.FileChanged | hook-event | supported | unknown | unknown | when a watched file changes on disk; matcher selects the filenames -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.InstructionsLoaded | hook-event | supported | unknown | unknown | when a CLAUDE.md or .claude/rules/*.md file is loaded into context -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.MessageDisplay | hook-event | supported | unknown | unknown | while assistant message text is displayed -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.Notification | hook-event | supported | unknown | unknown | when Claude Code sends a notification -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PermissionDenied | hook-event | supported | unknown | unknown | when auto mode denies a tool call -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PermissionRequest | hook-event | supported | unknown | unknown | when a tool call needs a permission decision -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PostCompact | hook-event | supported | unknown | unknown | after context compaction completes -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PostModelSwitch | hook-event | supported | unknown | unknown | after the session model changes -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PostToolBatch | hook-event | supported | unknown | unknown | after a batch of parallel tool calls resolves, before the next model call -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PostToolUse | hook-event | supported | supported | reproduced | after a tool call succeeds -> Fires after a tool completes; the matcher targets the tool name. |
| hook.event.PostToolUseFailure | hook-event | supported | unknown | unknown | after a tool call fails -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PreCompact | hook-event | supported | unknown | unknown | before context compaction -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PreModelSwitch | hook-event | supported | unknown | unknown | before a requested model switch is applied; can block the switch -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.PreToolUse | hook-event | supported | supported | reproduced | before a tool call executes; can block it -> Fires before a tool is executed; the matcher targets the tool name. |
| hook.event.SessionEnd | hook-event | supported | unknown | unknown | when a session terminates -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.SessionStart | hook-event | supported | unknown | unknown | when a session begins or resumes -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.Setup | hook-event | supported | unknown | unknown | on --init-only, or --init / --maintenance in -p mode -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.Stop | hook-event | supported | supported | reproduced | when Claude finishes responding -> Fires when the execution loop terminates; the matcher is ignored. |
| hook.event.StopFailure | hook-event | supported | unknown | unknown | when the turn ends due to an API error -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.SubagentStart | hook-event | supported | unknown | unknown | when a subagent is spawned -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.SubagentStop | hook-event | supported | unknown | unknown | when a subagent finishes -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.TaskCompleted | hook-event | supported | unknown | unknown | when a task is being marked as completed -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.TaskCreated | hook-event | supported | unknown | unknown | when a task is being created via TaskCreate -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.TeammateIdle | hook-event | supported | unknown | unknown | when an agent team teammate is about to go idle -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.UserPromptExpansion | hook-event | supported | unknown | unknown | when a user-typed command expands into a prompt; can block the expansion -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.UserPromptSubmit | hook-event | supported | unknown | unknown | when you submit a prompt, before Claude processes it -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.WorktreeCreate | hook-event | supported | unknown | unknown | when a worktree is being created; replaces default git behavior -> Absent from the supported-events table; the page does not say it is unavailable. |
| hook.event.WorktreeRemove | hook-event | supported | unknown | unknown | when a worktree is being removed at session exit or subagent finish -> Absent from the supported-events table; the page does not say it is unavailable. |
| hooks.managed | layout | supported | unknown | unknown | managed-settings.json -> (no matching entry in the target description) |
| hooks.plugin | layout | supported | supported | reproduced | hooks/hooks.json -> plugins/<plugin-name>/hooks.json |
| hooks.project | layout | supported | supported | reproduced | .claude/settings.json -> .agents/hooks.json |
| hooks.project-local | layout | supported | unknown | unknown | .claude/settings.local.json -> (no matching entry in the target description) |
| hooks.user | layout | supported | supported | reproduced | ~/.claude/settings.json -> ~/.gemini/config/hooks.json |
| settings.file.claude-json | settings-file | supported | unknown | unknown | ~/.claude.json — app state Claude Code writes for itself; sign-in, MCP servers, per-project state -> The counterpart topic is an app-state file the tool writes for itself (sign-in, MCP servers, per-project state). The settings page names no such file either way. |
| settings.file.managed | settings-file | supported | unknown | unknown | managed-settings.json and other managed sources; nothing you set overrides it -> No administrator-managed policy file is named on this page; nor is one ruled out. |
| settings.file.plugin-hooks | settings-file | supported | supported | reproduced | a plugin's hooks/hooks.json — hooks bundled with the plugin, active while it is enabled -> A plugin's own `hooks.json` at the plugin root, loaded while the plugin is active. |
| settings.file.project | settings-file | supported | unknown | unknown | .claude/settings.json — everyone working in the folder that contains it -> Project settings are documented as a settings panel, not as a file. No checked-in, project-scoped settings file is named, and the page does not say one is unavailable. |
| settings.file.project-local | settings-file | supported | unknown | unknown | .claude/settings.local.json — you, in this one project only; kept out of git -> No per-checkout, git-ignored settings override is named; nor is one ruled out. |
| settings.file.user | settings-file | supported | supported | reproduced | ~/.claude/settings.json — you, in every project on this machine -> `~/.gemini/antigravity-cli/settings.json` — you, on this machine, in every workspace. Written sparsely: only values that differ from the defaults reach disk. |
| settings.project | layout | supported | unknown | unknown | .claude/settings.json -> (no matching entry in the target description) |
| settings.project-local | layout | supported | unknown | unknown | .claude/settings.local.json -> (no matching entry in the target description) |
| settings.skillListingBudgetFraction | settings-file | supported | unknown | unknown | share of the context window reserved for the skill listing; default 0.01, that is 1% of the context window -> No setting that caps the share of the context window spent on the skill listing is named among the four settings categories, and none is ruled out. |
| settings.user | layout | supported | supported | reproduced | ~/.claude/settings.json -> ~/.gemini/antigravity-cli/settings.json |
| skill.frontmatter.agent | skill-field | supported | unknown | unknown | subagent type used when context: fork is set -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.allowed-tools | skill-field | supported | unknown | unknown | tools pre-approved for the invoking turn; the grant clears on the next user message -> The frontmatter table lists only `name` and `description`. It does not state that a tool-restriction field is rejected or ignored, so this is silence, not a denial. |
| skill.frontmatter.argument-hint | skill-field | supported | unknown | unknown | autocomplete hint for expected arguments -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.arguments | skill-field | supported | unknown | unknown | named positional arguments for $name substitution; space-separated string or YAML list -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.background | skill-field | supported | unknown | unknown | only with context: fork; false waits for the forked subagent in the invoking turn -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.compatibility | skill-field | unsupported | unknown | unknown | Agent Skills spec field, string up to 500 characters: "Claude Code accepts the field but doesn't act on it" -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.context | skill-field | supported | unknown | unknown | fork runs the skill in a forked subagent context -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.description | skill-field | supported | supported | reproduced | what the skill does and when to use it; falls back to the first non-empty content line -> Required; this is what the agent sees when deciding whether to apply the skill. |
| skill.frontmatter.disable-model-invocation | skill-field | supported | unknown | unknown | prevents automatic loading; since v2.1.196 also blocks scheduled-task invocation -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.disallowed-tools | skill-field | supported | unknown | unknown | tools removed from the pool while the skill is active; cannot remove EndConversation -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.effort | skill-field | supported | unknown | unknown | low \| medium \| high \| xhigh \| max; available levels depend on the model -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.hooks | skill-field | supported | unknown | unknown | hooks registered on invocation and kept for the rest of the session -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.license | skill-field | unsupported | unknown | unknown | Agent Skills spec field: "Claude Code accepts the field but doesn't act on it" -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.metadata | skill-field | unsupported | unknown | unknown | free-form YAML map for your own tooling: "Claude Code doesn't act on its contents, and drops a value that isn't a map" -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.model | skill-field | supported | unknown | unknown | model override for the rest of the turn; accepts /model values or inherit -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.name | skill-field | supported | supported | reproduced | display name in skill listings; defaults to the directory name -> Optional; defaults to the folder name when omitted. |
| skill.frontmatter.paths | skill-field | supported | unknown | unknown | glob patterns that gate automatic activation -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.shell | skill-field | supported | unknown | unknown | bash (default) or powershell for inline !`command` blocks -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.user-invocable | skill-field | supported | unknown | unknown | false hides the skill from the / menu; default true -> Not named by the frontmatter table; the page says nothing about it either way. |
| skill.frontmatter.when_to_use | skill-field | supported | unknown | unknown | extra trigger context appended to description in the skill listing -> Not named by the frontmatter table; the page says nothing about it either way. |
| skills.project | layout | supported | supported | reproduced | .claude/skills/<name>/SKILL.md -> <workspace-root>/.agents/skills/ |
| skills.user | layout | supported | supported | reproduced | ~/.claude/skills/<name>/SKILL.md -> ~/.gemini/config/skills/ |
| subagent.frontmatter.background | subagent-field | supported | unknown | unknown | true keeps the subagent in the background even when Claude asks for the foreground -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.color | subagent-field | supported | unknown | unknown | red \| blue \| green \| yellow \| purple \| orange \| pink \| cyan -> Not named by the frontmatter table, and not stated to be rejected. |
| subagent.frontmatter.description | subagent-field | supported | supported | reproduced | required; when Claude should delegate to this subagent -> Required string; used by the planner to decide when to delegate. |
| subagent.frontmatter.disallowedTools | subagent-field | supported | unknown | unknown | tools denied; an entry with a specifier still removes the whole tool -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.effort | subagent-field | supported | unknown | unknown | low \| medium \| high \| xhigh \| max; available levels depend on the model -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.experimental | subagent-field | supported | unknown | unknown | map of experimental options; cacheTtl accepts 5m or 1h -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.hooks | subagent-field | supported | unknown | unknown | lifecycle hooks scoped to this subagent; ignored for plugin subagents -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.initialPrompt | subagent-field | supported | unknown | unknown | auto-submitted first user turn when the agent runs as the main session agent -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.isolation | subagent-field | supported | unknown | unknown | worktree runs the subagent in a temporary git worktree -> Not a frontmatter property. Workspace isolation (`inherit`, `branch`, `share`) is chosen per invocation by the caller, not declared in the agent file. |
| subagent.frontmatter.maxTurns | subagent-field | supported | unknown | unknown | agentic turn cap; marking the output as partial requires v2.1.246 or later -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.mcpServers | subagent-field | supported | supported | reproduced | server names or inline definitions; ignored for plugin subagents -> Object list of MCP servers configured for this subagent. |
| subagent.frontmatter.memory | subagent-field | supported | unknown | unknown | persistent memory scope: user \| project \| local -> Not named by the frontmatter property table, and not stated to be rejected. |
| subagent.frontmatter.model | subagent-field | supported | supported | reproduced | sonnet \| opus \| haiku \| fable \| full model id \| inherit -> Model tier: `inherit`, `flash` or `pro`. Not a model identifier. |
| subagent.frontmatter.name | subagent-field | supported | supported | reproduced | required; lowercase letters and hyphens, no ':'; hooks receive it as agent_type -> Required string; the unique identifier of the custom agent. |
| subagent.frontmatter.permissionMode | subagent-field | supported | unknown | unknown | default \| acceptEdits \| auto \| dontAsk \| bypassPermissions \| plan \| manual; the manual alias needs v2.1.200+; ignored for plugin subagents -> Not named by the frontmatter property table. `commandExecutionPolicy` governs shell auto-execution only; whether a broader permission mode exists is not stated. |
| subagent.frontmatter.skills | subagent-field | supported | supported | reproduced | skills preloaded into the subagent context at startup, full content injected -> String list of skill paths or plugin dependencies (`skills` / `plugins`). |
| subagent.frontmatter.tools | subagent-field | supported | supported | reproduced | tools the subagent may use; inherits all subagent tools when omitted -> String list of permitted tools, spelled in Antigravity tool names. |
| subagent.limit.concurrent | subagent-field | supported | unknown | unknown | 20 running subagents per session by default; spawning another with the Agent tool then fails with Concurrent subagent limit reached -> The one ceiling this section states as strictly enforced is the nesting depth. It names no cap on the number of concurrently running subagents, and rules none out. |
| subagent.limit.spawn-depth | subagent-field | supported | supported | reproduced | 3 layers of subagents below the main conversation by default; CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH changes it, 1 turns nesting off -> A maximum nesting depth of 10 levels of subagents beneath the primary agent is strictly enforced, to prevent runaway recursion or resource exhaustion. |
