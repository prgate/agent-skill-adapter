"""Tests for the gaps seam: two descriptions -> outcome per entry -> rendered report."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_skill_adapter.envspec.gaps import (
    NO_ENTRY,
    NO_WORDING,
    Origin,
    Outcome,
    compare,
    main,
    render_json,
    render_markdown,
    report_from,
)
from agent_skill_adapter.envspec.model import EnvSpec, Support

TODAY = date(2026, 9, 14)


def build(
    *,
    vendor: str,
    environment: str,
    capabilities: list[dict[str, Any]],
    layout: list[dict[str, Any]] | None = None,
    version_range: str = ">=1.0.0,<2.0.0",
) -> EnvSpec:
    """A minimal description carrying only the entries a comparison test cares about."""
    return EnvSpec.model_validate(
        {
            "schema_version": 1,
            "vendor": vendor,
            "environment": environment,
            "version_range": version_range,
            "checked_at": TODAY,
            "normalization": "v1",
            "sources": [
                {
                    "id": "doc",
                    "url": "https://example.test/doc",
                    "anchor": "Fields",
                    "sha256": "a" * 64,
                    "checked_at": TODAY,
                    "environment_version": "1.0.0",
                }
            ],
            "capabilities": [
                {"kind": "skill-field", "source_id": "doc", **entry} for entry in capabilities
            ],
            "layout": [{"source_id": "doc", **entry} for entry in (layout or [])],
        }
    )


def test_outcome_follows_what_the_target_says() -> None:
    """Supported reproduces, a documented denial is missing, silence and absence are unknown."""
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {"id": "field.kept", "support": Support.SUPPORTED},
            {"id": "field.denied", "support": Support.SUPPORTED},
            {"id": "field.silent", "support": Support.SUPPORTED},
            {"id": "field.absent", "support": Support.SUPPORTED},
        ],
    )
    target = build(
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "field.kept", "support": Support.SUPPORTED},
            {"id": "field.denied", "support": Support.UNSUPPORTED},
            {"id": "field.silent", "support": Support.UNKNOWN},
        ],
    )

    outcomes = {gap.id: gap.outcome for gap in compare(source, target).gaps}

    assert outcomes == {
        "field.kept": Outcome.REPRODUCED,
        "field.denied": Outcome.MISSING,
        "field.silent": Outcome.UNKNOWN,
        "field.absent": Outcome.UNKNOWN,
    }


def test_the_power_to_block_is_an_entry_of_its_own() -> None:
    """What a hook may decide is a `hook-decision` entry, judged apart from the event.

    An environment that fires the event says nothing about whether a hook of it can stop
    what is about to happen. Kept in one entry, the event's `supported` would answer for
    both and the lost veto would never reach the report.
    """
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {"id": "hook.event.PreToolUse", "kind": "hook-event", "support": Support.SUPPORTED},
            {"id": "hook.decision.block", "kind": "hook-decision", "support": Support.SUPPORTED},
        ],
    )
    target = build(
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "hook.event.PreToolUse", "kind": "hook-event", "support": Support.SUPPORTED},
        ],
    )

    judged = {gap.id: (gap.kind, gap.outcome) for gap in compare(source, target).gaps}

    assert judged == {
        "hook.event.PreToolUse": ("hook-event", Outcome.REPRODUCED),
        "hook.decision.block": ("hook-decision", Outcome.UNKNOWN),
    }


def test_layout_entry_absent_from_the_target_is_unknown_not_missing() -> None:
    """A place the target does not document is silence, never a documented denial."""
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[],
        layout=[
            {"id": "skills.user", "path": "~/.claude/skills/"},
            {"id": "hooks.managed", "path": "/etc/claude-code/hooks/"},
        ],
    )
    target = build(
        vendor="google",
        environment="antigravity",
        capabilities=[],
        layout=[{"id": "skills.user", "path": "~/.gemini/config/skills/"}],
    )

    outcomes = {gap.id: gap.outcome for gap in compare(source, target).gaps}

    assert outcomes == {
        "skills.user": Outcome.REPRODUCED,
        "hooks.managed": Outcome.UNKNOWN,
    }


def two_sided() -> tuple[EnvSpec, EnvSpec]:
    """A source and a target whose ids agree, deliberately declared out of order."""
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {"id": "zeta.field", "support": Support.SUPPORTED},
            {"id": "alpha.field", "support": Support.SUPPORTED},
        ],
        layout=[{"id": "mid.place", "path": "~/.claude/skills/"}],
    )
    target = build(
        vendor="google",
        environment="antigravity",
        capabilities=[
            {
                "id": "alpha.field",
                "support": Support.UNSUPPORTED,
                "note": "pipes | and\nlines",
            }
        ],
        layout=[{"id": "mid.place", "path": "~/.gemini/config/skills/"}],
    )
    return source, target


def test_rendering_is_sorted_and_repeatable() -> None:
    """Ids come out sorted and a second rendering is byte for byte the first one."""
    report = compare(*two_sided())

    payload = json.loads(render_json(report))
    assert [gap["id"] for gap in payload["gaps"]] == ["alpha.field", "mid.place", "zeta.field"]
    assert payload["counts"] == {
        "reproduced": 1,
        "missing": 1,
        "unknown": 1,
        "out-of-scope": 0,
    }
    assert payload["absent_from_target"] == {
        "reproduced": 0,
        "missing": 0,
        "unknown": 1,
        "out-of-scope": 0,
    }

    assert render_json(report) == render_json(compare(*two_sided()))
    assert render_markdown(report) == render_markdown(compare(*two_sided()))


def test_markdown_keeps_one_row_per_entry() -> None:
    """The target's own words reach the row, and a pipe in them does not break the table."""
    text = render_markdown(compare(*two_sided()))

    rows = [line for line in text.splitlines() if line.startswith("| alpha.field ")]
    assert len(rows) == 1
    assert rows[0].count("|") - rows[0].count("\\|") == 8
    assert "\\|" in rows[0]
    assert rows[0].endswith(f"| {NO_WORDING} -> pipes \\| and lines |")

    absent = [line for line in text.splitlines() if line.startswith("| zeta.field ")]
    assert NO_ENTRY in absent[0]


def test_origin_says_who_declares_the_entry_not_who_acts_on_it() -> None:
    """Silence about a field of the extended format is other news than silence about an extension.

    The base description states what a *format* defines, so its ``support`` answers a
    different question than an environment's and must not decide the origin: the first entry
    below is declared by the format and recorded there as ``unsupported``, and it is still
    ``specification``. Membership is by id within the entry's own list: a place the format
    declares is inherited (``skill.file``), and a place whose name the format uses for a
    *field* is not (``skill.body.content`` -- the format said nothing about a directory), so
    the same name appears twice with two origins, one per list.
    """
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": Support.SUPPORTED},
            {"id": "skill.frontmatter.effort", "support": Support.SUPPORTED},
        ],
        layout=[
            {"id": "skill.file", "path": "skills/<name>/SKILL.md"},
            {"id": "skills.user", "path": "~/.claude/skills/"},
            {"id": "skill.body.content", "path": "skills/<name>/body/"},
        ],
    )
    target = build(vendor="google", environment="antigravity", capabilities=[])
    base = build(
        vendor="agentskills",
        environment="agent-skills",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": Support.UNSUPPORTED},
            {"id": "skill.body.content", "support": Support.SUPPORTED},
        ],
        layout=[{"id": "skill.file", "path": "<skill-name>/SKILL.md"}],
    )

    report = compare(source, target, [base])

    assert {(gap.id, gap.kind): gap.origin for gap in report.gaps} == {
        ("skill.frontmatter.name", "skill-field"): Origin.SPECIFICATION,
        ("skill.frontmatter.effort", "skill-field"): Origin.EXTENSION,
        ("skill.file", "layout"): Origin.SPECIFICATION,
        ("skills.user", "layout"): Origin.EXTENSION,
        ("skill.body.content", "layout"): Origin.EXTENSION,
        # Declared by the format, absent from the source description, compared all the same.
        ("skill.body.content", "skill-field"): Origin.SPECIFICATION,
    }
    assert report.count(Outcome.UNKNOWN) == 6
    assert report.count(Outcome.UNKNOWN, origin=Origin.SPECIFICATION) == 3

    payload = json.loads(render_json(report))
    assert payload["declared_by_specification"]["unknown"] == 3
    assert [gap["origin"] for gap in payload["gaps"] if gap["id"] == "skills.user"] == ["extension"]
    assert [base["environment"] for base in payload["specification"]] == ["agent-skills"]


def test_a_specification_entry_the_source_does_not_repeat_is_still_compared() -> None:
    """Declaring ``extends`` puts the format's entries into the comparison, written out or not.

    The source description repeats neither entry below; by saying it implements the format it
    owes both, and the target answers for both -- one place it documents, one it does not.
    Comparing only the entries one description happens to spell out would drop the whole class
    of rules a format states about the skill file itself.
    """
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[{"id": "skill.frontmatter.effort", "support": Support.SUPPORTED}],
    )
    target = build(
        vendor="google",
        environment="antigravity",
        capabilities=[],
        layout=[{"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"}],
    )
    base = build(
        vendor="agentskills",
        environment="agent-skills",
        capabilities=[],
        layout=[
            {"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"},
            {"id": "skill.dir.assets", "path": "<skill-name>/assets/"},
        ],
    )

    report = compare(source, target, [base])

    assert {gap.id: (gap.outcome, gap.origin) for gap in report.gaps} == {
        "skill.frontmatter.effort": (Outcome.UNKNOWN, Origin.EXTENSION),
        "skill.dir.scripts": (Outcome.REPRODUCED, Origin.SPECIFICATION),
        "skill.dir.assets": (Outcome.UNKNOWN, Origin.SPECIFICATION),
    }


ARGS = ["--source-version", "1.0.0", "--target-version", "1.0.0", "--allow-stale"]
"""What the command needs for the toy descriptions above: their own version, and no clock."""


def write(root: Path, spec: EnvSpec, name: str | None = None) -> None:
    """Put a description on disk the way the command expects to find it."""
    folder = root / spec.vendor
    folder.mkdir(parents=True, exist_ok=True)
    payload = spec.model_dump(mode="json", by_alias=True)
    file = folder / f"{name or spec.environment}.yaml"
    file.write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_nothing_missing_and_nothing_unknown_is_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty list is the answer "no product needed", not a successful run."""
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[{"id": "field.kept", "support": Support.SUPPORTED}],
    )
    target = build(
        vendor="google",
        environment="antigravity",
        capabilities=[{"id": "field.kept", "support": Support.SUPPORTED}],
    )
    write(tmp_path / "specs", source)
    write(tmp_path / "specs", target)
    out = tmp_path / "gaps"

    code = main([*ARGS, "--root", str(tmp_path / "specs"), "--out", str(out)])

    assert code != 0
    assert "not needed" in capsys.readouterr().out
    assert (out / "claude-code-to-antigravity.md").exists()
    assert (out / "claude-code-to-antigravity.json").exists()


def test_a_gap_left_over_is_a_successful_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One entry the target does not reproduce is enough to justify the product."""
    source, target = two_sided()
    write(tmp_path / "specs", source)
    write(tmp_path / "specs", target)

    code = main([*ARGS, "--root", str(tmp_path / "specs"), "--out", str(tmp_path / "gaps")])

    assert code == 0
    assert "missing 1" in capsys.readouterr().out


def test_committed_report_matches_the_descriptions_it_was_built_from() -> None:
    """The files in `specs/gaps/` are the current descriptions, not an older pair of them.

    The report is re-generated by hand after every edit to a description, and nothing but
    this test notices when that step is skipped. A red run here means: re-run
    ``python -m agent_skill_adapter.envspec.gaps``.
    """
    repo = Path(__file__).resolve().parents[2]
    # allow_stale: this test is about the report matching the descriptions, not about the
    # descriptions being due for a re-check. Without it the run would fail on a calendar.
    report = report_from(repo / "specs", allow_stale=True)
    committed = repo / "specs" / "gaps" / "claude-code-to-antigravity"

    assert committed.with_suffix(".md").read_text(encoding="utf-8") == render_markdown(report)
    assert committed.with_suffix(".json").read_text(encoding="utf-8") == render_json(report)


def test_version_picks_between_two_descriptions_of_one_environment(tmp_path: Path) -> None:
    """Descriptions of several versions sit side by side; the version says which one is read."""
    old = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[{"id": "field.old", "support": Support.SUPPORTED}],
        version_range=">=1.0.0,<2.0.0",
    )
    new = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[{"id": "field.new", "support": Support.SUPPORTED}],
        version_range=">=2.0.0,<3.0.0",
    )
    target = build(vendor="google", environment="antigravity", capabilities=[])
    root = tmp_path / "specs"
    write(root, old, name="claude-code-1")
    write(root, new, name="claude-code-2")
    write(root, target)

    report = report_from(root, source_version="2.5.0", target_version="1.0.0", allow_stale=True)

    assert [gap.id for gap in report.gaps] == ["field.new"]


def test_a_field_the_source_does_not_hold_is_never_reproduced() -> None:
    """The source accepts the field and ignores it: the target cannot reproduce a guarantee."""
    source = build(
        vendor="anthropic",
        environment="claude-code",
        capabilities=[{"id": "skill.frontmatter.license", "support": Support.UNSUPPORTED}],
    )
    target = build(
        vendor="google",
        environment="antigravity",
        capabilities=[{"id": "skill.frontmatter.license", "support": Support.SUPPORTED}],
    )

    report = compare(source, target)

    assert [gap.outcome for gap in report.gaps] == [Outcome.OUT_OF_SCOPE]
    assert report.count(Outcome.UNKNOWN) == 0
    assert report.transferable is False
