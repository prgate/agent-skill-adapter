# 0007. Hooks are split in the environment description, not special-cased in the converter

## Context and Problem Statement

PRD §5 deferred what to do with skills that rely on hooks: forbid the transfer, or move the check
outside into a git hook or a CI step. Both options assume the converter decides something about
hooks.

The question exists because one description entry answers two things at once. The Claude Code hook
lifecycle states two of them about `hook.event.PreToolUse`: that it fires before a tool call
executes, and that a hook of it can stop that call — an event, and an authority to deny the action.
Antigravity documents the same event, and says nothing about what a non-zero exit code from a hook
does. Graded as one entry, the pair is unanswerable — the target reproduces half of it.

## Decision Outcome

The entry is split in the descriptions. The event stays `hook.event.*`. The authority to deny
becomes its own entry, `hook.decision.block`, of a new `Capability.kind` value `hook-decision`,
with its own source anchor and hash on each side. Claude Code declares it supported; Antigravity
leaves it `unknown`, because its documentation is silent.

Nothing further is needed. Hooks are a vendor extension, so the origin rule already decided in
PRD §5.2 applies unchanged: `unknown` on an extension is `lossy` — transfer with a note, exit code
1. The event transfers where the target documents it; the note says the target does not document
what a non-zero exit code does, so blocking is not confirmed. The word "hook" appears in no branch
of the converter.

The report carries the human-facing alternatives as text; PRD §5.3 names the three of them and what
each one costs, and the report prints the same three. The converter picks none of them — FR-22
forbids it from parsing the command body, so it cannot tell which alternative fits a given hook, and
a person can.

## Considered Options

- **Forbid transfer of any skill that relies on hooks.** Rejected: it refuses on the part the target
  actually reproduces. `PreToolUse`, `PostToolUse` and `Stop` are documented on both sides; only the
  denial is unknown. It also fails NFR-3 from the other direction — an answer that is never wrong
  because it is never useful, on the most common Claude Code extension there is.
- **Uniform loss: drop every hook and report it.** Rejected: the mirror mistake. It discards a
  documented, reproducible event, and it flattens the one fact worth reporting — that blocking is
  unconfirmed — into the same line as everything else. FR-42 asks for the opposite: name what lost
  its guarantee.
- **Generate a git hook or a CI step instead.** Rejected: a git hook sees files, and a hook that
  forbids an agent action leaves no file for git to see, so the substitute silently covers a
  fraction of the cases while looking complete. Choosing it per hook needs the command body, which
  FR-22 puts out of reach. It survives as advice text, where a human evaluates it.
- **A hook-specific rule inside the converter.** Rejected: it would encode in code what FR-1 puts in
  data, and it would hide the actual finding — that one description entry carried two assertions —
  behind a branch that looks like a deliberate policy. Once the entry is split, the rule that
  remains is the one every other property already uses.
- **Write the transferred hook into the target's shared `hooks.json`.** Rejected here: that file is
  a workspace-wide file that may already hold someone else's entries, so writing into it is a merge
  with an existing result — FR-40, and a separate piece of work. The slice writes its entry beside
  the built skill and the report names the destination path from the description, for the human to
  place.

## Consequences

The split costs an edit in both descriptions and one more value in the closed `Capability.kind`
vocabulary, and every `hook.decision.*` fact needs its own anchor and hash like any other entry —
a claim about blocking is now sourced separately from a claim about the event.

Until Antigravity documents what a non-zero hook exit code does, every hook transfer is `lossy` and
never `clean`, with the same note repeated per hook. That repetition is accurate, and it goes away
by reading the vendor's documentation again, not by weakening the grade.

A reader who wants "hooks are forbidden" will not find that rule anywhere: the outcome is assembled
from an entry's grade and origin like everything else. Someone adding a hook-shaped branch later to
get a different answer is reintroducing exactly what this decision removed.
