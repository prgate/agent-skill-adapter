# 0006. The transfer vocabulary reuses the gap outcome

## Context and Problem Statement

PRD §5 deferred naming the grades a transferred property gets and the verdicts a file gets, until
the environment descriptions existed. They now exist, and the converter cannot be written without
those names: every property it finds needs a grade, and the exit code table (FR-27) needs a rule
that turns grades into one run outcome.

A vocabulary for grading one entry is already in the repository and already tested:
`envspec.gaps.Outcome` — `reproduced` / `missing` / `unknown` / `out-of-scope` — computed by
`compare()` over two descriptions. ADR-0003 explicitly rejected "reuse the transfer-grading
vocabulary from PRD §5", so reusing anything across that line has to be argued, not assumed.

## Decision Outcome

A property of a skill is graded with `envspec.gaps.Outcome`. No new vocabulary is introduced for it.

A file gets a `Verdict` — `clean` / `lossy` / `undecidable` — and the run outcome is the worst file
verdict, in the same vocabulary. `Verdict` is the single new name PRD §5 introduces. A property's
grade plus its origin (`specification` / `extension`, also an existing type) determines its verdict
by the table in PRD §5.2; `unknown` on a specification field is `undecidable`, `unknown` on a
vendor extension is `lossy`.

The dispute with ADR-0003 is real and is resolved, not stepped around. ADR-0003 rejected grading
*vendor documentation* with a transfer vocabulary: `Support` says what a vendor documented about
its own environment, which is not a statement about transfer. That stands untouched — `Support`
keeps its three values and its meaning. What is reused here is `Outcome`, which is not `Support`:
`Outcome` is already the result of comparing two descriptions — "does the target reproduce this
entry" — and that is exactly the question the converter asks about a skill property. ADR-0003 also
wrote that collapsing the two would commit the project to a §5 decision not yet made; the decision
is made now, and this is it.

## Considered Options

- **Name a third vocabulary in §5 from scratch.** Rejected: the same concept would then have two
  names, and every module that touches both comparison and conversion would carry a translation
  table. The §5 decision would have to state the mapping to `Outcome` anyway, which is the mapping
  written out as a fourth artifact instead of avoided.
- **Grade properties with `Support` (`supported` / `unsupported` / `unknown`).** Rejected: this is
  the reuse ADR-0003 forbids, and it loses information — `Support` is a statement about one
  environment, so it cannot express "the target denies this" as distinct from "our source declares
  it", and it has no room for `out-of-scope`.
- **One flat vocabulary for property, file and run.** Rejected: a property can be `out-of-scope`
  and a file cannot; a file can be `lossy` and a single property either transfers or does not.
  Merging them means every reader of a value must first ask what it was attached to.
- **A separate type for the run outcome, distinct from the file verdict.** Rejected: the run
  outcome is defined as the worst file verdict — the same three values with the same meanings. A
  second type would be an alias with a different name, and aliases drift.
- **Add a fourth `Verdict` value `blocked` now, for FR-36.** Rejected: no row of the assembly table
  produces it in this slice. A value nothing emits is a branch nothing exercises; it will be added
  together with the rule that defines a prohibition, and tested then.

## Consequences

`Outcome` now has two callers — the gap report and the converter — so changing it is no longer a
local edit inside `gaps`. That is the intended cost: one vocabulary, one place to change it.

Two vocabularies still have to be kept in step: when FR-36 introduces a prohibition, `Verdict`
grows a fourth value and the assembly table grows rows, while `Outcome` should not move — the
prohibition is a property of our transfer rules, not of what the target documents. Anyone adding a
value to `Outcome` instead is putting a transfer decision into a record about vendor documentation,
which is the mistake ADR-0003 was written to prevent.

Exit code 2 (transfer forbidden, FR-27) has no producer until then. The table in PRD §5.2 covers
every combination it can reach, and the codes it produces are 0, 1 and 3.
