"""Comparing two environment descriptions: what the target does not reproduce.

The report this module computes is the reason the project exists: it answers, entry by
entry, which of the source environment's fields, subagents and hooks the target
environment reproduces. Nothing here is written by hand except the introductory
paragraph of the markdown rendering -- a hand-written list cannot be re-checked, and
this one decides whether the product is worth building.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agent_skill_adapter.envspec.loader import capability, select
from agent_skill_adapter.envspec.model import EnvSpec, Support


class Outcome(str, Enum):
    """What a comparison concluded about one entry of the source environment."""

    REPRODUCED = "reproduced"
    MISSING = "missing"
    UNKNOWN = "unknown"
    OUT_OF_SCOPE = "out-of-scope"
    """The source environment does not hold the entry either, so there is nothing to reproduce."""


NO_ENTRY = "(no matching entry in the target description)"
"""Stands in for the target's words when the target description has no such entry at all."""

NO_WORDING = "(entry present, no wording)"
"""Stands in for the target's words when it carries the entry but says nothing about it."""

_FROM_SUPPORT = {
    Support.SUPPORTED: Outcome.REPRODUCED,
    Support.UNSUPPORTED: Outcome.MISSING,
    Support.UNKNOWN: Outcome.UNKNOWN,
}


@dataclass(frozen=True)
class Gap:
    """One entry of the source environment, and what the target says about it."""

    id: str
    kind: str
    source_support: Support
    target_support: Support
    outcome: Outcome
    matched: bool = True
    """Whether the target description carries an entry with this id at all."""
    source_note: str | None = None
    target_note: str | None = None


@dataclass(frozen=True)
class GapReport:
    """Every entry of ``source``, each carrying the target's answer, sorted by id."""

    source: EnvSpec
    target: EnvSpec
    gaps: tuple[Gap, ...]

    def count(self, outcome: Outcome, *, matched: bool | None = None) -> int:
        """How many entries ended in ``outcome``, optionally only the matched or unmatched ones.

        ``matched=False`` counts the entries the target description does not carry at all.
        Those are evidence about the target; the rest of ``unknown`` is the limit of our
        reading of someone else's documentation, and the two must not be added up silently.
        """
        return sum(
            1
            for gap in self.gaps
            if gap.outcome is outcome and (matched is None or gap.matched is matched)
        )

    @property
    def transferable(self) -> bool:
        """False when nothing is missing and nothing is unknown -- see :func:`main`."""
        return bool(self.count(Outcome.MISSING) or self.count(Outcome.UNKNOWN))


def compare(source: EnvSpec, target: EnvSpec) -> GapReport:
    """Match every entry of ``source`` against ``target`` by id and judge the outcome.

    Entries are matched by id within their own list: a capability against the target's
    capabilities, a layout entry against the target's layout. Matching by id is what
    makes the report re-computable; the ids of the two descriptions are written to agree
    wherever both environments name the same thing.

    An entry the *source* environment does not itself hold -- a field its own documentation
    records as accepted and inert -- is ``out-of-scope`` whatever the target says. There is
    no guarantee to carry over, so it can neither count as a gap nor, if the target one day
    documents it, as something reproduced.

    For the rest, the outcome is whatever the target *says*, never what it omits:

    * the target documents the entry as supported -- ``reproduced``;
    * the target documents it as unsupported, in words -- ``missing``;
    * the target says ``unknown``, or carries no such entry at all -- ``unknown``.

    An absent entry is therefore never ``missing`` (R22). The difference between "the
    documentation is silent" and "the documentation says no" is the whole point of
    collecting sources, and collapsing it would turn every gap in our own reading of the
    target's docs into a claimed defect of the target.

    A layout entry carries no support value of its own: the target either documents that
    place (``reproduced``) or does not (``unknown``).
    """
    target_notes = {entry.id: entry.note for entry in target.capabilities}
    target_layout = {entry.id: entry.path for entry in target.layout}
    gaps = []
    for entry in source.capabilities:
        support = capability(target, entry.id)
        gaps.append(
            Gap(
                id=entry.id,
                kind=entry.kind,
                source_support=entry.support,
                target_support=support,
                outcome=(
                    _FROM_SUPPORT[support]
                    if entry.support is Support.SUPPORTED
                    else Outcome.OUT_OF_SCOPE
                ),
                matched=entry.id in target_notes,
                source_note=entry.note,
                target_note=target_notes.get(entry.id) if entry.id in target_notes else NO_ENTRY,
            )
        )
    for place in source.layout:
        there = target_layout.get(place.id)
        support = Support.SUPPORTED if there is not None else Support.UNKNOWN
        gaps.append(
            Gap(
                id=place.id,
                kind="layout",
                source_support=Support.SUPPORTED,
                target_support=support,
                outcome=_FROM_SUPPORT[support],
                matched=there is not None,
                source_note=place.path,
                target_note=there if there is not None else NO_ENTRY,
            )
        )
    return GapReport(source=source, target=target, gaps=tuple(sorted(gaps, key=_order)))


def _order(gap: Gap) -> tuple[str, str]:
    """Sort by id, then by kind, so a re-run of the same descriptions renders identically."""
    return (gap.id, gap.kind)


_INTRO = (
    "This list is computed, not written: it is the output of comparing the two environment "
    "descriptions in `specs/`, entry by entry, matched by id. Only this paragraph is written "
    "by hand. `reproduced` means the target's own documentation says it supports the entry; "
    "`missing` means that documentation says, in words, that it does not; `unknown` means the "
    "documentation is silent or carries no such entry -- silence is never read as a denial. "
    "An empty list -- nothing missing and nothing unknown -- would mean the transfer is a file "
    "copy and this product is not needed. The last column splits `unknown` in two: an entry the "
    "target description does not carry at all is evidence about the target, while an entry it "
    "carries without a verdict is the limit of our reading of its documentation -- adding the "
    "two together would let our own incompleteness pass for a finding. `out-of-scope` is a "
    "field the source environment documents as accepted and inert: it has no behaviour to "
    "carry over, so it is neither a gap nor something the target can be credited with "
    "reproducing."
)


def _describe(spec: EnvSpec) -> dict[str, str]:
    return {
        "vendor": spec.vendor,
        "environment": spec.environment,
        "version_range": spec.version_range,
        "checked_at": spec.checked_at.isoformat(),
    }


def render_json(report: GapReport) -> str:
    """The report as JSON. Same descriptions in, same bytes out: no clock is read."""
    payload = {
        "source": _describe(report.source),
        "target": _describe(report.target),
        "counts": {outcome.value: report.count(outcome) for outcome in Outcome},
        "absent_from_target": {
            outcome.value: report.count(outcome, matched=False) for outcome in Outcome
        },
        "gaps": [
            {
                "id": gap.id,
                "kind": gap.kind,
                "source_support": gap.source_support.value,
                "target_support": gap.target_support.value,
                "outcome": gap.outcome.value,
                "matched": gap.matched,
                "source_note": gap.source_note,
                "target_note": gap.target_note,
            }
            for gap in report.gaps
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _cell(text: str | None) -> str:
    """One table cell: a note may carry pipes and newlines, a row may not."""
    if not text:
        return ""
    return " ".join(text.split()).replace("|", "\\|")


def _note_cell(gap: Gap) -> str:
    """Both sides of one entry: what the source keeps, and what the target says about it.

    One column with an arrow, not two: the pair reads as one sentence, and neither half is
    ever blank -- a blank cell would be indistinguishable from "nothing to say here".
    """
    left = _cell(gap.source_note) or NO_WORDING
    right = _cell(gap.target_note) or NO_WORDING
    return f"{left} -> {right}"


def render_markdown(report: GapReport) -> str:
    """The report as markdown. Same descriptions in, same bytes out: no clock is read."""
    source, target = report.source, report.target
    lines = [
        f"# What {target.vendor}/{target.environment} does not reproduce "
        f"from {source.vendor}/{source.environment}",
        "",
        _INTRO,
        "",
        f"- Source: `{source.vendor}/{source.environment}` {source.version_range}, "
        f"checked {source.checked_at.isoformat()}",
        f"- Target: `{target.vendor}/{target.environment}` {target.version_range}, "
        f"checked {target.checked_at.isoformat()}",
        "",
        "| outcome | entries | of which absent from the target description |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {outcome.value} | {report.count(outcome)} | {report.count(outcome, matched=False)} |"
        for outcome in Outcome
    ]
    lines += [
        "",
        "## Entries",
        "",
        "| id | kind | source | target | outcome | what each side documents |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {gap.id} | {gap.kind} | {gap.source_support.value} | "
        f"{gap.target_support.value} | {gap.outcome.value} | {_note_cell(gap)} |"
        for gap in report.gaps
    ]
    return "\n".join(lines) + "\n"


# The one pair this report is about. A second pair would need a second target description,
# and there is none: the command is a developer command, not a configurable tool.
SOURCE = ("anthropic", "claude-code")
TARGET = ("google", "antigravity")

# The environment versions the committed report is built for. They are declared here, not
# inferred: descriptions of several versions of one environment are meant to sit side by
# side (FR-5), and "take the newest one" is a selection rule the product has not declared.
# Moving to a new environment version is an edit of this line, visible in review.
SOURCE_VERSION = "2.1.270"
TARGET_VERSION = "2.0"


def report_from(
    root: str | Path,
    *,
    source_version: str = SOURCE_VERSION,
    target_version: str = TARGET_VERSION,
    allow_stale: bool = False,
) -> GapReport:
    """The report for the descriptions under ``root`` that cover the two given versions.

    Selection is :func:`loader.select`, so its refusals stand: no description covering the
    version raises ``SpecNotFound``, more than one raises ``AmbiguousSpec`` rather than
    picking, and a stale winner raises ``StaleSpec`` unless ``allow_stale`` is set.
    """
    return compare(
        select(root, *SOURCE, source_version, allow_stale=allow_stale),
        select(root, *TARGET, target_version, allow_stale=allow_stale),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Compute the gap report from ``--root`` and write both renderings into ``--out``.

    Returns non-zero when nothing is missing and nothing is unknown. That is not an error
    in the run -- it is the run's answer: the target reproduces everything the source
    documents, the transfer is a file copy, and the product has nothing left to do. The
    code belongs to this developer command alone; the exit codes of the adapter itself
    are fixed elsewhere and are not extended by it.
    """
    parser = ArgumentParser(prog="python -m agent_skill_adapter.envspec.gaps")
    parser.add_argument("--root", default="specs", help="tree of environment descriptions")
    parser.add_argument("--out", default="specs/gaps", help="where both renderings are written")
    parser.add_argument("--source-version", default=SOURCE_VERSION, help="source environment")
    parser.add_argument("--target-version", default=TARGET_VERSION, help="target environment")
    parser.add_argument(
        "--allow-stale", action="store_true", help="rebuild from a description due for a re-check"
    )
    args = parser.parse_args(argv)

    report = report_from(
        args.root,
        source_version=args.source_version,
        target_version=args.target_version,
        allow_stale=args.allow_stale,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{report.source.environment}-to-{report.target.environment}"
    (out / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
    (out / f"{stem}.json").write_text(render_json(report), encoding="utf-8")

    counts = []
    for outcome in Outcome:
        absent = report.count(outcome, matched=False)
        tail = f" ({absent} absent from the target description)" if absent else ""
        counts.append(f"{outcome.value} {report.count(outcome)}{tail}")
    summary = ", ".join(counts)
    print(f"{out / stem}.{{md,json}}: {len(report.gaps)} entries -- {summary}")
    if not report.transferable:
        print(
            f"Nothing missing and nothing unknown: {report.target.environment} reproduces every "
            f"entry {report.source.environment} documents. The transfer is a file copy and this "
            "product is not needed in its current form."
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
