# Claude Code environment spec — changelog

Each published version directory is immutable. A correction is a new version
next to the old one; `versions.lock` pins the content of every published
directory.

## 1.0.0 — 2026-09-13

First published document. `extends: agentskills@1.0.0`; portability of each
`skillFields` entry is derived against that baseline, never authored (design
D8).

- `environment.versions: ">=2.1.218,<2.2.0"` — the documentation states no
  overall version range for the frontmatter shape it describes. `2.1.218` is
  the lowest version any recorded `skillFields` entry's `since` names
  (`background`, "Requires Claude Code v2.1.218 or later"); the upper bound
  is the next minor. Unrelated version notes elsewhere on the same pages
  (tool-behavior changes, UX fixes) do not move this bound.
- `skillFields`: the 20 keys in the "Frontmatter reference" table
  (`code.claude.com/docs/en/skills#frontmatter-reference`) — `name`,
  `description`, `when_to_use`, `argument-hint`, `arguments`,
  `disable-model-invocation`, `user-invocable`, `allowed-tools`,
  `disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`,
  `hooks`, `paths`, `shell`, `metadata`, `license`, `compatibility`. All 20
  share one anchor, so they currently share one provenance hash; a future
  version can split the table's anchor by row if the documentation adds one.
  `isolation`, named in the PRD, is not in this table and is not recorded.
- `frontmatter`: omitted. Claude Code's own unknown-field handling for
  `SKILL.md` is not documented anywhere in the snapshot — the "hard error"
  text on the same page is scoped to claude.ai uploads, the Skills API, and
  `package_skill.py`, not to Claude Code reading a local file.
- `layout`: `skillFile: [SKILL.md]`; `skillsDirs` is `.claude/skills`
  (project) and `~/.claude/skills` (user), from the "Where skills live"
  table. The documentation never mentions a generic `.agents/skills`
  directory for Claude Code, so it is not recorded; `conventionalDirs` is
  empty because Claude Code states no `references/`/`assets/` convention the
  way the baseline specification does — `scripts/` appears only in one
  illustrative example, not as a stated convention.
- `tools`: 45 names from the table under `tools-reference`'s single page
  heading (no closer heading exists above the table in the rendered page).
- `limits`: `skill_file_lines` (500, recommended) and `catalog_entry_chars`
  (1536, hard — the truncation is automatic, though the cap is configurable).
  Other numeric mentions on the page (compaction token budgets, listing
  character budget as a percentage) either use a unit outside
  `bytes|chars|tokens|lines` or are not stated as a limit on authored
  content, and are not recorded (design's Open point #2).
- `invisibleSources`: `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, and
  `managed-settings.json` — each lives outside any project's repository.
  Project-scoped files (`.claude/settings.json`, `.claude/settings.local.json`,
  project `CLAUDE.md`) are inside the repository tree and are not recorded
  here.
- Deferred to 1.1.0: subagent fields. Deferred to 1.2.0: hooks records (the
  general hook-configuration format; the SKILL.md frontmatter key `hooks`
  itself is still recorded above, since it is a documented frontmatter
  field, not a hooks record).
