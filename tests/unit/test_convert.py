"""Tests for the convert seam: one skill folder, two descriptions -> report and exit code."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_skill_adapter.convert import Verdict, convert
from agent_skill_adapter.envspec.model import EnvSpec

TODAY = date(2026, 9, 14)
SOURCE = "anthropic/claude-code@1.0.0"
TARGET = "google/antigravity@1.0.0"


def write(
    root: Path,
    *,
    vendor: str,
    environment: str,
    capabilities: list[dict[str, Any]] | None = None,
    layout: list[dict[str, Any]] | None = None,
    extends: str | None = None,
) -> None:
    """Put a description carrying only the entries one test cares about on disk."""
    spec = EnvSpec.model_validate(
        {
            "schema_version": 1,
            "vendor": vendor,
            "environment": environment,
            "version_range": ">=1.0.0,<2.0.0",
            "checked_at": TODAY,
            "normalization": "v1",
            "extends": extends,
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
                {"kind": "skill-field", "source_id": "doc", **entry}
                for entry in (capabilities or [])
            ],
            "layout": [{"source_id": "doc", **entry} for entry in (layout or [])],
        }
    )
    folder = root / vendor
    folder.mkdir(parents=True, exist_ok=True)
    payload = spec.model_dump(mode="json", by_alias=True)
    (folder / f"{environment}.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")


def skill(folder: Path, frontmatter: str, *, directories: tuple[str, ...] = ()) -> Path:
    """A skill folder with the given frontmatter and bundled directories."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(f"---\n{frontmatter}---\n\nBody.\n", encoding="utf-8")
    for name in directories:
        (folder / name).mkdir()
    return folder


def properties(report: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    """Every property of the report as id -> (outcome, origin, verdict)."""
    return {
        entry["id"]: (entry["outcome"], entry["origin"], entry["verdict"])
        for entry in report["properties"]
    }


def four_row_tree(tmp_path: Path) -> Path:
    """Descriptions that make one skill hit all four rows of the assembly table."""
    root = tmp_path / "specs"
    write(
        root,
        vendor="agentskills",
        environment="agent-skills",
        capabilities=[{"id": "skill.frontmatter.allowed-tools", "support": "supported"}],
        layout=[{"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"}],
    )
    write(
        root,
        vendor="anthropic",
        environment="claude-code",
        extends="agentskills/agent-skills@1.0.0",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.model", "support": "supported"},
            {"id": "skill.frontmatter.deprecated", "support": "supported"},
        ],
    )
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.deprecated", "support": "unsupported"},
        ],
        layout=[{"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"}],
    )
    return root


def test_the_assembly_table_turns_each_outcome_into_a_verdict(tmp_path: Path) -> None:
    """PRD §5.2, one skill at a time: silence about a format field is the only refusal.

    The four keys below are the four rows of the table. The run takes the worst of them,
    so an `undecidable` property decides the run even though three others are transferable.
    """
    root = four_row_tree(tmp_path)
    folder = skill(
        tmp_path / "example",
        "name: example\nmodel: opus\ndeprecated: true\nallowed-tools: [Read]\n",
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert properties(result.report) == {
        "skill.frontmatter.name": ("reproduced", "extension", "clean"),
        "skill.frontmatter.model": ("unknown", "extension", "lossy"),
        "skill.frontmatter.deprecated": ("missing", "extension", "lossy"),
        "skill.frontmatter.allowed-tools": ("unknown", "specification", "undecidable"),
    }
    assert result.verdict is Verdict.UNDECIDABLE
    assert result.exit_code == 3
    assert result.report["outcome"] == "undecidable"
    assert result.report["report_schema"] == 1


def test_a_skill_the_target_reproduces_converts_without_loss(tmp_path: Path) -> None:
    """Everything reproduced is exit code 0: there is nothing to warn a caller about."""
    root = four_row_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts",))

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert properties(result.report) == {
        "skill.frontmatter.name": ("reproduced", "extension", "clean"),
        "skill.dir.scripts": ("reproduced", "specification", "clean"),
    }
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)
    assert result.report["advice"] == []


def test_a_property_no_description_declares_is_reported_not_dropped(tmp_path: Path) -> None:
    """An unheard-of key and an unheard-of directory get a row each, saying where they were seen.

    Passing over what neither description mentions is the one failure this command could
    not be trusted after: the caller would read a clean report of a skill that lost things.
    """
    root = four_row_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\ntelepathy: on\n", directories=("sandbox",))

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)
    rows = {entry["id"]: entry for entry in result.report["properties"]}

    assert properties(result.report) == {
        "skill.frontmatter.name": ("reproduced", "extension", "clean"),
        "skill.frontmatter.telepathy": ("unknown", "extension", "lossy"),
        "skill.dir.sandbox": ("unknown", "extension", "lossy"),
    }
    assert rows["skill.frontmatter.telepathy"]["found_as"] == "frontmatter key `telepathy`"
    assert rows["skill.dir.sandbox"]["found_as"] == "bundled directory `sandbox/`"
    assert rows["skill.dir.sandbox"]["note"]
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


BROKEN: dict[str, bytes | None] = {
    "no-skill-file": None,
    "unclosed-frontmatter": b"---\nname: example\n\nBody, and no closing line.\n",
    "invalid-yaml": b"---\nname: [unclosed\n---\n\nBody.\n",
    "duplicate-key": b"---\nname: one\nname: two\n---\n\nBody.\n",
    "byte-order-mark": b"\xef\xbb\xbf---\nname: example\n---\n\nBody.\n",
}
"""Five ways a skill file is not one. Each must stop the run rather than be read halfway."""


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_folder_that_is_not_a_skill_stops_the_run_and_still_reports(
    tmp_path: Path, case: str
) -> None:
    """Exit code 6, no properties, and a report that names the file it could not read.

    A duplicate key is here because PyYAML keeps the last of the two without a word: read
    and not refused, the frontmatter would convert as a value nobody chose.
    """
    root = four_row_tree(tmp_path)
    folder = tmp_path / "example"
    folder.mkdir()
    content = BROKEN[case]
    if content is not None:
        (folder / "SKILL.md").write_bytes(content)

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert result.exit_code == 6
    assert result.verdict is Verdict.UNDECIDABLE
    assert result.report["properties"] == []
    assert result.report["report_schema"] == 1
    assert str(folder) in result.report["error"]


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (None, TARGET),
        (SOURCE, None),
        ("anthropic/claude-code", TARGET),
        (SOURCE, "google/antigravity@9.9.9"),
    ],
)
def test_an_environment_version_is_never_guessed(
    tmp_path: Path, source: str | None, target: str | None
) -> None:
    """Not given, not a reference, or covered by no description: undecidable, never a guess."""
    root = four_row_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")

    result = convert(folder, source, target, root=root, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.UNDECIDABLE, 3)
    assert result.report["properties"] == []
    assert result.report["error"]


def hooks_tree(tmp_path: Path) -> Path:
    """A target that fires the event and documents nothing about stopping what follows."""
    root = tmp_path / "specs"
    write(
        root,
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.hooks", "support": "supported"},
            {"id": "hook.event.PreToolUse", "kind": "hook-event", "support": "supported"},
            {"id": "hook.decision.block", "kind": "hook-decision", "support": "supported"},
        ],
    )
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.hooks", "support": "supported"},
            {"id": "hook.event.PreToolUse", "kind": "hook-event", "support": "supported"},
        ],
    )
    return root


def test_a_declared_hook_asks_about_the_event_and_about_the_power_to_stop_it(
    tmp_path: Path,
) -> None:
    """The event is reproduced and the veto is not, and the report says so and offers the ways out.

    A target that fires `PreToolUse` has said nothing about what a non-zero exit code from
    the hook does. Asked as one question, the reproduced event would answer for both and the
    lost veto would leave no trace in the report.
    """
    root = hooks_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\nhooks:\n  PreToolUse:\n    - guard.sh\n")

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert properties(result.report) == {
        "skill.frontmatter.name": ("reproduced", "extension", "clean"),
        "skill.frontmatter.hooks": ("reproduced", "extension", "clean"),
        "hook.event.PreToolUse": ("reproduced", "extension", "clean"),
        "hook.decision.block": ("unknown", "extension", "lossy"),
    }
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)
    assert len(result.report["advice"]) == 3
    assert "pre-commit" in " ".join(result.report["advice"])


def test_writing_the_converted_skill_is_refused_rather_than_faked(tmp_path: Path) -> None:
    """`out` is not built yet, and a report claiming a transfer that never happened is worse."""
    root = four_row_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")

    with pytest.raises(NotImplementedError):
        convert(folder, SOURCE, TARGET, root=root, allow_stale=True, out=tmp_path / "out")
