# 0014. Documentation shipped with the CLI is a source, and `freshness` leaves it alone

## Context and Problem Statement

ADR-0002 pins every source to the hash of a documentation section, taken from the markdown twin of
a public URL, and `freshness` re-fetches exactly those.

Two facts this track rests on are not on a public page. That `.agents/rules/*.md` is read at all,
and only with a `trigger` header (ADR-0009), and that the plugin manifest carries two fields
(ADR-0015), are both stated in the documentation shipped inside the CLI under `agy-customizations/`.
In both cases the vendor's public page says something narrower, and the environment behaves the way
the shipped file describes.

## Decision Outcome

`Source` gains `retrieved_from: "web" | "shipped"`, defaulting to `web`. `freshness` re-fetches only
`web` sources and passes over `shipped` ones.

A description may therefore carry both a public page and a shipped file for the same subject, and
where the two disagree it records both rather than choosing between them. `references/` and
`resources/` are both `layout` entries on that basis, each naming its own source: one documented by
a shipped skill, the other by a public page.

## Considered Options

- **Use public pages only.** Rejected: the environment does what its shipped documentation says, as
  the live runs showed. A description limited to the public page is a record of what the vendor
  publishes rather than of what the environment is, and the two decisions above would then rest on
  nothing written down anywhere.
- **Give the shipped file a plausible URL so nothing else has to change.** Rejected: `freshness`
  would fetch a page that is not the text that was hashed, and report a discrepancy on the very
  first run. Staleness would stop meaning anything, which costs more than the field saves.
- **Let `freshness` read the shipped file from the local disk.** Rejected: the answer would then
  depend on which CLI version is installed on whichever machine ran the check, and on it being
  installed at all — a check whose result varies by operator is not a check. Re-reading a shipped
  file after a CLI upgrade is deliberate human work, and it should look like it.

## Consequences

A shipped source is never re-checked automatically. `checked_at` and `stale_after_days` still apply
to the description as a whole, but nothing will ever contradict a shipped hash on its own; keeping
it honest means a person opening the installed file again after the CLI moves.

A description can hold two sources that disagree about the same subject, and a reader has to see
both. That is the point — picking one would hide a disagreement that is real.

Existing sources are untouched: the default keeps every previously written `Source` a `web` one.
