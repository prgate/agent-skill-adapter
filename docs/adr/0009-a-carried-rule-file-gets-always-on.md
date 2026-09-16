# 0009. A carried rule file gets `trigger: always_on`

## Context and Problem Statement

A rule file of the source environment is plain Markdown: the environment reads every such file in
its rules folder, and the file has no header and no key that says when it applies. The target
names a closed set for that decision — `always_on` and `model_decision` — in the frontmatter key
`trigger`, and its description records that set (`specs/google/antigravity-2.0.yaml`,
`rules.frontmatter.trigger`).

Two things were established by running the target environment on real files, and are recorded as
observations of that run (`D01`):

- a rule file with no header is not read at all — the environment skips it rather than defaulting
  it to anything;
- `always_on` is loaded, unconditionally.

A third thing is read, not run: what `model_decision` does. The documentation the environment ships
with says it, in the section the description pins as the source `rules-shipped-trigger`
(`agy-customizations/SKILL.md`, anchor `Progressive Disclosure (Skills and Rules)`) — "Rules with
`trigger: model_decision` behave similarly. Only `always_on` rules are loaded unconditionally."
That same sentence is where the closed set itself comes from. It is stated as read and not as run
because "established by running" is the strongest claim this repository makes, and spending it on
something nobody ran would turn a fact obtained into a fact assumed — in exactly the direction the
whole track is written against.

So a rule file carried across unchanged is a file that never takes effect, and the converter has
to write a `trigger` for it. Which member of the set it writes is not in either description — the
set is the target's, the choice between its members is ours — and this is the same class of
decision as ADR-0008, which is why it is recorded the same way.

## Decision Outcome

A carried rule file that declares no `trigger` gets `trigger: always_on`.

A rule of the source environment was unconditional: the environment read it on every turn, with
nobody asked. A translation that keeps the file and changes when it applies has moved the file and
lost the rule, and the whole point of the transfer is that the set works in the target the way it
worked in the source.

The pair lives in `rules/claude-code-to-antigravity-1.0.yaml` under
`value_maps.rules.frontmatter.trigger`, written as `"": always_on` — the empty left-hand side is
the value a file that declares none has, so the pair reads as every other pair in that file reads:
what was written, and what it becomes. It is versioned by `rules_version` apart from either
description.

A file whose author already set `trigger` keeps what it says. The key is added, never merged over:
somebody who stated when their rule applies has made this decision themselves, and it is not the
converter's to redecide.

The converter names neither value. It asks the target description for the closed set, asks the
rules file what a file without the key gets, and reports the result as an applied rule like any
other.

## Considered Options

- **`model_decision`, on the grounds that it is the more conservative of the two and lets the
  environment decide.** Rejected: it is conservative about the wrong thing. A rule the model may
  or may not load is a rule that applies on some turns and not others, which is a behaviour the
  source set never had and never asked for. The failure is also the silent kind this whole command
  exists against — the file is on disk, the report says it crossed, and the rule holds only
  sometimes, with nothing to read that says which turns. `always_on` can be wrong too, but its
  wrongness is visible: the rule applies, and the owner of the set can see it apply and change one
  key.
- **No key at all: carry the file as it was found and report the missing trigger.** Rejected here
  and kept everywhere the rules name no counterpart. It is the right answer when nobody has
  decided, and it would be the right answer if the environment defaulted an unheaded file to
  something. It does not: the file is not read. Carrying it untouched would mean a report calling
  the transfer clean over a file that does nothing, which is the exact silence of the brief.
- **Ask the caller per file.** Rejected: the command is offline and deterministic, and the answer
  is the same for every rule file of every Claude Code set — that is what makes it a rule rather
  than a prompt.

## Consequences

A rule file of the source set arrives in the target with a header it did not have, and acts. The
report shows the added key as an applied rule with its `rules_version`, so what was added and by
what version is on the record.

The choice is data, not code: a different opinion, or a third member in a later `trigger` set, is
an edit to the rules file and a bump of `rules_version`, with no change to the converter and no
change to either description.

The added key is the only thing this run writes into a rule file. Its body crosses byte for byte,
except where link substitution rewrites an address the same run moved (spec Decisions §7), and
never in a file the rules keep out of substitution.
