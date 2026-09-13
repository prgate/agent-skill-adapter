# Agent Skills baseline spec — changelog

Each published version directory is immutable. A correction is a new version
next to the old one; `versions.lock` pins the content of every published
directory.

## 1.0.0 — 2026-09-13

First published document. Baseline for `spec.extends`; the portability of every
other environment's frontmatter is derived from it (design D8).

- Upstream: `agentskills/agentskills` at commit
  `69ef37e9424c0a7ea9dd2293b559e43ec8176379`; the repo has no tags, so the
  commit is the version. Recorded in
  `metadata.annotations.adapter.prgate.io/upstream-commit`.
- `environment.versions: "*"` — the open specification is not versioned per
  environment release.
- `skillFields`: the six keys the specification defines (`name`,
  `description`, `license`, `compatibility`, `metadata`, `allowed-tools`).
- `frontmatter.unknownFields: reject` — the behaviour of the reference
  validator (`skills-ref`, `ALLOWED_FIELDS`). The client guide's
  warn-and-load recommendation is a different claim and is not recorded here.
- `layout`: the specification documents only the contents of one skill
  directory (`SKILL.md`, optional `scripts/`, `references/`, `assets/`), not
  where skill directories are discovered on disk. `layout.skillsDirs` is
  therefore empty, and `skillFile` is `[SKILL.md]` — the specification never
  mentions a lowercase `skill.md` alternative.
- `limits`: the three recommendations under progressive disclosure.
- `tools`, `invisibleSources`: absent — the specification names neither.
