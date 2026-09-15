"""Tests for the convert seam: one skill folder, two descriptions -> report and exit code."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from agent_skill_adapter.cli.main import app
from agent_skill_adapter.convert import WORKAROUNDS, Scope, Verdict, convert
from agent_skill_adapter.envspec.model import EnvSpec

runner = CliRunner()

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
    """A skill folder with the given frontmatter and bundled directories.

    `description` is written for every case: it is a required field, so a folder without it
    is not a skill folder at all, and the cases about that live in `BROKEN` as raw bytes.
    """
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\ndescription: what it does\n{frontmatter}---\n\nBody.\n", encoding="utf-8"
    )
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
            {"id": "skill.frontmatter.description", "support": "supported"},
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
            {"id": "skill.frontmatter.description", "support": "supported"},
            {"id": "skill.frontmatter.deprecated", "support": "unsupported"},
        ],
        # A place for a skill file, because a target that names none has nowhere to assemble
        # into at all -- which is its own refusal, in either mode, and not what these four
        # rows are about.
        layout=[
            {"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"},
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
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
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
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
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
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
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
        "skill.frontmatter.telepathy": ("unknown", "extension", "lossy"),
        "skill.dir.sandbox": ("unknown", "extension", "lossy"),
    }
    assert rows["skill.frontmatter.telepathy"]["found_as"] == "frontmatter key `telepathy`"
    assert rows["skill.dir.sandbox"]["found_as"] == "bundled directory `sandbox/`"
    assert rows["skill.dir.sandbox"]["note"]
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


def nested(levels: int) -> bytes:
    """A frontmatter whose one key nests `levels` mappings deep and is valid YAML throughout."""
    rungs = "".join(f"{'  ' * (level + 1)}k{level}:\n" for level in range(levels))
    header = (
        f"name: example\ndescription: what it does\nnest:\n{rungs}{'  ' * (levels + 1)}leaf: x\n"
    )
    return f"---\n{header}---\n\nBody.\n".encode()


BROKEN: dict[str, bytes | None] = {
    "no-skill-file": None,
    "unclosed-frontmatter": b"---\nname: example\n\nBody, and no closing line.\n",
    "invalid-yaml": b"---\nname: [unclosed\n---\n\nBody.\n",
    "duplicate-key": b"---\nname: one\nname: two\ndescription: what it does\n---\n\nBody.\n",
    "duplicate-normalized-key": b"---\ndescription: what it does\nhooks:\n  PreToolUse:\n"
    b"    2026-09-14: from-date-key\n    '2026-09-14': from-string-key\n---\n\nBody.\n",
    "duplicate-written-key": b"---\ndescription: what it does\nhooks:\n  PreToolUse:\n"
    b"    1: from-int-key\n    '1': from-string-key\n---\n\nBody.\n",
    "unhashable-key": b"---\ndescription: what it does\n? [a, b]\n: v\n---\n\nBody.\n",
    "unstable-set": b"---\ndescription: what it does\nhooks: !!set {alpha, beta}\n---\n\nBody.\n",
    "unstable-bytes": b"---\ndescription: what it does\nseed: !!binary aGk=\n---\n\nBody.\n",
    "nonfinite-nan": b"---\ndescription: what it does\nweight: .nan\n---\n\nBody.\n",
    "nonfinite-infinity": b"---\ndescription: what it does\nweight: .inf\n---\n\nBody.\n",
    "nonfinite-negative-infinity": b"---\ndescription: what it does\nweight: -.inf\n---\n\nBody.\n",
    "byte-order-mark": b"\xef\xbb\xbf---\nname: example\ndescription: d\n---\n\nBody.\n",
    "no-opening-line": b"name: example\ndescription: what it does\n---\n\nBody.\n",
    "not-a-mapping": b"---\n- name: example\n- description: what it does\n---\n\nBody.\n",
    "not-utf-8": b"---\nname: \xff\ndescription: what it does\n---\n\nBody.\n",
    "anchor-and-alias": b"---\nname: &n example\ndescription: *n\n---\n\nBody.\n",
    "oversize": b"---\nname: example\ndescription: " + b"x" * 200_000 + b"\n---\n\nBody.\n",
    "too-deep": nested(40),
    "no-description": b"---\nname: example\n---\n\nBody.\n",
    "file-too-large": b"---\nname: example\ndescription: what it does\n---\n\n"
    + b"x" * 1024 * 1024,
}
"""Twenty-one ways a skill file is not one. Each must stop the run rather than be read halfway.

A set and a block of bytes are here because neither has a text it always reads back as: the
same header would put different bytes in the assembled file on every run, and a converter
whose output moves on a fixed input cannot be checked against anything. `.nan`, `.inf` and
`-.inf` are here for the other half of the same rule: JSON has no such number, and
`json.dumps` writes them as a bare `NaN` or `Infinity` that a strict reader refuses -- the
file would leave here looking assembled and arrive as something the target cannot load.
"""


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_folder_that_is_not_a_skill_stops_the_run_and_still_reports(
    tmp_path: Path, case: str
) -> None:
    """Exit code 6, no properties, and a report that names the file it could not read.

    A duplicate key is here because PyYAML keeps the last of the two without a word: read
    and not refused, the frontmatter would convert as a value nobody chose. Two keys that
    become one only once the header is carried across are the same duplicate, made by this
    command rather than by the person, and are refused the same way. An anchor and
    its alias are the same defect in another spelling -- what a reader sees in the file and
    what the parser builds stop being the same text (FR-15). A header without `description`
    is a missing required field, which FR-16 counts as a structural break and not as an
    optional field left out; `name` is not in that company, and the test below says so.
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


def test_two_header_keys_that_carry_across_as_one_are_both_named(tmp_path: Path) -> None:
    """A date key and the quoted text of it are two keys in the file and one after carrying.

    Whichever of the two values is dropped, dropping it silently is the failure this command
    exists to prevent, so the run stops. The message names the place inside the header and
    both keys as they are written there: "a key was lost" is nothing a person can act on
    without knowing which, and the two read the same once either is a plain string.
    """
    root = four_row_tree(tmp_path)
    folder = skill(
        tmp_path / "example",
        "hooks:\n  PreToolUse:\n    2026-09-14: from-date-key\n    '2026-09-14': from-string-key\n",
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    error = result.report["error"]

    assert result.exit_code == 6
    assert "frontmatter.hooks.PreToolUse" in error
    # As the header writes them: the date bare, the text quoted. A Python `repr` would name
    # the type instead -- `datetime.date(2026, 9, 14)` -- which is a string the file does not
    # contain, and this module refuses to name a value by its type twenty lines further down.
    assert re.search(r"(?<!['\w])2026-09-14(?!['\w])", error)
    assert "'2026-09-14'" in error
    assert "datetime" not in error


@pytest.mark.skipif(os.geteuid() == 0, reason="a mode of 000 does not stop root from reading")
def test_a_skill_file_the_filesystem_refuses_to_open_stops_the_run_the_same_way(
    tmp_path: Path,
) -> None:
    """A `SKILL.md` nobody may read is a folder that could not be read: code 6 and a report.

    The refusal arrives as a `PermissionError` rather than as anything this module raises,
    and the answer a caller gets must not depend on that: a traceback would exit 1, the code
    that says the skill transferred with known losses.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    (folder / "SKILL.md").chmod(0o000)

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.UNDECIDABLE, 6)
    assert result.report["properties"] == []
    assert str(folder) in result.report["error"]


@pytest.mark.skipif(os.geteuid() == 0, reason="a mode of 000 does not stop root from reading")
def test_a_description_that_cannot_be_read_is_blamed_on_the_description(tmp_path: Path) -> None:
    """A description nobody may read: exit code 3, and the file named is the one that failed.

    The side that failed decides both. Naming the skill folder would send a person to look
    for a fault in their own skill, and code 6 would tell them the folder is not a skill
    folder -- while what could not be read is a file of this repository. Every other way of
    not knowing what the two environments say is code 3, and this is one more of them.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    shut = root / "google" / "antigravity.yaml"
    shut.chmod(0o000)

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.UNDECIDABLE, 3)
    assert str(shut) in result.report["error"]
    assert result.report["properties"] == []


def test_a_field_the_descriptions_call_optional_is_not_demanded_here(tmp_path: Path) -> None:
    """A skill file without `name` converts: both environments default it to the folder name.

    Requiring it would be this command inventing a rule about environments it only reads
    about -- and inventing it in the harshest form there is, a refusal to read the file at
    all. The open specification does mark `name` required; both environments say it defaults
    to the directory name, and the runtime that loads the file is the one whose refusal a
    person meets.
    """
    root = four_row_tree(tmp_path)
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\ndescription: what it does\n---\n\nBody.\n", encoding="utf-8"
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)
    assert properties(result.report) == {
        "skill.frontmatter.description": ("reproduced", "extension", "clean")
    }


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
            {"id": "skill.frontmatter.description", "support": "supported"},
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
            {"id": "skill.frontmatter.description", "support": "supported"},
            {"id": "skill.frontmatter.hooks", "support": "supported"},
            {"id": "hook.event.PreToolUse", "kind": "hook-event", "support": "supported"},
        ],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
            {"id": "hooks.project", "path": ".agents/hooks.json"},
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
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
        "skill.frontmatter.hooks": ("reproduced", "extension", "clean"),
        "hook.event.PreToolUse": ("reproduced", "extension", "clean"),
        "hook.decision.block": ("unknown", "extension", "lossy"),
    }
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)
    # Three ways out, and the three the module offers: the count is pinned here and not
    # read off the constant, or an emptied constant would agree with an empty report.
    assert len(result.report["advice"]) == 3
    assert result.report["advice"] == list(WORKAROUNDS["hook-decision"])


def test_a_hook_no_description_declares_still_earns_the_ways_out(tmp_path: Path) -> None:
    """The advice follows from the hook in the folder, not from anyone having written it down.

    One folder, one hook, two trees of descriptions: one that mentions hooks and one that
    has never heard of them. The second holds no entry to read a kind off, and the hook is
    lost there exactly as it is in the first -- so the ways of keeping the rule are the same
    ways, word for word. A report that warned about the loss while offering nothing to do
    about it is a warning nobody can act on.
    """
    silent = four_row_tree(tmp_path)
    documented = hooks_tree(tmp_path / "documented")
    folder = skill(tmp_path / "example", "name: example\nhooks:\n  Stop:\n    - bye.sh\n")

    unheard_of = convert(folder, SOURCE, TARGET, root=silent, allow_stale=True)
    written_down = convert(folder, SOURCE, TARGET, root=documented, allow_stale=True)

    assert properties(unheard_of.report)["hook.event.Stop"] == ("unknown", "extension", "lossy")
    assert unheard_of.report["advice"] == written_down.report["advice"]
    assert len(unheard_of.report["advice"]) == 3
    assert unheard_of.report["advice"] == list(WORKAROUNDS["hook-event"])


def test_the_lost_veto_names_every_hook_it_was_asked_about(tmp_path: Path) -> None:
    """Two declared events, one row for the power to stop them, and both events named in it.

    `hook.decision.block` is asked once however many hooks the skill declares. Naming the
    first of them and dropping the rest reads as though only that one loses its veto.
    """
    root = hooks_tree(tmp_path)
    folder = skill(
        tmp_path / "example",
        "name: example\nhooks:\n  PreToolUse:\n    - guard.sh\n  Stop:\n    - bye.sh\n",
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)
    found_as = {entry["id"]: entry["found_as"] for entry in result.report["properties"]}

    assert "PreToolUse" in found_as["hook.decision.block"]
    assert "Stop" in found_as["hook.decision.block"]


def assembly_tree(tmp_path: Path) -> Path:
    """The four-row descriptions, plus a target that names where a skill of it lives."""
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
            {"id": "skill.frontmatter.deprecated", "support": "unsupported"},
        ],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
            {"id": "skills.user", "path": "~/.gemini/config/skills/"},
            {"id": "hooks.project", "path": ".agents/hooks.json"},
        ],
    )
    return root


def test_the_skill_is_assembled_at_the_paths_the_target_description_names(tmp_path: Path) -> None:
    """`SKILL.md` and `scripts/` land where the description says; `sandbox/` is left behind.

    The expected paths are read off the description written above, not recomputed the way
    the code computes them. A directory the target names no place for is not carried over
    on a guess -- it keeps its row in the report, and the report says it was left behind for
    want of a destination, so that "we had nowhere to put it" cannot be mistaken for "we
    forgot about it": both look the same in a list of what was written.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts", "sandbox"))
    (folder / "scripts" / "run.sh").write_text("echo hi\n", encoding="utf-8")
    (folder / "sandbox" / "toy.txt").write_text("toy\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.report["skill"]["assembled_name"] == "example-antigravity"
    assert [(entry["from"], entry["to"]) for entry in result.report["written"]] == [
        ("SKILL.md", ".agents/skills/example-antigravity/SKILL.md"),
        ("scripts/", ".agents/skills/example-antigravity/scripts/"),
    ]
    carried = out / ".agents/skills/example-antigravity/scripts/run.sh"
    assert carried.read_text(encoding="utf-8") == "echo hi\n"
    assert (out / ".agents/skills/example-antigravity/SKILL.md").is_file()
    assert not (out / ".agents/skills/example-antigravity/sandbox").exists()
    assert any("sandbox/" in line for line in result.report["advice"])
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


def _an_ordinary_absolute_path(root: Path) -> tuple[str, Path | None, str]:
    return str(skill(root / "widget", "")), None, "widget"


def _a_relative_path(root: Path) -> tuple[str, Path | None, str]:
    skill(root / "widget", "")
    return "widget", root, "widget"


def _a_trailing_slash(root: Path) -> tuple[str, Path | None, str]:
    return f"{skill(root / 'widget', '')}/", None, "widget"


def _a_dot_invoked_from_inside_the_skill_folder(root: Path) -> tuple[str, Path | None, str]:
    folder = skill(root / "widget", "")
    return ".", folder, "widget"


def _a_dot_dot_invoked_from_a_subdirectory_of_it(root: Path) -> tuple[str, Path | None, str]:
    folder = skill(root / "widget", "", directories=("scripts",))
    return "..", folder / "scripts", "widget"


def _a_skill_folder_that_is_a_symbolic_link(root: Path) -> tuple[str, Path | None, str]:
    real = skill(root / "real-name", "")
    link = root / "installed-as"
    link.symlink_to(real)
    return str(link), None, "installed-as"


def _a_frontmatter_name_that_differs_from_the_folder_name(
    root: Path,
) -> tuple[str, Path | None, str]:
    return str(skill(root / "widget", "name: gizmo\n")), None, "gizmo"


NAME_CASES: dict[str, Callable[[Path], tuple[str, Path | None, str]]] = {
    "an-ordinary-absolute-path": _an_ordinary_absolute_path,
    "a-relative-path": _a_relative_path,
    "a-trailing-slash": _a_trailing_slash,
    "a-dot-invoked-from-inside-the-skill-folder": _a_dot_invoked_from_inside_the_skill_folder,
    "a-dot-dot-invoked-from-a-subdirectory-of-it": _a_dot_dot_invoked_from_a_subdirectory_of_it,
    "a-skill-folder-that-is-a-symbolic-link": _a_skill_folder_that_is_a_symbolic_link,
    "a-frontmatter-name-that-differs-from-the-folder-name": (
        _a_frontmatter_name_that_differs_from_the_folder_name
    ),
}
"""How the same skill is named regardless of how its folder is spelled on the command line.

Each builder returns what is passed to `convert`, where to run it from (`None` for the
current directory), and the name the run must settle on. `..` from a subdirectory is the
defect this rule replaces: `Path("..").name` reads as `".."`, which is not empty, so the old
two-branch heuristic took it as the skill's own name and assembled the result outside
`.agents/skills/` entirely rather than inside a folder there. `os.path.abspath` answers `..`,
`.` and a trailing slash from the one expression that never touches the filesystem, and never
follows the link of the last case -- a link keeps the name it is invoked by.
"""


@pytest.mark.parametrize("case", sorted(NAME_CASES))
def test_the_skill_name_follows_one_rule_however_the_folder_is_spelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """The frontmatter's `name` wins; short of one, the folder's own last component does --
    and the assembled destination is built from that name and never lands outside
    ``.agents/skills/``, whichever of the seven ways above the folder was named by.
    """
    root = assembly_tree(tmp_path)
    given, chdir_to, expected = NAME_CASES[case](tmp_path / case / "skill-root")
    if chdir_to is not None:
        monkeypatch.chdir(chdir_to)
    out = tmp_path / case / "out"

    result = convert(given, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assembled = f"{expected}-antigravity"
    assert result.report["skill"]["name"] == expected
    assert result.report["skill"]["assembled_name"] == assembled
    assert {
        "from": "SKILL.md",
        "to": f".agents/skills/{assembled}/SKILL.md",
        "path": str(out / ".agents/skills" / assembled / "SKILL.md"),
    } in result.report["written"]


INVALID_NAMES = ("Uppercase", "under_score", "has space", "-leading", "trailing-", "")
"""Six ways a name fails the rule: none of them is quietly repaired into the directory name."""


@pytest.mark.parametrize("bad_name", INVALID_NAMES)
def test_a_frontmatter_name_that_fails_the_rule_is_refused_not_substituted(
    tmp_path: Path, bad_name: str
) -> None:
    """Exit code 6, nothing assembled, and the report names the offending value.

    Never a fall back to the directory name the folder happens to sit in: that would leave
    the caller believing the frontmatter's own choice of name had been honoured.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "widget", f"name: {json.dumps(bad_name)}\n")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 6
    assert result.verdict is Verdict.UNDECIDABLE
    assert result.report["properties"] == []
    assert result.report["written"] == []
    assert not out.exists()
    assert repr(bad_name) in result.report["error"]


def test_a_name_that_only_overflows_once_the_target_suffix_is_appended_is_refused(
    tmp_path: Path,
) -> None:
    """64 characters passes on its own; the target's own suffix can still push it over.

    Refused rather than truncated: shortening a name someone chose is its own kind of loss,
    and no row of the assembly table produces it.
    """
    root = assembly_tree(tmp_path)
    long_name = "a" * 60
    folder = skill(tmp_path / "widget", f"name: {long_name}\n")

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert result.exit_code == 6
    assert result.verdict is Verdict.UNDECIDABLE
    assert long_name in result.report["error"]
    assert "antigravity" in result.report["error"]


def test_a_skill_folder_that_is_a_loop_of_links_is_answered_with_a_report_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    """A skill folder that is itself a loop of links is a refusal, not a crash.

    `_findings` already refuses this as exit code 6, `no such folder` -- `Path.is_dir()`
    answers `False` for a cycle rather than raising. The report is then built from that
    refusal, and building it must not resolve the very folder that could not be read: doing
    so raises the `RuntimeError` a loop of links gives `Path.resolve()`, uncaught by the
    `ConvertError`/`OSError` handler around it, leaving a traceback and exit code 1 where the
    caller was promised a report and exit code 6.
    """
    root = four_row_tree(tmp_path)
    loop = tmp_path / "loop"
    loop.mkdir()
    (loop / "a").symlink_to(loop / "b")
    (loop / "b").symlink_to(loop / "a")

    result = convert(loop / "a", SOURCE, TARGET, root=root, allow_stale=True)

    assert result.exit_code == 6
    assert result.verdict is Verdict.UNDECIDABLE
    assert result.report["properties"] == []
    assert result.report["skill"]["name"] == "a"


def test_a_part_only_the_target_names_a_place_for_is_clean_not_undeclared(
    tmp_path: Path,
) -> None:
    """``compare`` matches only what the source declares -- the target may know more.

    ``examples/`` is a directory only `google/antigravity`'s own layout names a place for;
    neither `anthropic/claude-code` nor the open specification it extends mentions it. The
    very same run copies it to the path the target names, so the row must not read as
    "undeclared" while the assembly acts on exactly the declaration it denies.
    """
    root = assembly_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
            {"id": "skill.frontmatter.deprecated", "support": "unsupported"},
        ],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"},
            {"id": "skill.dir.examples", "path": "<skill-name>/examples/"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n", directories=("examples",))
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)
    rows = {entry["id"]: entry for entry in result.report["properties"]}

    assert properties(result.report)["skill.dir.examples"] == ("reproduced", "extension", "clean")
    note = rows["skill.dir.examples"]["note"] or ""
    assert "undeclared" not in note.lower()
    assert {
        "from": "examples/",
        "to": ".agents/skills/example-antigravity/examples/",
        "path": str(out / ".agents/skills/example-antigravity/examples"),
    } in result.report["written"]
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_a_target_only_capability_is_judged_by_its_support_not_by_having_a_note(
    tmp_path: Path,
) -> None:
    """A capability only the target names still carries the target's own verdict on it.

    `compare` never carries `skill.frontmatter.deprecated` or `skill.frontmatter.confidential`:
    the source description does not declare either, so there is no `Gap`. The target's own
    capabilities do, and say one is unsupported and the other supported -- a documented
    answer this run must not collapse to "reproduced" (keyed on a `note` being present) or
    to "unknown" (keyed on one being absent) instead of reading the `support` it was given.
    """
    root = tmp_path / "specs"
    write(
        root,
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
        ],
    )
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
            {
                "id": "skill.frontmatter.deprecated",
                "support": "unsupported",
                "note": "Antigravity ignores this field entirely.",
            },
            {"id": "skill.frontmatter.confidential", "support": "supported"},
        ],
        layout=[
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\ndeprecated: true\nconfidential: true\n")

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert properties(result.report)["skill.frontmatter.deprecated"] == (
        "missing",
        "extension",
        "lossy",
    )
    assert properties(result.report)["skill.frontmatter.confidential"] == (
        "reproduced",
        "extension",
        "clean",
    )
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


def test_a_line_only_starting_with_three_dashes_does_not_close_the_frontmatter(
    tmp_path: Path,
) -> None:
    """The header closes at a line that is exactly `---`, not at one merely starting with it.

    `---note: below` is a valid YAML key and reads as a frontmatter line to a careless
    scanner, but every conventional frontmatter reader treats it as content, not as the
    closing delimiter. Closing early there would hide every key past it -- `allowed-tools`
    among them -- from grading while still copying the file byte for byte.
    """
    root = tmp_path / "specs"
    write(
        root,
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
            {"id": "skill.frontmatter.allowed-tools", "support": "supported"},
        ],
    )
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
            {
                "id": "skill.frontmatter.allowed-tools",
                "support": "unsupported",
                "note": "Antigravity carries no tool allow-list.",
            },
        ],
        layout=[
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
        ],
    )
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: tidy-imports\ndescription: sorts your imports\n---note: below\n"
        "allowed-tools: [Bash, WebFetch]\n---\n\nBody.\n",
        encoding="utf-8",
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert properties(result.report)["skill.frontmatter.allowed-tools"] == (
        "missing",
        "extension",
        "lossy",
    )


def test_a_header_whose_lines_end_in_crlf_closes_where_a_reader_sees_it_close(
    tmp_path: Path,
) -> None:
    """A skill file written on Windows is a skill file: `\r\n` closes the header as `\n` does.

    The closing line of a CRLF file is `---\r\n`, and a pattern that admits only a bare
    `\n` never finds it -- the whole file reads as an unclosed header and the run refuses a
    skill every editor, every frontmatter reader and both target environments accept.
    """
    root = assembly_tree(tmp_path)
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "SKILL.md").write_bytes(
        b"---\r\ndescription: what it does\r\nname: example\r\n---\r\n\r\nBody.\r\n"
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert result.exit_code != 6
    assert result.report["skill"]["name"] == "example"


def test_a_symbolic_link_inside_the_skill_folder_is_carried_as_a_link_and_named(
    tmp_path: Path,
) -> None:
    """A link is never read, whatever it points at: copied as a link and named in the advice.

    Reading through a link inside the skill folder -- `scripts -> ~/.ssh`, say -- would
    materialise a stranger's files as real bytes inside the converted skill, in a run that
    still called itself clean. The link is carried over as a link, and the report says so.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "id_rsa").write_text("do-not-copy\n", encoding="utf-8")
    (folder / "scripts").symlink_to(secret)
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    staged = out / ".agents/skills/example-antigravity/scripts"
    assert staged.is_symlink()
    assert os.readlink(staged) == str(secret)
    assert any("symbolic link" in line and "scripts" in line for line in result.report["advice"])


def test_a_skill_file_that_is_a_symbolic_link_is_read_and_assembled_whole(
    tmp_path: Path,
) -> None:
    """`SKILL.md` is the one file the whole run reads to grade the skill; it is not carried as
    a link the way a bundled directory's own link is.

    Carrying it over as a link would stage a link relative to where the skill folder itself
    sits, almost never resolvable under `out`, while the report still called the run clean
    and said the file was written -- half an assembled skill mistaken for a whole one. The
    file this run already read to reach its verdict is written as the bytes it was graded
    from, not as a pointer back to them.
    """
    root = assembly_tree(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    content = "---\nname: example\ndescription: what it does\n---\n\nBody.\n"
    (real / "SKILL.md").write_text(content, encoding="utf-8")
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "SKILL.md").symlink_to(real / "SKILL.md")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    staged = out / ".agents/skills/example-antigravity/SKILL.md"
    assert not staged.is_symlink()
    assert staged.read_text(encoding="utf-8") == content
    assert not any(
        "SKILL.md" in line and "symbolic link" in line for line in result.report["advice"]
    )
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_an_occupied_destination_stops_the_assembly_and_keeps_what_is_there(
    tmp_path: Path,
) -> None:
    """Exit code 8, the file that was there is still there, and the verdict is still the table's.

    The check runs over the whole plan before the first copy: a run that overwrote two
    files and then refused the third would have destroyed what it refused to touch.

    Being unable to write is not a judgement about the skill. This one transfers without
    loss; only the place was taken. A report that answered `undecidable` here would be
    saying the descriptions do not settle what the skill becomes, which is exit code 3 and
    is not what happened.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts",))
    out = tmp_path / "out"
    occupied = out / ".agents/skills/example-antigravity/scripts"
    occupied.mkdir(parents=True)
    (occupied / "run.sh").write_text("mine\n", encoding="utf-8")

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 8)
    assert result.report["outcome"] == "clean"
    assert (occupied / "run.sh").read_text(encoding="utf-8") == "mine\n"
    assert not (out / ".agents/skills/example-antigravity/SKILL.md").exists()
    assert result.report["written"] == []
    assert result.report["error"]


def test_two_parts_of_one_plan_aimed_at_one_destination_stop_it_before_the_first_write(
    tmp_path: Path,
) -> None:
    """Exit code 8, nothing under `out`, and neither file reported as written.

    A description keeps its `id` unique and says nothing about `path`, so a target may
    legitimately give two entries the same destination; noticing that the plan then writes
    twice to one place is this command's work. Left alone, the second copy lands on the
    first and `written` reports both as carried over -- a report saying a file arrived
    where another file is.
    """
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[{"id": "skill.frontmatter.name", "support": "supported"}],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skill.top.README.md", "path": "<skill-name>/doc.md"},
            {"id": "skill.top.NOTES.md", "path": "<skill-name>/doc.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n")
    (folder / "README.md").write_text("read me\n", encoding="utf-8")
    (folder / "NOTES.md").write_text("notes\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 8
    assert result.report["written"] == []
    assert not out.exists()
    assert result.report["error"]


def test_a_copy_that_fails_part_way_leaves_no_half_assembled_skill(tmp_path: Path) -> None:
    """A file this process cannot read, inside a bundle: exit code 7, a report, and empty `--out`.

    The refusal is an operating system error like any other -- reaching the caller as a
    traceback it would exit 1, the code for a transfer that lost something, on a run that
    transferred nothing. The skill file was copied before the bundle failed, and it is taken
    back: half an assembled skill on disk is indistinguishable from a whole one.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts",))
    locked = folder / "scripts" / "locked"
    locked.write_text("secret\n", encoding="utf-8")
    locked.chmod(0o000)
    out = tmp_path / "out"

    try:
        result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)
    finally:
        locked.chmod(0o644)

    assert result.exit_code == 7
    assert result.report["written"] == []
    assert result.report["error"]
    # What is left, and not merely what is not: the empty skeleton of the destination and
    # nothing else -- no file, and no half-copied bundle. A run that left the copied
    # `SKILL.md`, or the half-copied bundle it never finished, would pass a test that only
    # counted files it could open.
    assert sorted(entry.relative_to(out).as_posix() for entry in out.rglob("*")) == [
        ".agents",
        ".agents/skills",
        ".agents/skills/example-antigravity",
    ]


def test_a_run_that_could_not_be_decided_assembles_nothing(tmp_path: Path) -> None:
    """`allowed-tools` is a field of the open format the target is silent about: no transfer.

    Exit code 3 says the descriptions do not settle what this skill becomes in the target
    environment. Writing the transferable half of it anyway would hand the caller a folder
    that looks like a converted skill and is not one.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\nallowed-tools: [Read]\n")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.UNDECIDABLE, 3)
    assert result.report["written"] == []
    assert not out.exists()


def test_without_out_nothing_is_written(tmp_path: Path) -> None:
    """The default is a report and no file: another filesystem is not touched unasked."""
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts",))

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert result.report["written"] == []


def test_only_a_hook_the_target_fires_is_staged_and_the_report_says_where_it_belongs(
    tmp_path: Path,
) -> None:
    """`PreToolUse` is staged beside the skill, `Stop` is not, and the entry is not merged.

    `.agents/hooks.json` belongs to the whole workspace and may already hold entries of
    someone else's; merging into it is FR-40. So the ready entry lands beside the assembled
    skill and the report names the file it has to be added to, and says who adds it.
    """
    root = hooks_tree(tmp_path)
    folder = skill(
        tmp_path / "example",
        "name: example\nhooks:\n  PreToolUse:\n    - guard.sh\n  Stop:\n    - bye.sh\n",
    )
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    staged = out / "hooks.json"
    assert json.loads(staged.read_text(encoding="utf-8")) == {"hooks": {"PreToolUse": ["guard.sh"]}}
    assert {
        "from": "frontmatter key `hooks`",
        "to": ".agents/hooks.json",
        "path": str(staged),
    } in result.report["written"]
    assert any(".agents/hooks.json" in line for line in result.report["advice"])


def test_a_hook_the_target_fires_and_names_no_file_for_is_not_dropped_in_silence(
    tmp_path: Path,
) -> None:
    """Nothing else is lost here, so exit code 0 is what the run would give -- on a lost hook.

    A hook is the one thing a target can reproduce and still have nowhere to put: the event
    is a capability and the file a hook is written in is a layout entry, and a description
    that declares the first owes nothing about the second. A bundled directory with no place
    gets a line saying it stayed behind; the declaration gets the same line, and a code that
    is not the one for a skill that transferred whole.
    """
    root = hooks_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
            {"id": "skill.frontmatter.hooks", "support": "supported"},
            {"id": "hook.event.PreToolUse", "kind": "hook-event", "support": "supported"},
            {"id": "hook.decision.block", "kind": "hook-decision", "support": "supported"},
        ],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\nhooks:\n  PreToolUse:\n    - guard.sh\n")
    out = tmp_path / "out"

    reported = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)
    assembled = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    # The same skill and the same two descriptions, asked twice: one run was asked for the
    # bytes and the other only for the answer. Whether a part has a place is read off the
    # layout of the target, so both runs know it, and a flag that changes what is written
    # must not change what the transfer is said to cost.
    assert (reported.verdict, reported.exit_code) == (assembled.verdict, assembled.exit_code)
    assert (reported.verdict, reported.exit_code) == (Verdict.LOSSY, 1)
    assert not (out / "hooks.json").exists()
    assert any("`hooks`" in line for line in reported.report["advice"])


def test_a_target_with_nowhere_to_put_a_skill_answers_the_same_either_way(tmp_path: Path) -> None:
    """No place for a skill file is no place whether or not the bytes were asked for.

    Nothing about this skill is lost in the transfer -- both its keys are reproduced -- so
    the run would otherwise be clean. What is not known is where any of it goes, and that is
    read off the layout of the target, not off the filesystem: a report-only run that
    answered `clean` here would be saying the descriptions settle something they do not.
    """
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
        ],
        layout=[{"id": "skill.dir.scripts", "path": "<skill-name>/scripts/"}],
    )
    folder = skill(tmp_path / "example", "name: example\n")

    reported = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)
    assembled = convert(folder, SOURCE, TARGET, root=root, out=tmp_path / "out", allow_stale=True)

    assert (reported.verdict, reported.exit_code) == (assembled.verdict, assembled.exit_code)
    assert (reported.verdict, reported.exit_code) == (Verdict.UNDECIDABLE, 3)
    assert reported.report["error"]


def test_the_report_names_the_place_the_bytes_are(tmp_path: Path) -> None:
    """A `..` in a layout path that stays under `out`: the report names where the file is.

    `written` is what a caller reads to find what this run produced, and a path that leads
    to the file only once an operating system has worked out what the `..` meant is not that
    -- it is the path the run held before it knew. The bytes go to the place the checks were
    made about, and that place is what is reported.
    """
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
        ],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/../SKILL.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    written = result.report["written"][0]["path"]
    assert written == str(out / ".agents/skills/SKILL.md")
    assert Path(written).is_file()


@pytest.mark.parametrize("already_there", [True, False])
def test_a_destination_that_collapses_onto_out_is_refused_either_way(
    tmp_path: Path, already_there: bool
) -> None:
    """`out` is the folder a result is assembled in, and never one part of that result.

    Answered before anything on disk is looked at, because the fault is in the plan and not
    in what happens to be there: met as an empty name, `out` would be replaced by whichever
    part landed on it -- the folder the caller named turned into a file -- and the run would
    report that as a part carried over.
    """
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
            {"id": "skill.frontmatter.description", "support": "supported"},
        ],
        layout=[
            {"id": "skill.file", "path": ".."},
            {"id": "skills.project", "path": "<workspace-root>/x/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n")
    out = tmp_path / "out"
    if already_there:
        out.mkdir()

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 7
    assert result.report["written"] == []
    assert not out.is_file()


def test_a_destination_whose_last_step_climbs_out_of_out_is_refused(tmp_path: Path) -> None:
    """`out/..` is the folder above `out`, and a step back is not a name to write under.

    The check resolves the parent and keeps the last name as written, so that a link at the
    destination stays an occupied place rather than an escape. A `..` in that position is
    not a name but a step, and read as a name it would pass for a path under `out` -- and be
    answered, one check later, as a place that is merely taken.
    """
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[{"id": "skill.frontmatter.name", "support": "supported"}],
        layout=[
            {"id": "skill.file", "path": ".."},
            {"id": "skills.project", "path": "<workspace-root>/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 7
    assert result.report["written"] == []


def test_a_plan_that_leaves_out_and_writes_twice_answers_for_leaving_out(tmp_path: Path) -> None:
    """Both wrong at once: the code names the promise broken, not the lesser of the two.

    Writing outside `--out` is the one thing this command promises never to do; writing twice
    into one place is a plan of ours that would lose a file. Answered with code 8, the run
    would report a collision and say nothing about having been about to write into somebody
    else's folder, and the collision is the part that is fixed by editing the description.
    """
    root = four_row_tree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[{"id": "skill.frontmatter.name", "support": "supported"}],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skill.top.README.md", "path": "<skill-name>/doc.md"},
            {"id": "skill.top.NOTES.md", "path": "<skill-name>/doc.md"},
            {"id": "skills.project", "path": f"{elsewhere}/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n")
    (folder / "README.md").write_text("read me\n", encoding="utf-8")
    (folder / "NOTES.md").write_text("notes\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 7
    assert not elsewhere.exists()
    assert result.report["written"] == []


def test_a_date_in_the_header_is_staged_as_the_text_iso_8601_spells(tmp_path: Path) -> None:
    """Two unquoted timestamps reach the staged entry as the text they were written as.

    An unquoted date is ordinary YAML and an ordinary thing to write in a header, and PyYAML
    hands it over as a `date` -- which JSON has no type for. Left to `json.dumps` it is a
    `TypeError` past every handler: no report and exit code 1, the code that says the skill
    transferred with known losses. Written out by `str()` instead, the `T` a person typed
    comes back a space, so the expected text below is the text of the file and not what
    printing the value happens to give.
    """
    root = hooks_tree(tmp_path)
    folder = skill(
        tmp_path / "example",
        "name: example\nhooks:\n  PreToolUse:\n    - 2026-09-14\n    - 2026-09-14T10:00:00+03:00\n",
    )
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert json.loads((out / "hooks.json").read_text(encoding="utf-8")) == {
        "hooks": {"PreToolUse": ["2026-09-14", "2026-09-14T10:00:00+03:00"]}
    }
    assert result.exit_code == 1


def test_the_user_level_destination_is_the_home_folder_and_the_bytes_stay_under_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--scope user` takes the other layout entry, and `~` in it is the home folder.

    The assembly still happens under `out`: expanding `~` decides what the report calls the
    destination, not where this command writes. A converter that reached into the home
    folder because a path in a description begins with a tilde would be changing the
    caller's environment as a side effect of being asked what a transfer costs.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, scope=Scope.USER, allow_stale=True)

    assert result.report["written"] == [
        {
            "from": "SKILL.md",
            "to": f"{home}/.gemini/config/skills/example-antigravity/SKILL.md",
            "path": str(out / ".gemini/config/skills/example-antigravity/SKILL.md"),
        }
    ]
    assert (out / ".gemini/config/skills/example-antigravity/SKILL.md").is_file()
    assert not home.exists()


def test_a_destination_the_description_puts_outside_out_is_refused(tmp_path: Path) -> None:
    """A layout path that is absolute leads out of `out`, and the run refuses to follow it.

    `Path(out) / "/somewhere"` is `/somewhere`: joining an absolute path throws the root
    away without a word. A description is data like any other, and the promise that this
    command writes only under `out` cannot rest on every description being well behaved.

    The plan failed the check made before the first byte is written, which is exit code 7 --
    not code 3. Being unable to write is not a judgement about the skill, so the verdict the
    table computed stands, exactly as it does when the destination is already occupied.
    """
    root = four_row_tree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[{"id": "skill.frontmatter.name", "support": "supported"}],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skills.project", "path": f"{elsewhere}/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert not elsewhere.exists()
    assert result.report["written"] == []
    assert result.report["error"]
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 7)


def test_a_dangling_link_at_the_destination_is_an_occupied_place(tmp_path: Path) -> None:
    """A symbolic link pointing nowhere is not an empty place, and is not written through.

    `exists()` answers `False` for a link whose target is missing, and writing to the link
    then creates that target -- outside `out`, under a name the caller never named. The
    place is taken by the link itself, whatever it points at.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    out = tmp_path / "out"
    (out / ".agents/skills/example-antigravity").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (out / ".agents/skills/example-antigravity/SKILL.md").symlink_to(elsewhere / "SKILL.md")

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 8
    assert list(elsewhere.iterdir()) == []
    assert result.report["written"] == []


def test_a_link_partway_down_the_destination_is_not_written_through(tmp_path: Path) -> None:
    """A link at a level above the destination is a door out of it, and is refused as one.

    The check that a destination stays under `out` follows links, so one pointing away is
    already caught. This one points back inside `out`, which that check is content with --
    and it is still a path component this run did not create and cannot vouch for a moment
    later. `mkdir(parents=True, exist_ok=True)` walks through it without a word, so the
    question has to be asked of every level and not only of the last one.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    out = tmp_path / "out"
    (out / "real").mkdir(parents=True)
    (out / ".agents").symlink_to(out / "real")

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 7
    assert result.report["written"] == []
    assert list((out / "real").iterdir()) == []


def test_a_loop_of_links_at_out_is_answered_with_a_report_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    """Two links pointing at each other are still a destination, and a destination is answered.

    `Path.resolve()` raises `RuntimeError` on a cycle up to 3.12, which is neither a
    `ConvertError` nor an `OSError`, so the run left as a traceback and the exit code 1 the
    caller reads as "moved, and here is what it cost". A cycle is a place nothing can be
    written to, which is what code 7 says.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    loop = tmp_path / "loop"
    loop.mkdir()
    (loop / "a").symlink_to(loop / "b")
    (loop / "b").symlink_to(loop / "a")

    result = convert(folder, SOURCE, TARGET, root=root, out=loop / "a", allow_stale=True)

    assert result.exit_code == 7
    assert result.report["written"] == []
    assert result.report["error"]


def test_a_file_beside_the_skill_file_gets_a_row_and_is_never_lost_in_silence(
    tmp_path: Path,
) -> None:
    """A `README.md` at the top of the skill folder is content, and content is not dropped.

    Neither description says what the target environment does with a file that is neither
    `SKILL.md` nor part of a bundle it names, so nothing is known about it -- and exit code
    0 on a folder that lost a file is the one answer this command must never give.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    (folder / "README.md").write_text("How this works.\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)
    rows = {entry["id"]: entry for entry in result.report["properties"]}

    assert properties(result.report) == {
        "skill.frontmatter.name": ("reproduced", "extension", "clean"),
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
        "skill.top.README.md": ("unknown", "extension", "lossy"),
    }
    assert rows["skill.top.README.md"]["found_as"] == "top-level file `README.md`"
    assert any("README.md" in line for line in result.report["advice"])
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


def test_the_plain_values_of_a_header_cross_as_themselves(tmp_path: Path) -> None:
    """Refusing `.nan` narrows to three values: a fraction, a whole number and `on` cross.

    JSON holds all three, and this is the line the narrowing is drawn against: one type too
    wide and every skill that puts a number in a hook is refused, by a refusal that looks
    exactly like the one that belongs there. `on` is YAML's own spelling of true and crosses
    as `true`, which is the branch the narrowing split -- a `bool` is an `int` in Python and
    would leave as `1` if it were ever carried by the number half.
    """
    root = hooks_tree(tmp_path)
    folder = skill(
        tmp_path / "example", "name: example\nhooks:\n  PreToolUse:\n    - 1.5\n    - 3\n    - on\n"
    )
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)
    carried = json.loads((out / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]

    assert carried == [1.5, 3, True]
    # `3 == 3.0` and `True == 1`, so the line above holds even if the shapes were lost on the
    # way. The types are what says the file carries `3` and `true` rather than `3.0` and `1`,
    # and a file that says `1` where it said `true` is a different file to whatever reads it.
    assert [type(item) for item in carried] == [float, int, bool]
    assert result.exit_code == 1


def test_a_rewritten_header_value_is_named_in_the_report(tmp_path: Path) -> None:
    """The report says which value changed shape, what it was, and what it became.

    No `--out` here: the rewrite happened while the header was read, and a person has to be
    able to see it whether or not a file was written afterwards. Unsaid, the only trace of
    a value entering as a date and leaving as text would be the text itself -- and the exit
    code of such a run stands for something else entirely.
    """
    root = four_row_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\nmodel: 2026-09-14\n")

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)
    said = [line for line in result.report["advice"] if "frontmatter.model" in line]

    assert len(said) == 1
    assert "date" in said[0]
    assert "2026-09-14" in said[0]


def cli_arguments(folder: Path, root: Path) -> list[str]:
    """The one run both command-line tests make, as a list of arguments."""
    return [
        "convert",
        str(folder),
        "--source",
        SOURCE,
        "--target",
        TARGET,
        "--specs",
        str(root),
        "--allow-stale",
    ]


def test_standard_output_carries_the_json_report_and_nothing_else(tmp_path: Path) -> None:
    """A caller may pipe this command into a program that reads JSON, and `--report` frees it.

    This is checked through the command line because that is where the two streams exist:
    the seam returns both reports as values and cannot say which stream either went to. A
    line of prose printed beside the JSON breaks every caller that parses it, and breaks
    them silently -- which is why the report and the words for a person are separated here
    and not left to whoever remembers to redirect.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    arguments = cli_arguments(folder, root)

    piped = runner.invoke(app, arguments)
    into_file = tmp_path / "report.json"
    saved = runner.invoke(app, [*arguments, "--report", str(into_file)])

    assert (piped.exit_code, saved.exit_code) == (0, 0)
    assert json.loads(piped.stdout)["report_schema"] == 1
    assert piped.stderr.startswith(str(folder))
    assert saved.stdout == ""
    assert json.loads(into_file.read_text(encoding="utf-8")) == json.loads(piped.stdout)


def test_a_report_that_cannot_be_written_is_still_issued_and_says_so(tmp_path: Path) -> None:
    """`--report` into a folder that is not there: the report goes to standard output instead.

    A traceback would leave the command exiting 1, the code for a transfer that lost
    something -- an answer about the skill, given for a mistake in the arguments. And a run
    that swallowed the report because the file would not open would be breaking the one
    promise made about every outcome (FR-26), on the outcome nobody planned for.

    All three places have to agree on the number: what the report says, what the words for a
    person say, and what the process returns. The verdict is untouched -- the transfer costs
    what it cost before the report had nowhere to go.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    nowhere = tmp_path / "no-such-folder" / "report.json"

    result = runner.invoke(app, [*cli_arguments(folder, root), "--report", str(nowhere)])
    issued = json.loads(result.stdout)

    assert result.exit_code == 11
    assert issued["exit_code"] == 11
    assert issued["outcome"] == "clean"
    assert str(nowhere) in issued["error"]
    assert "(exit 11)" in result.stderr


def test_a_run_that_was_stopped_keeps_its_code_over_the_unwritten_report(tmp_path: Path) -> None:
    """Code 11 stands over a run nothing stopped, never over a refusal (FR-27).

    The folder below holds no `SKILL.md`, so the run stops at code 6 before it judges
    anything, and `--report` then names a place that does not exist either. A caller reads
    the code to learn what happened to the skill, and exiting 11 would answer about the
    report instead -- the later mishap costing the earlier stop its answer. Both reasons are
    in `error`, and the report is on standard output where an unwritten one goes.
    """
    root = assembly_tree(tmp_path)
    folder = tmp_path / "example"
    folder.mkdir()
    nowhere = tmp_path / "no-such-folder" / "report.json"

    result = runner.invoke(app, [*cli_arguments(folder, root), "--report", str(nowhere)])
    issued = json.loads(result.stdout)

    assert result.exit_code == 6
    assert issued["exit_code"] == 6
    assert str(folder) in issued["error"]
    assert str(nowhere) in issued["error"]
