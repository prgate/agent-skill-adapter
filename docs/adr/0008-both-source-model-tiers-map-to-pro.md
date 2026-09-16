# 0008. Both source model tiers map to `pro`

## Context and Problem Statement

A Claude Code subagent names its model tier in the frontmatter key `model`. Antigravity names a
closed set for the same field — `inherit`, `flash`, `pro` — and its description records that set
(`specs/google/antigravity-2.0.yaml`, `subagent.frontmatter.model`). The source spellings `opus`
and `sonnet` are outside it, so a subagent carried across unchanged declares a value the target
does not accept, which is how a subagent ends up invisible to the environment that loaded it.

The converter refuses to invent a counterpart (FR-12), so somebody has to decide what `opus` and
`sonnet` become, and the decision has to be written down where the next reader finds it. The
target documents no pairing with another vendor's tiers — no vendor documents another vendor's
vocabulary — so this is our decision and not a fact read out of either description.

## Decision Outcome

`opus` and `sonnet` both map to `pro`. The roles that write code and fix production bugs are worth
more to keep at their quality than to keep at their price, and `flash` is the cheaper tier.

The mapping lives in `rules/claude-code-to-antigravity-1.0.yaml` under
`value_maps.subagent.frontmatter.model`, versioned by `rules_version` apart from either
description (ADR-0002 keeps a description a record of what a vendor documents; this is not that).
Every applied mapping appears in the report as what was there, what it became and by what rule, and
the report names `rules_version` beside both environment versions, so the run can be repeated.

The converter itself names neither tier. It asks the target description for the closed set, finds
the written value outside it, and asks the rules file for the counterpart; a target that documents
no set for the field is translated against nothing and earns an `unknown` row saying so.

## Considered Options

- **`sonnet` → `flash`, `opus` → `pro`, matching the tiers by their place in each vendor's price
  list.** Rejected: the two ladders are not the same ladder, and the cost of guessing wrong is
  asymmetric. A set whose subagents review diffs and repair failing tests would quietly run them on
  the cheaper tier after a transfer nobody was asked about; the opposite error costs money, which
  the owner of the set can see in a bill and change in one line. A downgrade is visible only as
  worse work.
- **`inherit` for both, deferring the choice to whatever the workspace is set to.** Rejected: the
  source set states a tier per subagent on purpose, and collapsing every one of them onto the
  workspace default discards that statement while reporting a clean transfer. It is a translation
  that loses the thing being translated.
- **No mapping at all: leave the value and report it.** Rejected for this pair and kept for every
  other: this is exactly what the converter does where the rules name no counterpart, and it is the
  right answer when nobody has decided. Here somebody has, and leaving a documented decision out of
  the rules file would make every run of a real set lossy over a question already settled.

## Consequences

A transfer of a set whose subagents are all `opus` or `sonnet` is clean on the `model` field, and
the report shows three lines of work rather than a field that silently agreed.

The pair is data, not code: a later Antigravity tier, or a different opinion about the trade, is an
edit to the rules file and a bump of `rules_version`, with no change to the converter and no change
to either description. A reader who wants to know what a past run did reads the `rules_version` the
report carries.

Tool names travel through the same table and are not covered by this decision: the target documents
its own tool set rather than a closed value set on the field, so `Read`, `Grep` and `Bash` have
documented counterparts and every other source name has none, crosses as it was written, and earns
a row (spec Decisions §2).
