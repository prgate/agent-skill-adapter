# 0002. Source freshness is a hash of the normalized markdown section

## Context and Problem Statement

Every capability record cites a documentation section, and freshness is checked by re-fetching that
section and comparing hashes (FR-7). A hash is meaningless unless the text it covers is produced by
a rule that is declared and reproducible on any machine (R34i).

## Decision Outcome

The description declares `normalization: v1`, which means: fetch the markdown rendition of the page
(`<url>.md`, served by both vendors); cut the section from the anchor heading to the next heading of
the same or higher level; match the anchor against heading text with whitespace trimmed, inner
whitespace collapsed and case folded, and fail if more than one heading matches; then apply NFC,
`\r\n` → `\n`, strip trailing spaces per line, collapse consecutive blank lines into one, strip
blank lines at the edges; `sha256` of the result in UTF-8.

## Considered Options

- **Hash the HTML page.** Rejected: HTML changes with navigation, styling and build details, so a
  redesign would report every record as changed while the content is untouched — the opposite of
  "content, not presentation" (R13).
- **Hash the whole page instead of one section.** Rejected: one edit anywhere makes every record on
  that page discrepant, and the report loses the ability to name which record actually moved.
- **Fuzzy or semantic comparison of the section.** Rejected: not reproducible between a developer's
  machine and CI, and a check that disagrees with itself is not evidence.
- **Take the first matching heading when several match.** Rejected: it silently hashes the wrong
  section, which is worse than refusing — the hash still looks valid.

## Consequences

The rule is a versioned contract: changing any step invalidates every stored `sha256` at once, so a
change means re-verifying all sources and must ship as `normalization: v2`, not as an edit to v1.
The check depends on vendors serving a markdown rendition; if one stops, every source under it
becomes `unreachable` and its description goes stale — correct behaviour, but it halts work until a
human intervenes. Cosmetic content edits (a typo fix inside the section) still count as a change, so
reviewers will see discrepancies that turn out to be nothing. A page with duplicate headings breaks
the check instead of guessing.
