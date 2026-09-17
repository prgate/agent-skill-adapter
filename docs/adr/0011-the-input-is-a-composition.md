# 0011. The input is a composition, not a single root

## Context and Problem Statement

`convert` took one positional argument: a skill folder. The thing people actually own is a set —
skills, subagents, commands, rule files, a plugin manifest — and prgate-kit lays those out in
folders of its own choosing. Any other set of the same format has to convert without a code change
(R07, R27), and prgate-kit's layout proves nothing about anyone else's.

## Decision Outcome

The composition is named on the command line: `--skills DIR`, `--agents DIR`, `--commands DIR`,
`--rules PATH`, `--plugin FILE`, each repeatable, each optional. A run without one of them is a run
without that part of the set, and reads the same as a run with it. The positional skill folder
stays and means exactly what it meant before.

A run that names no part at all is a refusal listing the options, not an empty report with a clean
verdict.

## Considered Options

- **One root plus a layout convention** — `skills/`, `agents/`, `commands/` under whatever the
  caller passes. Rejected: that is prgate-kit's layout promoted to a rule. A set that spells its
  folders differently then needs either a code change or a rename of the caller's own files, and
  the requirement is that neither happens.
- **One root plus discovery** — walk it and recognise each part by its contents. Rejected: a
  recogniser is a rule derived from observing one set, and it fails silently. Anything it does not
  recognise is not in the run and produces no row, which is the exact silence this command exists
  to end. It is also ambiguous on its face: a folder of Markdown files under a skill bundle and a
  folder of rule files look alike, and guessing between them is a decision made for the caller
  without telling them.
- **A manifest file describing the set.** Rejected: a new format to define, version and validate in
  order to carry what five flags carry, and it would have to be written by hand for every set that
  does not already have one.

## Consequences

The caller must know their own layout; nothing is discovered for them, and the command line grows
by five options. In exchange the converter holds no opinion about where anything lives, so a set
laid out any way at all converts by the same rules.

A named folder that turns out to be empty is a row saying that part of the set is empty, not an
error, and it does not spoil the verdict.

A part nobody named is simply not in the run, and the report cannot say a word about it. That
silence belongs to the caller, and it is the one silence left: the guarantee that no file
disappears without a row holds over what was named.

A sixth kind of asset later is a sixth option, not a change to how anything is found.
