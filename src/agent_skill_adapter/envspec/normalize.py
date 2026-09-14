"""Section extraction, text normalization and hashing (normalization rule ``v1``)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_BLANK_RUN = re.compile(r"\n{3,}")
_HEADING = re.compile(r" {0,3}(#{1,6})\s+(\S.*)$")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")


def _anchor_key(text: str) -> str:
    """Return the comparison form of a heading text: collapsed spacing, case folded."""
    return " ".join(text.split()).casefold()


class AnchorError(ValueError):
    """Raised when an anchor matches no heading, or more than one."""


def section_text(markdown: str, anchor: str) -> str:
    """Return the section introduced by the heading matching ``anchor``.

    The section runs from its heading to the next heading of the same or a higher
    level; deeper headings stay inside it. Hashes inside fenced code blocks are
    not headings, and a fenced block ends only on a marker of the same character,
    at least as long as the one that opened it. The
    anchor is the heading text without the hashes, compared after trimming,
    collapsing inner spacing and folding case.
    """
    wanted = _anchor_key(anchor)
    lines = markdown.splitlines()
    headings: list[tuple[int, int]] = []
    matches: list[int] = []
    fence: tuple[str, int] | None = None
    for number, line in enumerate(lines):
        found_fence = _FENCE.match(line)
        if found_fence is not None:
            marker = found_fence.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            continue
        if fence is not None:
            continue
        found = _HEADING.match(line)
        if found is None:
            continue
        headings.append((number, len(found.group(1))))
        if _anchor_key(found.group(2)) == wanted:
            matches.append(number)

    if not matches:
        raise AnchorError(f"anchor {anchor!r} matches no heading")
    if len(matches) > 1:
        found_at = ", ".join(f"line {number + 1}" for number in matches)
        raise AnchorError(f"anchor {anchor!r} matches {len(matches)} headings: {found_at}")

    start = matches[0]
    level = next(level for number, level in headings if number == start)
    end = next(
        (number for number, other in headings if number > start and other <= level),
        len(lines),
    )
    return "\n".join(lines[start:end])


def normalize(text: str) -> str:
    """Return ``text`` under normalization rule ``v1``.

    NFC, CRLF/CR to LF, trailing whitespace stripped per line, runs of blank lines
    collapsed to one, blank lines trimmed at both ends.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return _BLANK_RUN.sub("\n\n", text).strip("\n")


def digest(text: str) -> str:
    """Return the hex sha256 of ``text`` normalized under rule ``v1``."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
