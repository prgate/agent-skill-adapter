# 0001. Environment descriptions as per-version YAML files under `specs/<vendor>/`

## Context and Problem Statement

Environment knowledge must live in a data file rather than in code (FR-1), be read by a human
during review (FR-10), and hold several versions of the same environment side by side (FR-5).

## Decision Outcome

Each environment description is one YAML file at `specs/<vendor>/<environment>-<version>.yaml`
(`specs/anthropic/claude-code-2.1.yaml`, `specs/google/antigravity-2.0.yaml`). The version is part
of the file name, so a new version is a new file next to the old one, each with its own
`checked_at`. Parsing uses the already-declared `pyyaml`; the shape is validated by `pydantic>=2`.

## Considered Options

- **JSON.** Rejected: the artefact is accepted by reading a diff, and JSON has no comments, quotes
  every key, and turns a one-line edit inside a nested list into bracket noise. Readability of the
  review diff is the property that decides here.
- **One file per environment with an internal map of versions.** Rejected: every new version
  rewrites lines of the previous one in the same file, which is exactly what R08 forbids — versions
  must sit side by side, not overwrite each other — and it makes "which description did this run
  use" a question about file content instead of file identity.
- **TOML or a custom format.** Rejected: a new dependency for no gain (CFP level 3), while
  `pyyaml` is already in the project through skill frontmatter.

## Consequences

Version selection depends on file naming and directory layout: a renamed or misplaced file is a
description that no longer exists for the loader, and nothing else will notice. YAML's own traps
(implicit booleans, auto-parsed dates) are ours to catch in schema validation rather than at parse
time. The number of files grows monotonically — old versions are never deleted, because deleting
one removes the ability to reproduce a past transfer.
