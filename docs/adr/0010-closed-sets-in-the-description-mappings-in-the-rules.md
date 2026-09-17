# 0010. A closed value set belongs to the description, a mapping to the rules file

## Context and Problem Statement

Translating a field with a closed set of values — `model`, a tool name — needs two facts that look
alike and are not. Which values the target accepts is a fact its vendor documents. Which source
value becomes which target value is a decision nobody's vendor documents, because no vendor
documents another vendor's vocabulary.

Both facts were about to end up in the same file. `EnvSpec` already carried `tool_names` as a list
of `from`/`to` pairs, which is a mapping between two environments sitting inside a record of what
one of them documents — a record that ADR-0001 dates with `checked_at` and ADR-0002 pins to the
hash of a vendor page.

## Decision Outcome

`Capability` gains an optional `values: list[str] | None`: the closed set the target's documentation
names, quoted from the pinned section like everything else in a description.

Every mapping leaves the descriptions. A separately versioned `rules/<name>-<version>.yaml` carries
the value maps by entry id, the tool-name pairs, the list of ignored paths, the rule for an
undocumented file and the list of files link substitution may touch. `tool_names` is deleted from
`EnvSpec`; it is empty in all three descriptions, so no data moves and none is lost. The report
names `rules_version` beside both environment versions, so a past run can be repeated.

A capability with no `values` means the documentation names no set — never that any value is
accepted. No translation is applied against a set that does not exist, and the entry earns an
`unknown` row saying why.

## Considered Options

- **Keep the mapping where `tool_names` already was, in the target description.** Rejected: a
  description is dated against a vendor page and re-fetched by `freshness`, and a mapping has no
  vendor page to compare against. Changing our own opinion about `sonnet` would edit a file whose
  whole meaning is "this is what the vendor documented on this date", and would either lie about
  that date or force a documentation re-check that nothing prompted. The two artefacts change for
  different reasons and on different schedules, which is what makes them two artefacts.
- **Derive the closed set from the sample set instead of the documentation** — collect the values
  prgate-kit actually uses and treat them as the accepted ones. Rejected: it is the rule derived
  from one set that the brief forbids outright (R06), and it cannot see a value the sample happens
  not to use.
- **Read a missing `values` as "the field accepts anything".** Rejected: that is the permissive
  answer on missing knowledge, which ADR-0003 already settled in the other direction. Silence in a
  document is not permission, and a field translated against a set nobody documented would be a
  rule invented by the converter.
- **Put the pairs in the converter.** Rejected twice over: it writes one vendor's vocabulary into
  code, which the project's conventions forbid, and it leaves the pairs unversioned, so a report
  could never say by which table a past run translated.

## Consequences

Every run carries two version numbers, and both belong in the report: a description version says
what was documented, a `rules_version` says what we decided. A reader chasing an old result needs
both.

Editing an opinion never touches a description, and re-reading documentation never touches an
opinion. The price is a second file to find: the answer to "why did it become `pro`" is in the
rules file and in an ADR, not in `specs/`.

A target that documents no closed set for a field cannot be translated into, by design. Those runs
come back `unknown` and stay `unknown` until somebody reads more documentation — the report says
so, rather than filling the hole with a guess.
