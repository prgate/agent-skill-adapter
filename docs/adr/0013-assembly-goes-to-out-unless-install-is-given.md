# 0013. Assembly writes to `--out`; the live root needs `--install`

## Context and Problem Statement

The goal is a set that works in Antigravity, whose roots are live directories under `~/.gemini/`
and the workspace. Until now the converter wrote only where `--out` pointed, and without `--out`
wrote nothing at all, which leaves the last step — copying into the live roots — to a human doing
by hand the thing the command exists to get right.

## Decision Outcome

The default does not change: without `--install`, assembly goes to `--out` and the command prints
the install line the caller can run.

`--install` expands the same `layout` entries against the live roots instead, prints the whole plan
to the error stream before the first byte is written, and applies the same collision and
escape-the-root checks. `--install` together with `--out` is a refusal: there is one destination,
not two. There is no separate dry-run flag, because the plan prints on every run.

Command files are written at neither destination. The target description has no `commands.*` entry,
so there is nowhere documented to put them, and each command of the set earns a refusal row naming
the one known replacement — a skill is called by name, and the wrapper is not needed.

## Considered Options

- **Install by default, with a flag to write elsewhere.** Rejected: the first run of a new command
  would write into a live configuration root, and the command's entire claim is that it tells you
  what it is about to do. A default that is hard to undo is the wrong default no matter how
  convenient it is on the tenth run.
- **A separate `--dry-run`.** Rejected: the plan is printed on every run regardless, so the flag
  would switch nothing on — and a flag that makes the plan optional is exactly the flag someone
  omits on the run where they needed it.
- **Copy command files anyway, to a plausible path.** Rejected: a path no description names is a
  path the converter invented. The files would sit inert in the target while the report listed them
  as written, which is precisely the gap between "on disk" and "works" that the track closes. A row
  saying there is nowhere to put them is the honest form, and it is more useful.

## Consequences

The ordinary workflow is two steps — convert, read the report, then run the printed line — and that
is the intended friction.

A second `--install` over an existing root shows what would be replaced and refuses on conflict
rather than overwriting quietly, so a repeat run cannot silently flatten someone else's file.

Every destination still comes from the target's `layout`, so `--install` cannot write outside the
roots the description names; the escape check that guarded `--out` guards the live root unchanged.

The owner of the set still has to deal with the commands by hand. The report tells them so, once
per command, with the reason and the replacement.
