# 0005. Documented ceilings without a size unit are recorded as capabilities

## Context and Problem Statement

The plan assumed `limits:` would hold the documented ceilings of an environment. Tasks 03 and 04 hit
real ceilings that have no size unit — 20 concurrent subagents in Claude Code, 10 levels of nesting
in Antigravity — while FR-32 fixes `Limit.unit` to `bytes` / `characters` / `tokens`.

## Decision Outcome

`limits:` holds size limits only. A documented ceiling of another nature is recorded as an ordinary
capability of the environment, with the number stated in `note`.

## Considered Options

- **Extend the unit vocabulary with `agents`, `levels`, and whatever comes next.** Rejected: FR-32
  closes that vocabulary, and the closed vocabulary is what makes a limit comparable between two
  environments at all. An open one turns `limits` into a bag of incomparable numbers.
- **Drop the facts that do not fit.** Rejected: the vendor documentation asserts them, and a
  documented ceiling that the target does not match is precisely the kind of gap the report exists
  to name. Losing it silently is the worst available outcome.
- **Add a third section for non-size ceilings.** Rejected: a new top-level list and its own schema
  for two facts, when an existing capability record already carries source, support and a note.

## Consequences

The number sits in free-text `note`, so it is not machine-comparable: nothing will automatically
flag that the source environment allows 20 concurrent subagents and the target allows 10. A real,
documented incompatibility is therefore visible to a reader but invisible to the computed gap list.
Making it comparable later means a typed field and a migration of these records — do that when a
second such ceiling actually needs comparing, not before.
