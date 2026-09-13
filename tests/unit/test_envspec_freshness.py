"""Tests for the freshness seam: a fetched page -> a discrepancy, and back into the file.

``fetch`` is always a stub here: the suite makes no network call.
"""

from __future__ import annotations

from datetime import date
from email.message import Message
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError

import pytest

from agent_skill_adapter.envspec.freshness import check, main, record
from agent_skill_adapter.envspec.loader import is_stale, load
from agent_skill_adapter.envspec.model import DiscrepancyKind
from agent_skill_adapter.envspec.normalize import digest, section_text

TODAY = date(2026, 9, 14)
ANCHOR = "Frontmatter fields"

PAGE = """# Skills

## Frontmatter fields

- `name` names the skill.
- `description` says when to use it.

## Something else

Not part of the section.
"""


def write_spec(root: Path, sha256: str, *, markdown_url: str | None = None) -> Path:
    """Write a description whose single source records ``sha256`` for the page section."""
    source = [
        "  - id: skills-frontmatter",
        "    url: https://example.invalid/docs/skills",
        *([f"    markdown_url: {markdown_url}"] if markdown_url else []),
        f'    anchor: "{ANCHOR}"',
        f'    sha256: "{sha256}"',
        f"    checked_at: {TODAY}",
        '    environment_version: "2.1.270"',
    ]
    text = "\n".join(
        [
            "schema_version: 1",
            "vendor: anthropic",
            "environment: claude-code",
            'version_range: ">=2.1.0,<2.2.0"',
            f"checked_at: {TODAY}",
            "normalization: v1",
            "sources:",
            *source,
            "capabilities:",
            "  - id: skill.frontmatter.name",
            "    kind: skill-field",
            "    support: supported",
            "    source_id: skills-frontmatter",
            "discrepancies: []",
            "",
        ]
    )
    path = root / "spec.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def recorded_sha() -> str:
    """The hash a freshness run would have written when the page still read like ``PAGE``."""
    return digest(section_text(PAGE, ANCHOR))


def test_changed_section_text_reports_both_hashes(tmp_path: Path) -> None:
    spec = load(write_spec(tmp_path, recorded_sha()))
    edited = PAGE.replace("names the skill", "names the skill, lowercase only")

    found = check(spec, fetch=lambda _url: edited, today=TODAY)

    assert [d.kind for d in found] == [DiscrepancyKind.CHANGED]
    detail = found[0].detail or ""
    assert recorded_sha() in detail
    assert digest(section_text(edited, ANCHOR)) in detail
    assert str(TODAY) in detail


def test_formatting_only_change_is_not_a_discrepancy(tmp_path: Path) -> None:
    """Normalization is what makes the hash mean content: styling alone must not trip it."""
    spec = load(write_spec(tmp_path, recorded_sha()))
    restyled = PAGE.replace("\n", "\r\n").replace("names the skill.", "names the skill.   ")
    restyled = restyled.replace("## Frontmatter fields", "## Frontmatter fields\r\n\r\n")

    assert check(spec, fetch=lambda _url: restyled, today=TODAY) == []

    reworded = PAGE.replace("names the skill", "is the skill identifier")
    assert len(check(spec, fetch=lambda _url: reworded, today=TODAY)) == 1


def test_unreadable_source_is_unreachable_not_silence(tmp_path: Path) -> None:
    spec = load(write_spec(tmp_path, recorded_sha()))
    failures: list[Exception] = [
        OSError("network is unreachable"),
        HTTPError("https://example.invalid/docs/skills.md", 404, "Not Found", Message(), None),
        # A cut-off answer is the server's failure, and HTTPException is outside OSError.
        IncompleteRead(b"## Frontmatter fi"),
    ]

    for failure in failures:

        def fetch(_url: str, failure: Exception = failure) -> str:
            raise failure

        found = check(spec, fetch=fetch, today=TODAY)
        assert [d.kind for d in found] == [DiscrepancyKind.UNREACHABLE], failure


def test_vanished_anchor_is_unreachable(tmp_path: Path) -> None:
    """The page still loads, but the section it was quoted from is gone."""
    spec = load(write_spec(tmp_path, recorded_sha()))
    renamed = PAGE.replace("## Frontmatter fields", "## Skill metadata")

    found = check(spec, fetch=lambda _url: renamed, today=TODAY)

    assert [d.kind for d in found] == [DiscrepancyKind.UNREACHABLE]
    assert ANCHOR in (found[0].detail or "")


def test_recorded_discrepancy_survives_a_reload_and_makes_the_spec_stale(tmp_path: Path) -> None:
    """A discrepancy lives in the description file, so a run without a network still sees it."""
    path = write_spec(tmp_path, recorded_sha())
    spec = load(path)
    edited = PAGE.replace("says when to use it", "says when to use it (one sentence)")
    found = check(spec, fetch=lambda _url: edited, today=TODAY)

    record(path, found)

    reloaded = load(path)
    assert [(d.source_id, d.kind) for d in reloaded.discrepancies] == [
        (d.source_id, d.kind) for d in found
    ]
    assert reloaded.discrepancies[0].detail == found[0].detail
    assert is_stale(reloaded, TODAY)
    assert "capabilities:" in path.read_text(encoding="utf-8"), "the rest of the file is kept"


def test_a_second_run_appends_next_to_the_first(tmp_path: Path) -> None:
    """The block already holds an entry: the new one is added to it, not written over it."""
    path = write_spec(tmp_path, recorded_sha())
    reworded = PAGE.replace("says when to use it", "says when it applies")
    record(path, check(load(path), fetch=lambda _url: reworded, today=TODAY))

    def unreadable(_url: str) -> str:
        raise OSError("network is unreachable")

    record(path, check(load(path), fetch=unreadable, today=TODAY))

    reloaded = load(path)
    assert [d.kind for d in reloaded.discrepancies] == [
        DiscrepancyKind.CHANGED,
        DiscrepancyKind.UNREACHABLE,
    ]


def test_a_defect_of_ours_is_not_filed_as_a_vendor_discrepancy(tmp_path: Path) -> None:
    """Only a failure to read the page is ``unreachable``; a broken ``fetch`` must surface."""
    spec = load(write_spec(tmp_path, recorded_sha()))

    def broken(_url: str) -> str:
        raise TypeError("a defect in our own code, not the vendor's server")

    with pytest.raises(TypeError):
        check(spec, fetch=broken, today=TODAY)


def test_appended_entries_take_the_indent_of_the_existing_block(tmp_path: Path) -> None:
    """A block written at column zero is valid YAML: appending must not break the file."""
    path = write_spec(tmp_path, recorded_sha())
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "discrepancies: []",
            "discrepancies:\n- source_id: skills-frontmatter\n  kind: unreachable\n",
        ),
        encoding="utf-8",
    )
    reworded = PAGE.replace("names the skill", "identifies the skill")

    record(path, check(load(path), fetch=lambda _url: reworded, today=TODAY))

    assert [d.kind for d in load(path).discrepancies] == [
        DiscrepancyKind.UNREACHABLE,
        DiscrepancyKind.CHANGED,
    ]


def test_main_writes_into_the_file_only_with_write(tmp_path: Path) -> None:
    path = write_spec(tmp_path, recorded_sha())
    reworded = PAGE.replace("names the skill", "identifies the skill")

    assert main(["--root", str(tmp_path)], fetch=lambda _url: reworded) == 0
    assert load(path).discrepancies == [], "a plain run only reports"

    assert main(["--root", str(tmp_path), "--write"], fetch=lambda _url: reworded) == 0
    assert [d.kind for d in load(path).discrepancies] == [DiscrepancyKind.CHANGED]


def test_main_refuses_a_root_with_nothing_to_check(tmp_path: Path) -> None:
    """Nothing checked is not everything confirmed — a mistyped root must not read as green."""
    with pytest.raises(SystemExit) as exit_code:
        main(["--root", str(tmp_path / "typo")], fetch=lambda _url: PAGE)

    assert exit_code.value.code != 0
