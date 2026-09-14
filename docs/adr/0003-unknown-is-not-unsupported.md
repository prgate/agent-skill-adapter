# 0003. Documentation silence is `unknown`, never `unsupported`

## Context and Problem Statement

The gap list between Claude Code and Antigravity is the go/no-go criterion for the whole product
(FR-48), and the target vendor's documentation may simply say nothing about subagents, hooks or
permissions.

## Decision Outcome

A capability record carries `supported` / `unsupported` / `unknown`, describing what the vendor
documentation states about the environment — not how well a feature transfers. `capability(spec, id)`
returns `UNKNOWN` for an id that has no record at all. The computed gap list grades every source
record as `reproduced` / `missing` / `unknown`, where `missing` is reserved for an explicit denial in
the target documentation; an absent record yields `unknown`, never `missing`.

## Considered Options

- **Absent record means "not supported".** Rejected: it would manufacture the very gap list that
  justifies building the product, so the go/no-go criterion would confirm itself. Distinguishing
  "the documentation is silent" from "the documentation says no" is the entire reason sources are
  collected at all.
- **Absent record means "supported".** Rejected: that is the permissive answer on missing knowledge,
  and missing knowledge must never produce a permissive result (NFR-3).
- **Reuse the transfer-grading vocabulary from PRD §5.** Rejected: that vocabulary grades properties
  of the *transfer*, this one grades what the vendor *documents*. Collapsing them would commit the
  project to a §5 decision that has not been made yet, in a file written before the core exists.
- **Two-valued support plus a free-text note.** Rejected: the third state then lives in prose and
  cannot be counted, while the gap list must be computed rather than read.

## Consequences

The gap list may come back mostly `unknown` — an honest answer that does not settle the go/no-go
question. Re-running the computation will not improve it; only reading more documentation or testing
the environment will, and that is human work proportional to the number of `unknown` records. From
the report alone, "nobody looked" and "we looked and the docs are silent" read the same; telling
them apart means going back to `sources` and `checked_at`. Anyone later tempted to default the
absent record to `unsupported` to get a fuller-looking report is destroying the criterion, not
improving it.
