# 0012. A refusal names only what the caller named

## Context and Problem Statement

Inside a folder the caller names, there will be things that are not the entity it was named for: a
directory with no `SKILL.md`, a file in the wrong format, a symlinked directory the walk does not
descend so it cannot loop, build leftovers. The converter has to decide which of those stop the run
and which are reported.

## Decision Outcome

A refusal is only ever about what the human named: a path that does not exist, a path that cannot
be read. That is a refusal code and a report whose `error` says which path.

Everything found inside a named path that is not an entity is a row — "nobody declared this" — and
the run continues over the rest of the set. The row carries into the verdict like any other
property.

## Considered Options

- **Refuse on anything unrecognised.** Rejected: a foreign set with one service directory sitting
  next to its skills gets a refusal instead of a transfer, and the rule that no file crosses or
  fails without a row breaks in both directions at once — there is no run, so there are no rows
  either, including for the files that would have converted perfectly.
- **Skip anything unrecognised in silence.** Rejected: that is the defect the whole command was
  built against, reproduced inside it. A file that vanishes between the input folder and the report
  is indistinguishable from a file that was never there.
- **Recognise by a list of known names and extensions.** Rejected: a list of known names in the
  converter is what R04 forbids, and it moves the problem rather than solving it — everything off
  the list still needs one of the three answers above.

## Consequences

A typo in a `--skills` path is an immediate refusal naming the path. A typo inside that path is a
row in a report that otherwise succeeded, so the exit code alone does not tell the caller their set
was complete: the rows have to be read. That is deliberate — the exit code grades the transfer, and
the rows are the transfer.

A run over a folder full of unrelated material finishes, and says so item by item, rather than
stopping at the first surprise.

A symlinked directory is not descended, and the row says that is why, so nobody mistakes a loop
guard for a missing file.
