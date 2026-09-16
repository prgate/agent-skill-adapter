"""Tests for the convert seam: one skill folder, two descriptions -> report and exit code."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from agent_skill_adapter import convert as convert_module
from agent_skill_adapter.assets import Asset, Finding, Inputs, Kind
from agent_skill_adapter.cli.main import app
from agent_skill_adapter.convert import WORKAROUNDS, Conversion, Scope, Verdict
from agent_skill_adapter.convert import convert as convert_set
from agent_skill_adapter.envspec.model import EnvSpec
from agent_skill_adapter.rules import Rules

runner = CliRunner()

TODAY = date(2026, 9, 14)
SOURCE = "anthropic/claude-code@1.0.0"
TARGET = "google/antigravity@1.0.0"

TRANSLATION = Rules.model_validate(
    {
        "rules_version": "1.0",
        "ignore": ["__pycache__", "*.py[co]"],
        "undocumented": {"action": "copy", "note": "nothing declares this file"},
    }
)
"""The translation rules every run here is given: the smallest ones that are valid."""


def convert(
    skill_dir: str | Path, source: str | None, target: str | None, **named: Any
) -> Conversion:
    """One skill folder, which is a composition of one part -- what the command line passes.

    The seam takes a set; the cases below are about one skill each, and a set of one is how
    they say so. A case about a composition of several parts passes `convert_set` directly.
    """
    return convert_set(
        Inputs(translation=TRANSLATION, skill=(Path(os.path.abspath(skill_dir)),)),
        source,
        target,
        **named,
    )


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


def rows(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every row of every entity of the report, by the entry id it asked about."""
    return {
        entry["id"]: entry
        for asset in report["assets"]
        for entry in asset["properties"]
        if entry["id"] is not None
    }


def properties(report: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    """Every property of the report as id -> (outcome, origin, verdict)."""
    return {
        entry_id: (entry["outcome"], entry["origin"], entry["verdict"])
        for entry_id, entry in rows(report).items()
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
    assert result.report["report_schema"] == 2


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
    found = rows(result.report)

    assert properties(result.report) == {
        "skill.frontmatter.name": ("reproduced", "extension", "clean"),
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
        "skill.frontmatter.telepathy": ("unknown", "extension", "lossy"),
        "skill.dir.sandbox": ("unknown", "extension", "lossy"),
    }
    assert found["skill.frontmatter.telepathy"]["found_as"] == "frontmatter key `telepathy`"
    assert found["skill.dir.sandbox"]["found_as"] == "bundled directory `sandbox/`"
    assert found["skill.dir.sandbox"]["note"]
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


def test_a_folder_that_could_not_be_read_stops_the_run_and_still_reports(
    tmp_path: Path,
) -> None:
    """Exit code 6, no entity judged, and a report that names the folder it could not read.

    What makes a skill file unreadable is the reading's own business and is pinned where the
    reading lives (`tests/unit/test_assets.py`); what is pinned here is the answer this
    command gives for it -- a report and a code, never a traceback.
    """
    root = four_row_tree(tmp_path)
    folder = tmp_path / "example"
    folder.mkdir()

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert result.exit_code == 6
    assert result.verdict is Verdict.UNDECIDABLE
    assert result.report["assets"] == []
    assert result.report["report_schema"] == 2
    assert str(folder) in result.report["error"]
    # The folder is there and holds no skill file, so that is what the refusal says. The
    # case below is the other one, and the two must not answer in each other's words.
    assert "SKILL.md" in result.report["error"]


def test_a_path_that_is_not_there_is_refused_as_a_path_and_not_as_a_missing_skill_file(
    tmp_path: Path,
) -> None:
    """A path nobody has is a path to correct, and the refusal says so in those words.

    Answered with "no SKILL.md here", a person with a typo in the path is sent looking for a
    file inside a folder that does not exist -- a true sentence about nothing, and the wrong
    thing to go and do. The code and the report are the same either way; the reason is not.
    """
    root = four_row_tree(tmp_path)
    missing = tmp_path / "definitely-not-there"

    result = convert(missing, SOURCE, TARGET, root=root, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.UNDECIDABLE, 6)
    assert result.report["assets"] == []
    assert str(missing) in result.report["error"]
    assert "SKILL.md" not in result.report["error"]


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
    assert result.report["assets"] == []
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
    assert result.report["assets"] == []


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
    assert result.report["assets"] == []
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
            {"id": "hooks.project", "path": "<workspace-root>/.agents/hooks.json"},
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
    found_as = {entry_id: entry["found_as"] for entry_id, entry in rows(result.report).items()}

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

    assert result.report["assets"][0]["assembled_name"] == "example-antigravity"
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


def test_nothing_the_rules_keep_out_is_written_inside_a_directory_that_is(
    tmp_path: Path,
) -> None:
    """A row saying a path was kept out and the same path on disk are one run contradicting itself.

    The ignore list speaks while the set is read, and the bundled directory holding the path
    is carried whole afterwards -- so the two have to agree at the copy as well, or the
    report says a build cache stayed behind while five files of it are in the assembled
    skill, under an exit code calling the transfer clean. Asked of the disk against the
    rules rather than against the wording of any row: what the report calls it is not the
    defect, being there is.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts",))
    (folder / "scripts" / "run.sh").write_text("echo hi\n", encoding="utf-8")
    (folder / "scripts" / "__pycache__").mkdir()
    (folder / "scripts" / "__pycache__" / "run.cpython-310.pyc").write_bytes(b"\x00")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    kept_out = [
        entry["found_as"]
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if entry["outcome"] == "out-of-scope"
    ]
    assert kept_out == ["scripts/__pycache__/"]
    assert (out / ".agents/skills/example-antigravity/scripts/run.sh").is_file()
    assert [
        path.relative_to(out).as_posix()
        for path in sorted(out.rglob("*"))
        if TRANSLATION.ignored(path.relative_to(out).as_posix())
    ] == []


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
    assert result.report["assets"][0]["name"] == expected
    assert result.report["assets"][0]["assembled_name"] == assembled
    assert {
        "from": "SKILL.md",
        "to": f".agents/skills/{assembled}/SKILL.md",
        "path": str(out / ".agents/skills" / assembled / "SKILL.md"),
    } in result.report["written"]


INVALID_NAMES = (
    "Uppercase",
    "under_score",
    "has space",
    "-leading",
    "trailing-",
    "",
    "widget\n",
    "../evil",
)
"""Eight ways a name fails the rule: none of them is quietly repaired into the directory
name, and none of the last two is let through by a match that stops before the end of the
value -- a trailing newline and a `..` are what a path segment must never be built from."""


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
    assert result.report["assets"] == []
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

    The reading refuses it as exit code 6 -- `Path.is_file()` answers `False` for a cycle
    rather than raising. The report is then built from that refusal, and building it must not
    resolve the very folder that could not be read: doing so raises the `RuntimeError` a loop
    of links gives `Path.resolve()`, uncaught by the handler around it, leaving a traceback
    and exit code 1 where the caller was promised a report and exit code 6.
    """
    root = four_row_tree(tmp_path)
    loop = tmp_path / "loop"
    loop.mkdir()
    (loop / "a").symlink_to(loop / "b")
    (loop / "b").symlink_to(loop / "a")

    result = convert(loop / "a", SOURCE, TARGET, root=root, allow_stale=True)

    assert result.exit_code == 6
    assert result.verdict is Verdict.UNDECIDABLE
    assert result.report["assets"] == []
    assert str(loop / "a") in result.report["error"]


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
    found = rows(result.report)

    assert properties(result.report)["skill.dir.examples"] == ("reproduced", "extension", "clean")
    note = found["skill.dir.examples"]["note"] or ""
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


def test_a_target_environment_that_is_not_a_path_segment_is_the_descriptions_fault(
    tmp_path: Path,
) -> None:
    """Exit code 3, not 6: the skill is readable, and what is unusable is the description.

    The assembled name is the skill's own name suffixed with the target's `environment`, so
    an `environment` that is not lowercase-and-hyphens makes a name no folder can be called.
    Answered with code 6 that reads as "this skill folder could not be read" and sends a
    person to look at a skill file that is exactly as it should be.
    """
    root = tmp_path / "specs"
    write(
        root,
        vendor="anthropic",
        environment="claude-code",
        capabilities=[{"id": "skill.frontmatter.description", "support": "supported"}],
    )
    write(
        root,
        vendor="google",
        environment="Anti_Gravity",
        capabilities=[{"id": "skill.frontmatter.description", "support": "supported"}],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\n")

    result = convert(folder, SOURCE, "google/Anti_Gravity@1.0.0", root=root, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.UNDECIDABLE, 3)
    assert "Anti_Gravity" in result.report["error"]


def test_a_header_whose_lines_end_in_crlf_closes_where_a_reader_sees_it_close(
    tmp_path: Path,
) -> None:
    r"""A skill file written on Windows is a skill file: `\r\n` closes the header as `\n` does.

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
    assert result.report["assets"][0]["name"] == "example"


def test_the_words_for_a_person_cannot_be_forged_by_what_is_written_in_the_skill(
    tmp_path: Path,
) -> None:
    """A frontmatter key is a stranger's text: it never reaches a terminal as control characters.

    The summary is one line per property, and a key carrying a newline writes as many lines
    as it likes -- a forged row claiming a property transferred cleanly, indistinguishable
    from the rows this run actually computed. An escape sequence in the same place moves the
    cursor, repaints or wipes the screen of whoever ran the command. The machine-readable
    report is safe either way, because `json.dumps` escapes both; the words for a person are
    the sink that has to.
    """
    root = assembly_tree(tmp_path)
    folder = tmp_path / "example"
    folder.mkdir()
    forged = "x\n  clean        forged.row -- injected (reproduced, specification)"
    (folder / "SKILL.md").write_text(
        "---\ndescription: what it does\nname: example\n"
        f"{json.dumps(forged)}: 1\n{json.dumps(chr(27) + '[2Jwiped')}: 2\n---\n\nBody.\n",
        encoding="utf-8",
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)

    assert "\x1b" not in result.summary
    assert not any(
        line.startswith("  clean        forged.row") for line in result.summary.splitlines()
    )


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


def test_a_link_nested_inside_a_bundled_directory_is_named_by_its_path_within_it(
    tmp_path: Path,
) -> None:
    """The advice names `scripts/inner/link`, not `link` and not the directory that holds it.

    A link deep inside a copied directory is the one a caller has the hardest time finding,
    and a report naming only the leaf, or only the part it came in with, tells them a link
    exists somewhere under a directory they now have to walk themselves.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts",))
    (folder / "scripts" / "inner").mkdir()
    (folder / "scripts" / "inner" / "link").symlink_to(tmp_path / "elsewhere")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert any("`scripts/inner/link`" in line for line in result.report["advice"])


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
    # Said out loud, and not by being left out of the list: the run did read through a link
    # into a folder nobody named on the command line, and the advice says which one. The
    # verdict is still clean, because nothing about the skill was lost -- the wording has to
    # carry that, so it says the content was read and copied rather than that it was not read.
    assert any(
        "SKILL.md" in line and "symbolic link" in line and str(real / "SKILL.md") in line
        for line in result.report["advice"]
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


@pytest.mark.skipif(os.geteuid() == 0, reason="a mode of 000 does not stop root from reading")
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
    # A price and not a refusal, exactly as it is for every other kind: the skill stays where
    # it is and the report says why. A code 3 here would be this one skill deciding for the
    # whole run, and a set of twenty would lose the nineteen rows it had already earned.
    assert (reported.verdict, reported.exit_code) == (Verdict.LOSSY, 1)
    assert reported.report["error"] is None
    assert any("names no place" in line for line in reported.report["advice"])
    assert reported.report["assets"][0]["assembled_name"] is None
    assert assembled.report["written"] == []


def test_a_target_with_no_place_for_a_skill_keeps_the_rest_of_the_set_in_the_report(
    tmp_path: Path,
) -> None:
    """One root nobody named must not cost the other nineteen entities their rows.

    The refusal it used to be was raised before a single entity had been judged, so a set
    of many answered with an empty report about a run that never looked at most of it.
    """
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[{"id": "skill.frontmatter.description", "support": "supported"}],
        layout=[{"id": "agents.project", "path": ".agents/agents/"}],
    )
    skills = tmp_path / "set" / "bundles"
    skill(skills / "alpha", "name: alpha\n")

    result = convert_set(
        Inputs(translation=MOVING, skills=(skills,), agents=(subagents(tmp_path / "roles"),)),
        SOURCE,
        TARGET,
        root=root,
        out=tmp_path / "out",
        allow_stale=True,
    )
    named = {(asset["kind"], asset["name"]) for asset in result.report["assets"]}

    assert ("skill", "alpha") in named
    assert ("subagent", "note-keeper") in named
    # The subagent had somewhere to go and went there; only the skill stayed.
    assert [entry["to"] for entry in result.report["written"]] == [".agents/agents/note-keeper.md"]
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


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


@pytest.mark.parametrize("spelling", ["out", "a/../out"])
def test_a_link_partway_down_the_destination_is_not_written_through(
    tmp_path: Path, spelling: str
) -> None:
    """A link at a level above the destination is a door out of it, and is refused as one.

    The check that a destination stays under `out` follows links, so one pointing away is
    already caught. This one points back inside `out`, which that check is content with --
    and it is still a path component this run did not create and cannot vouch for a moment
    later. `mkdir(parents=True, exist_ok=True)` walks through it without a word, so the
    question has to be asked of every level and not only of the last one.

    Asked of both spellings of the same folder, because the levels are counted by text: with
    a `..` in `--out` the levels below it were compared against the spelling the caller typed
    rather than the one the bytes are written to, none of them matched, and every level in
    between went unasked -- the link was written through on a path the report then called
    clean.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    (tmp_path / "a").mkdir()
    out = tmp_path / spelling
    (tmp_path / "out" / "real").mkdir(parents=True)
    (tmp_path / "out" / ".agents").symlink_to(tmp_path / "out" / "real")

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 7
    assert result.report["written"] == []
    assert list((tmp_path / "out" / "real").iterdir()) == []


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
    found = rows(result.report)

    assert properties(result.report) == {
        "skill.frontmatter.name": ("reproduced", "extension", "clean"),
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
        "skill.top.README.md": ("unknown", "extension", "lossy"),
    }
    assert found["skill.top.README.md"]["found_as"] == "top-level file `README.md`"
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


def test_a_link_that_leads_nowhere_is_refused_as_the_link_it_is(tmp_path: Path) -> None:
    """A dangling link is blamed on the link and on what it points at, never on `SKILL.md`.

    `exists()` follows a link, so a link pointing at nothing answers it exactly as a path
    with nothing at it does -- and the reading, which asks whether there is a skill file at
    the path, answers both with the words for a folder that holds no skill file. That is the
    same false blame as a mistyped path, through a narrower door: the folder the person is
    sent to look inside is a link, and what is wrong is at the other end of it.
    """
    root = four_row_tree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    dangling = tmp_path / "widget"
    dangling.symlink_to(elsewhere)

    result = convert(dangling, SOURCE, TARGET, root=root, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.UNDECIDABLE, 6)
    assert result.report["assets"] == []
    assert str(dangling) in result.report["error"]
    assert str(elsewhere) in result.report["error"]
    assert "SKILL.md" not in result.report["error"]


def test_a_reason_the_run_has_no_rule_for_is_a_row_whose_verdict_still_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finding whose reason this run cannot weigh is `unknown`, and the run is not clean.

    The reading and this command version together, so a fifth reason cannot arrive today.
    The cost of being wrong about it is one-sided: taken for nothing to say, a reason nobody
    could read turns a lost file into exit code 0 -- an entity called clean because the
    program did not recognise why it was not. So the row is there, its verdict is counted
    with every other, and the words the reading used are still in it.

    The reading is replaced here rather than provoked: it has no fifth reason to give, and a
    rule about what to do with one cannot be pinned by a set that cannot produce it.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    unheard_of = Finding("scratch/", (), "a reason nobody has written a rule for")
    monkeypatch.setattr(
        convert_module, "read", lambda inputs: (Asset(Kind.SKILL, folder, "", {}, (unheard_of,)),)
    )

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)
    named = {
        entry["found_as"]: entry
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if entry["id"] is None
    }

    assert named["scratch/"]["outcome"] == "unknown"
    assert named["scratch/"]["verdict"] == "lossy"
    assert unheard_of.note in (named["scratch/"]["note"] or "")
    # The whole of it: a row that is there and whose weight is not added answers the same as
    # no row at all to a caller reading the code.
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)
    assert not any(unheard_of.note in line for line in result.report["advice"])


def a_set(tmp_path: Path) -> Inputs:
    """A composition of several parts, laid out under names nobody documented.

    Two skills, one of which loses a field the target calls unsupported; a subagent neither
    description has ever heard of; a build cache the rules keep out; and a file beside the
    subagents that is no subagent at all.
    """
    root = tmp_path / "set"
    skill(root / "bundles" / "alpha", "name: alpha\n")
    skill(root / "bundles" / "beta", "name: beta\ndeprecated: true\n")
    cache = root / "bundles" / "alpha" / "__pycache__"
    cache.mkdir()
    (cache / "stale.pyc").write_bytes(b"\x00")
    (root / "people").mkdir()
    (root / "people" / "helper.md").write_text(
        "---\nname: helper\ndescription: helps\n---\n\nYou help.\n", encoding="utf-8"
    )
    (root / "people" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
    return Inputs(translation=TRANSLATION, skills=(root / "bundles",), agents=(root / "people",))


def test_a_whole_set_is_one_report_whose_verdict_is_the_worst_of_it(tmp_path: Path) -> None:
    """One report, rows grouped under the entity they were found in, and one verdict.

    `alpha` transfers whole and `beta` loses a field the target calls unsupported, so the
    two entities answer differently and the run answers for the worse of them -- the way one
    skill already answers for the worst of its own rows. A caller reading an exit code must
    not have to add up a code per entity to learn that something in the set was lost.
    """
    root = assembly_tree(tmp_path)

    result = convert_set(a_set(tmp_path), SOURCE, TARGET, root=root, allow_stale=True)
    verdicts = {
        (asset["kind"], asset["name"]): asset["verdict"] for asset in result.report["assets"]
    }

    assert verdicts[("skill", "alpha")] == "clean"
    assert verdicts[("skill", "beta")] == "lossy"
    assert verdicts[("subagent", "helper")] == "lossy"
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)
    # Grouped, and not merely all present: the row about `beta` belongs to `beta`, or a set
    # of hundreds of files is a flat list nobody can read an entity out of.
    beta = next(asset for asset in result.report["assets"] if asset["name"] == "beta")
    assert "skill.frontmatter.deprecated" in {entry["id"] for entry in beta["properties"]}
    assert "skill.frontmatter.deprecated" not in {
        entry["id"]
        for asset in result.report["assets"]
        if asset["name"] == "alpha"
        for entry in asset["properties"]
    }


def test_every_path_of_the_set_gets_a_row_whatever_happens_to_it(tmp_path: Path) -> None:
    """A path kept out by rule and a file nobody declared are each a row, and different ones.

    Silence is the one failure this command could not be trusted after. What the rules keep
    out costs the transfer nothing and says so; a file no description declares is `unknown`
    and carries the one rule the translation states for such a file -- FR-30 asks for one
    rule and one row, not for a wording of our own beside the rules' own.
    """
    root = assembly_tree(tmp_path)

    result = convert_set(a_set(tmp_path), SOURCE, TARGET, root=root, allow_stale=True)
    named = {
        entry["found_as"]: entry
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if entry["id"] is None
    }

    assert named["__pycache__/"]["outcome"] == "out-of-scope"
    assert named["__pycache__/"]["verdict"] == "clean"
    assert named["diagram.svg"]["outcome"] == "unknown"
    assert named["diagram.svg"]["note"] == TRANSLATION.undocumented.note


def test_the_three_things_a_row_can_say_about_being_declared_are_three_rows(
    tmp_path: Path,
) -> None:
    """Both descriptions know the entry, only the target knows it, nobody knows it.

    "No entry with this id in either description" printed where the target does document the
    entry sends a person looking for a cause that is not there -- and the same run acts on
    exactly the declaration that line denies. Three cases, three answers, in one run so that
    the wordings cannot agree by accident.
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
            {"id": "skill.frontmatter.confidential", "support": "supported"},
        ],
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
    )
    folder = skill(tmp_path / "example", "name: example\nconfidential: true\ntelepathy: on\n")

    result = convert(folder, SOURCE, TARGET, root=root, allow_stale=True)
    found = rows(result.report)
    both = found["skill.frontmatter.name"]
    target_only = found["skill.frontmatter.confidential"]
    neither = found["skill.frontmatter.telepathy"]

    # Both know it: `compare` carried the entry, and there is no reason to give for silence.
    assert both["note"] is None
    # Only the target: a documented answer, so the row is not the one about nobody knowing.
    assert target_only["note"] is not None
    assert target_only["note"] != neither["note"]
    assert (target_only["outcome"], target_only["verdict"]) == ("reproduced", "clean")
    assert (neither["outcome"], neither["verdict"]) == ("unknown", "lossy")


TRANSLATING = Rules.model_validate(
    {
        "rules_version": "2.0",
        "value_maps": {
            "subagent.frontmatter.model": {"opus": "pro", "sonnet": "pro"},
            "subagent.frontmatter.tools": {"Read": "view_file", "Grep": "grep_search"},
        },
        "undocumented": {"action": "copy", "note": "nothing declares this file"},
    }
)
"""Rules that do translate something, versioned apart from the descriptions on purpose."""

SUBAGENT_FIELDS = (
    "subagent.frontmatter.name",
    "subagent.frontmatter.description",
    "subagent.frontmatter.model",
    "subagent.frontmatter.tools",
    "subagent.system-prompt-body",
)


SKILL_TRANSLATING = Rules.model_validate(
    {
        "rules_version": "2.0",
        "value_maps": {"skill.frontmatter.model": {"sonnet": "pro"}},
        "undocumented": {"action": "copy", "note": "nothing declares this file"},
    }
)
"""The same rules against the one kind this command assembles today: a skill."""


def translating_tree(tmp_path: Path) -> Path:
    """Descriptions where the target names a one-value set for the model field of a skill."""
    root = tmp_path / "specs"
    fields = [
        {"id": "skill.frontmatter.name", "support": "supported"},
        {"id": "skill.frontmatter.description", "support": "supported"},
        {"id": "skill.frontmatter.model", "support": "supported"},
        {"id": "skill.frontmatter.licence", "support": "supported"},
    ]
    write(root, vendor="anthropic", environment="claude-code", capabilities=fields)
    target: list[dict[str, Any]] = [dict(entry) for entry in fields]
    target[2]["values"] = ["pro"]
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=target,
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
        ],
    )
    return root


def a_subagent(folder: Path, frontmatter: str) -> Inputs:
    """A composition of one folder holding one subagent with the given extra header lines."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "note-keeper.md").write_text(
        f"---\nname: note-keeper\ndescription: keeps notes\n{frontmatter}---\n\nYou keep notes.\n",
        encoding="utf-8",
    )
    return Inputs(translation=TRANSLATING, agents=(folder,))


def value_tree(tmp_path: Path, *, values: list[str] | None) -> Path:
    """Descriptions of two environments that both know the subagent fields below.

    ``values`` is the closed set the *target* names for the model field, or ``None`` for a
    target that names none -- which is the whole of the difference these cases turn on.
    """
    root = tmp_path / "specs"
    fields = [
        {"kind": "subagent-field", "id": entry, "support": "supported"} for entry in SUBAGENT_FIELDS
    ]
    write(root, vendor="anthropic", environment="claude-code", capabilities=fields)
    target: list[dict[str, Any]] = [dict(entry) for entry in fields]
    if values is not None:
        target[SUBAGENT_FIELDS.index("subagent.frontmatter.model")]["values"] = values
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=target,
        # A place for a subagent, because a target that names none has nowhere to put one at
        # all -- a price of its own, and not what these cases about values turn on.
        layout=[{"id": "agents.project", "path": ".agents/agents/"}],
    )
    return root


def test_a_value_outside_the_targets_set_is_translated_and_the_report_names_both_versions(
    tmp_path: Path,
) -> None:
    """The applied rule is in the report -- what was there, what it became, by what rule.

    And both versions with it: the descriptions decide what the closed set is, the rules
    decide what a value outside it becomes, and the two are versioned apart, so a person
    repeating this run needs both numbers to get the same bytes back (FR-13.1).
    """
    root = value_tree(tmp_path, values=["inherit", "flash", "pro"])

    result = convert_set(
        a_subagent(tmp_path / "roles", "model: sonnet\n"),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )

    assert result.report["rules_version"] == "2.0"
    assert result.report["target"] == {
        "vendor": "google",
        "environment": "antigravity",
        "version": "1.0.0",
    }
    assert [
        (entry["id"], entry["from"], entry["to"]) for entry in result.report["translations"]
    ] == [("subagent.frontmatter.model", "sonnet", "pro")]
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_a_value_outside_the_set_and_outside_the_table_is_a_row_and_not_a_guess(
    tmp_path: Path,
) -> None:
    """Nothing is invented for it and nothing is dropped: the run says what it could not do.

    A value the target does not accept and the rules have no counterpart for is exactly the
    case a converter is tempted to resolve by picking the nearest-sounding word. The answer
    is a row naming the value and the reason, and a verdict that is not `clean` (FR-12).
    """
    root = value_tree(tmp_path, values=["inherit", "flash", "pro"])

    result = convert_set(
        a_subagent(tmp_path / "roles", "model: haiku\n"),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )
    row = next(
        entry
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if "haiku" in entry["found_as"]
    )

    assert result.report["translations"] == []
    assert (row["id"], row["outcome"], row["verdict"]) == (
        "subagent.frontmatter.model",
        "unknown",
        "lossy",
    )
    assert row["note"] == convert_module.NO_COUNTERPART
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


def test_a_field_the_target_names_no_value_set_for_is_left_alone_and_says_why(
    tmp_path: Path,
) -> None:
    """No set, no translation: silence about the set is not permission to translate.

    The rules do carry a counterpart for this very value, and it is still not applied --
    which is the whole of the boundary. Without a documented set there is nothing that makes
    the written value wrong, so a rewrite would be a rule of ours passed off as a fact about
    the target environment (FR-11.2).
    """
    root = value_tree(tmp_path, values=None)

    result = convert_set(
        a_subagent(tmp_path / "roles", "model: sonnet\n"),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )
    row = next(
        entry
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if "sonnet" in entry["found_as"]
    )

    assert result.report["translations"] == []
    assert (row["outcome"], row["verdict"]) == ("unknown", "lossy")
    assert row["note"] == convert_module.NO_VALUE_SET


def test_a_value_that_is_not_text_is_refused_with_the_file_and_the_field_named(
    tmp_path: Path,
) -> None:
    """A number where a tier was expected is a refusal a person can act on (FR-11.1).

    Both halves of the address are asserted: a message naming only the field sends a person
    grepping a set for it, and one naming only the file leaves them reading a header.
    """
    root = value_tree(tmp_path, values=["inherit", "flash", "pro"])

    result = convert_set(
        a_subagent(tmp_path / "roles", "model: 3\n"),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )

    assert result.exit_code == 6
    assert str(tmp_path / "roles" / "note-keeper.md") in result.report["error"]
    assert "`model`" in result.report["error"]


def test_the_assembled_skill_file_carries_the_translated_value_and_not_the_written_one(
    tmp_path: Path,
) -> None:
    """The bytes that leave, not the report about them: the file says what the run claims.

    A report that prints `translated to pro` over a file still saying `sonnet` states a fact
    about the caller's data that is not true, and calls the transfer clean while the value
    the target refuses is exactly what was written. Asserted on the staged file, because the
    five cases above all watch the report and none of them watches what the caller gets.

    Everything the run did not translate is asserted untouched in the same breath: a header
    re-dumped wholesale would pass an assertion about `pro` while quietly rewriting the rest
    of somebody's file, which is the same defect with the blame moved.
    """
    root = translating_tree(tmp_path)
    folder = skill(tmp_path / "alpha", "name: alpha\nmodel: sonnet\nlicence: sonnet-2.0\n")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=SKILL_TRANSLATING, skill=(folder,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    staged = (out / ".agents/skills/alpha-antigravity/SKILL.md").read_text(encoding="utf-8")

    assert "model: pro\n" in staged
    assert "model: sonnet" not in staged
    # The value of another key, and the body, are none of the translation's business: only
    # what a rule was applied to may differ from the file the run was given.
    assert "licence: sonnet-2.0\n" in staged
    assert staged.endswith("\nBody.\n")
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_a_counterpart_the_targets_own_set_does_not_carry_is_a_row_and_not_a_rewrite(
    tmp_path: Path,
) -> None:
    """The rules do not outrank the description: a pair the target refuses is not applied.

    The two files are versioned apart and either may be the stale one, so a counterpart the
    target's own set does not contain is a disagreement this run cannot settle -- and writing
    the value anyway would let a rules file quietly overrule the documentation it was written
    against, which is the one thing Decisions 1 exists to prevent.
    """
    root = value_tree(tmp_path, values=["inherit", "flash"])

    result = convert_set(
        a_subagent(tmp_path / "roles", "model: sonnet\n"),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )
    row = next(
        entry
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if "sonnet" in entry["found_as"]
    )

    assert result.report["translations"] == []
    assert (row["outcome"], row["verdict"]) == ("unknown", "lossy")
    assert row["note"] == convert_module.REFUSED_BY_THE_TARGET


def test_a_tool_name_without_a_documented_pair_stays_as_it_is_and_is_named(
    tmp_path: Path,
) -> None:
    """The names the rules pair are translated; the rest cross unchanged, each with a row.

    Dropping an unpaired name would quietly narrow what the subagent may do, and pairing it
    by how it sounds would hand the target a tool it never documented. Both are silent, and
    the report is what this command has instead of silence (FR-17, FR-18).
    """
    root = value_tree(tmp_path, values=["inherit", "flash", "pro"])

    result = convert_set(
        a_subagent(tmp_path / "roles", "tools: Read, Write, Grep, SendMessage\n"),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )
    unpaired = {
        entry["found_as"]: entry
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if entry["note"] == convert_module.NO_TOOL_COUNTERPART
    }

    assert [(entry["from"], entry["to"]) for entry in result.report["translations"]] == [
        ("Read", "view_file"),
        ("Grep", "grep_search"),
    ]
    assert set(unpaired) == {"tool name `Write`", "tool name `SendMessage`"}
    assert unpaired["tool name `Write`"]["id"] == "subagent.frontmatter.tools"
    assert result.report["advice"] == list(convert_module._HOW_TO_KEEP_A_TOOL_NAME)
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


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
    assert json.loads(piped.stdout)["report_schema"] == 2
    assert str(folder) in piped.stderr
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


MOVING = Rules.model_validate(
    {
        "rules_version": "2.0",
        "value_maps": {
            "subagent.frontmatter.model": {"opus": "pro", "sonnet": "pro"},
            "subagent.frontmatter.tools": {"Read": "view_file", "Grep": "grep_search"},
            # The shape the value is written in, which is a value like any other here: the
            # left-hand side is how the source wrote it, the right-hand side the form the
            # target documents.
            "subagent.frontmatter.tools.form": {"comma-separated string": "list"},
            # The empty left-hand side is the value a file that declares none has: the rule
            # says what a rule file without a trigger gets, in the same shape as every other
            # pair -- what was written, and what it becomes.
            "rules.frontmatter.trigger": {"": "always_on"},
        },
        "rewrite": {"include": ["*.md"], "exclude": ["CHANGELOG.md"]},
        "undocumented": {"action": "copy", "note": "nothing declares this file"},
    }
)
"""Rules for a set of several kinds: a model tier to translate and a header to add."""


def destinations_tree(tmp_path: Path, agents_root: str = ".agents/agents/") -> Path:
    """Descriptions whose target names a place for every kind of this set except a command.

    ``agents_root`` is the one layout path a caller here may choose, because where a root is
    measured from is what a run that installs is held to: a test about a path leading out of
    every root needs a description that names one.
    """
    root = tmp_path / "specs"
    fields: list[dict[str, Any]] = [
        {"kind": "subagent-field", "id": entry, "support": "supported"} for entry in SUBAGENT_FIELDS
    ]
    write(root, vendor="anthropic", environment="claude-code", capabilities=fields)
    target: list[dict[str, Any]] = [dict(entry) for entry in fields]
    target[SUBAGENT_FIELDS.index("subagent.frontmatter.model")]["values"] = [
        "inherit",
        "flash",
        "pro",
    ]
    target.append(
        {
            "kind": "settings-file",
            "id": "rules.frontmatter.trigger",
            "support": "supported",
            "values": ["always_on", "model_decision"],
        }
    )
    target.append(
        {
            "kind": "subagent-field",
            "id": "subagent.frontmatter.tools.form",
            "support": "supported",
            "values": ["list"],
        }
    )
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=target,
        layout=[
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "skill.top.CHANGELOG.md", "path": "<skill-name>/CHANGELOG.md"},
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
            {"id": "agents.project", "path": agents_root},
            {"id": "agents.user", "path": "~/.gemini/config/agents/"},
            {"id": "rules.project", "path": ".agents/rules/"},
        ],
    )
    return root


def subagents(folder: Path, frontmatter: str = "model: sonnet\n") -> Path:
    """A folder of subagents named nothing like the target's own, holding one subagent."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "note-keeper.md").write_text(
        f"---\nname: note-keeper\ndescription: keeps notes\n{frontmatter}---\n\nYou keep notes.\n",
        encoding="utf-8",
    )
    return folder


def test_a_subagent_is_assembled_where_the_target_names_agents_with_the_value_translated(
    tmp_path: Path,
) -> None:
    """The whole point of the track: the file lands where the environment reads it, and reads.

    A subagent copied to the right folder carrying `model: sonnet` is as invisible as one
    never copied -- the target's own closed set has no such tier -- so the destination and
    the translated header are one acceptance and not two. Both are read off the target
    description written above, never recomputed the way the code computes them.
    """
    root = destinations_tree(tmp_path)
    folder = subagents(tmp_path / "set" / "roles")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(folder,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    staged = (out / ".agents/agents/note-keeper.md").read_text(encoding="utf-8")

    assert [(entry["from"], entry["to"]) for entry in result.report["written"]] == [
        ("note-keeper.md", ".agents/agents/note-keeper.md")
    ]
    assert "model: pro\n" in staged
    assert "model: sonnet" not in staged
    assert staged.endswith("\nYou keep notes.\n")
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_the_form_of_a_value_is_translated_like_the_value_itself(tmp_path: Path) -> None:
    """The names inside the field are half of it; the shape the field is written in is the other.

    A subagent whose `tools` is one comma-separated string reaches the target and is never
    read, so the shape the target documents is a property of its description -- the closed
    set of `subagent.frontmatter.tools.form` -- and turning one shape into the other is a
    translation rule, shown in the report as every applied rule is.
    """
    root = destinations_tree(tmp_path)
    folder = subagents(tmp_path / "set" / "roles", "tools: Read, Grep\n")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(folder,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    staged = (out / ".agents/agents/note-keeper.md").read_text(encoding="utf-8")

    assert ("subagent.frontmatter.tools.form", "comma-separated string", "list") in [
        (entry["id"], entry["from"], entry["to"]) for entry in result.report["translations"]
    ]
    assert yaml.safe_load(staged.split("---")[1])["tools"] == ["view_file", "grep_search"]
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_the_level_the_caller_asked_for_decides_which_agents_root_is_used(tmp_path: Path) -> None:
    """`--scope user` is the other entry of the same pair, and the bytes still stay under out."""
    root = destinations_tree(tmp_path)
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(subagents(tmp_path / "set" / "roles"),)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        scope=Scope.USER,
        allow_stale=True,
    )
    written = result.report["written"][0]

    assert written["to"] == f"{Path.home()}/.gemini/config/agents/note-keeper.md"
    assert written["path"] == str(out / ".gemini/config/agents/note-keeper.md")


def test_a_rules_file_moves_to_the_rules_root_and_carries_the_header_that_loads_it(
    tmp_path: Path,
) -> None:
    """`.agents/rules/` and `trigger: always_on`: without either, the rule is on disk and idle.

    The value is the target's own, from the closed set its description names; that the
    header is added at all is the translation rules' decision, and the report shows it as
    the applied rule it is.
    """
    root = destinations_tree(tmp_path)
    rule = tmp_path / "set" / "policy" / "tone.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("Be brief.\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, rules=(rule,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    assert [entry["to"] for entry in result.report["written"]] == [".agents/rules/tone.md"]
    assert (out / ".agents/rules/tone.md").read_text(encoding="utf-8") == (
        "---\ntrigger: always_on\n---\n\nBe brief.\n"
    )
    assert [(entry["id"], entry["to"]) for entry in result.report["translations"]] == [
        ("rules.frontmatter.trigger", "always_on")
    ]


@pytest.mark.parametrize(
    ("header", "expected", "applied"),
    [
        ("---\nscope: repo\n---\n\n", "---\ntrigger: always_on\nscope: repo\n---\n\n", 1),
        ("---\ntrigger: model_decision\n---\n\n", "---\ntrigger: model_decision\n---\n\n", 0),
    ],
    ids=["a header without the key", "a header that already sets it"],
)
def test_a_rules_file_that_has_a_header_keeps_it_and_only_gains_what_is_missing(
    tmp_path: Path, header: str, expected: str, applied: int
) -> None:
    """Somebody else's header is not redecided: the key is added, or nothing happens at all."""
    root = destinations_tree(tmp_path)
    rule = tmp_path / "set" / "policy" / "tone.md"
    rule.parent.mkdir(parents=True)
    rule.write_text(f"{header}Be brief.\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, rules=(rule,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    assert (out / ".agents/rules/tone.md").read_text(encoding="utf-8") == f"{expected}Be brief.\n"
    assert len(result.report["translations"]) == applied


def test_two_rule_files_of_one_name_from_different_folders_collide_rather_than_overwrite(
    tmp_path: Path,
) -> None:
    """The second would land on the first, and a report calling both carried over is a lie."""
    root = destinations_tree(tmp_path)
    named = []
    for folder in ("house", "team"):
        rule = tmp_path / "set" / folder / "tone.md"
        rule.parent.mkdir(parents=True)
        rule.write_text("Be brief.\n", encoding="utf-8")
        named.append(rule)
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, rules=tuple(named)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    assert result.exit_code == 8
    assert result.report["written"] == []
    assert not (out / ".agents/rules/tone.md").exists()


@pytest.mark.parametrize("names", [("note.md", "recap.md"), ()], ids=["two commands", "none"])
def test_every_command_earns_one_refusal_and_no_command_is_ever_written(
    tmp_path: Path, names: tuple[str, ...]
) -> None:
    """A row each, naming what it is, why it stays and what to do instead -- and never a file.

    Counted against the commands on the input and not against a number somebody observed
    once: an empty folder of commands earns no refusals at all, and that is the same rule.
    """
    root = destinations_tree(tmp_path)
    commands = tmp_path / "set" / "shortcuts"
    commands.mkdir(parents=True)
    for name in names:
        (commands / name).write_text("Do the thing.\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, commands=(commands,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    refused = [
        entry
        for asset in result.report["assets"]
        for entry in asset["properties"]
        if entry["id"] == "command.file"
    ]

    assert len(refused) == len(names)
    assert {entry["found_as"] for entry in refused} == {f"command file `{name}`" for name in names}
    assert all(entry["note"] == convert_module.NO_ROOM_FOR[Kind.COMMAND] for entry in refused)
    assert result.report["written"] == []


@pytest.mark.parametrize("action", ["copy", "skip"])
def test_the_rule_for_an_undocumented_file_is_carried_out_and_not_only_printed(
    tmp_path: Path, action: str
) -> None:
    """`action` decides what happens to a file nobody declared; the row says so either way.

    The row has been there since the set report; until now the action beside it decided
    nothing, so a rules file saying `skip` still carried the file across.
    """
    root = destinations_tree(tmp_path)
    folder = subagents(tmp_path / "set" / "roles")
    (folder / "openai.yaml").write_text("model: gpt\n", encoding="utf-8")
    out = tmp_path / "out"
    translation = MOVING.model_copy(
        update={"undocumented": MOVING.undocumented.model_copy(update={"action": action})}
    )

    result = convert_set(
        Inputs(translation=translation, agents=(folder,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    carried = str(out / "roles/openai.yaml") in {
        entry["path"] for entry in result.report["written"]
    }

    assert carried is (action == "copy")
    assert (out / "roles/openai.yaml").exists() is (action == "copy")
    # Never in the root the target reads as a folder of subagents, whichever way the rule
    # went: what is carried is the file, not a claim that the environment will take it.
    assert not (out / ".agents/agents/openai.yaml").exists()
    # The row is there whichever way the rule went: a file dropped in silence is the one
    # thing this command exists to prevent, and copying it is not a reason to stop saying so.
    assert any(
        entry["found_as"] == "openai.yaml"
        for asset in result.report["assets"]
        for entry in asset["properties"]
    )


def test_a_rule_file_that_is_not_utf_8_is_refused_with_its_path_and_still_reports(
    tmp_path: Path,
) -> None:
    """Somebody else's bytes are not this command's to crash on: a refusal, never a traceback.

    Every other file of a set already answers this way, and a caller who gets a stack trace
    instead of a report has no exit code to act on and no path to go and look at.
    """
    root = destinations_tree(tmp_path)
    rule = tmp_path / "set" / "policy" / "tone.md"
    rule.parent.mkdir(parents=True)
    rule.write_bytes(b"Soyez bref\xe9\n")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, rules=(rule,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    assert result.exit_code == 6
    assert str(rule) in result.report["error"]
    assert result.report["written"] == []
    assert not out.exists()


def test_an_undocumented_path_is_never_staged_in_a_root_the_target_scans_for_entities(
    tmp_path: Path,
) -> None:
    """`action: copy` keeps the file; it does not hand the environment a broken entity.

    A folder with no skill file inside the target's own skills root is a skill the
    environment will try to read and fail to, which is worse than the silence this whole
    command exists to break -- and it contradicts the very row that tells the caller to
    place the file by hand. It is staged under `out` instead, beside the part it came from.
    """
    root = destinations_tree(tmp_path)
    skills = tmp_path / "set" / "bundles"
    skill(skills / "alpha", "name: alpha\n")
    (skills / "_templates").mkdir()
    (skills / "_templates" / "note.md").write_text("A template.\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, skills=(skills,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    assert not (out / ".agents/skills/_templates").exists()
    assert (out / "bundles/_templates/note.md").read_text(encoding="utf-8") == "A template.\n"
    assert (out / ".agents/skills/alpha-antigravity/SKILL.md").is_file()
    assert str(out / "bundles/_templates") in {entry["path"] for entry in result.report["written"]}


def linking_subagents(folder: Path, addresses: str) -> Path:
    """A subagent whose body addresses another file of the set by a relative path."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "note-keeper.md").write_text(
        "---\nname: note-keeper\ndescription: keeps notes\nmodel: sonnet\n---\n\n"
        f"Follow `{addresses}` when writing.\n",
        encoding="utf-8",
    )
    return folder


def test_an_address_of_a_moved_file_points_at_where_this_run_put_it(tmp_path: Path) -> None:
    """The point of the whole rule: the two files move apart, and the address moves with them.

    A subagent goes to the agents root and the rule file it names goes to the rules root, so
    the path that reached one from the other in the source set reaches nothing in the target.
    Left alone it is a role sending itself to a mode that is not there. The new address is
    worked out from where the two parts landed, and both of those are read off the target
    description.
    """
    root = destinations_tree(tmp_path)
    rule = tmp_path / "set" / "policy" / "tone.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("Be brief.\n", encoding="utf-8")
    roles = linking_subagents(tmp_path / "set" / "roles", "../policy/tone.md")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(roles,), rules=(rule,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    staged = (out / ".agents/agents/note-keeper.md").read_text(encoding="utf-8")

    assert "`../rules/tone.md`" in staged
    assert "../policy/tone.md" not in staged
    assert (out / ".agents/agents" / "../rules/tone.md").resolve().is_file()
    assert [(entry["from"], entry["to"]) for entry in result.report["links"]] == [
        ("../policy/tone.md", "../rules/tone.md")
    ]


def test_an_address_of_a_file_that_stayed_where_it_was_is_left_exactly_as_written(
    tmp_path: Path,
) -> None:
    """Only what moved is repointed. A command is assembled nowhere, so its path still holds.

    Rewriting it would aim the subagent at a place under `--out` where nothing was ever
    written, turning an address that still works into one that does not -- and the run would
    report the damage as work done.
    """
    root = destinations_tree(tmp_path)
    shortcuts = tmp_path / "set" / "shortcuts"
    shortcuts.mkdir(parents=True)
    (shortcuts / "note.md").write_text("Take a note.\n", encoding="utf-8")
    roles = linking_subagents(tmp_path / "set" / "roles", "../shortcuts/note.md")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(roles,), commands=(shortcuts,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    staged = (out / ".agents/agents/note-keeper.md").read_text(encoding="utf-8")

    assert "`../shortcuts/note.md`" in staged
    assert result.report["links"] == []
    assert not [line for line in result.report["advice"] if "../shortcuts/note.md" in line]


def test_an_address_leading_out_of_the_set_is_left_alone_and_named_in_the_report(
    tmp_path: Path,
) -> None:
    """Nobody here can work out what it should become, and silence would hide that from the caller.

    The composition names what this run was given; a path under none of it points at a file
    this run never saw, never moved and can say nothing about beyond that it is still written
    the way it was.
    """
    root = destinations_tree(tmp_path)
    roles = linking_subagents(tmp_path / "set" / "roles", "../../house/style.md")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(roles,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    staged = (out / ".agents/agents/note-keeper.md").read_text(encoding="utf-8")

    assert "`../../house/style.md`" in staged
    assert result.report["links"] == []
    assert [line for line in result.report["advice"] if "../../house/style.md" in line]


def test_the_change_history_is_carried_over_byte_for_byte(tmp_path: Path) -> None:
    """The one file the rules keep out of substitution, and the one test that it stays out.

    A change history is a record of what was written. An address inside it is part of that
    record, and a run that repointed it would leave a record of what we wish had been
    written -- so the file arrives with the address still leading where it led, which is
    exactly the state the exclusion promises.
    """
    root = destinations_tree(tmp_path)
    folder = skill(tmp_path / "set" / "bundles" / "note-taker", "name: note-taker\n")
    history = "# History\n\n- Moved the rules to `../../policy/tone.md`.\n"
    (folder / "CHANGELOG.md").write_text(history, encoding="utf-8")
    rule = tmp_path / "set" / "policy" / "tone.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("Be brief.\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, skill=(folder,), rules=(rule,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    carried = out / ".agents/skills/note-taker-antigravity/CHANGELOG.md"
    assert carried.read_bytes() == history.encode("utf-8")
    assert result.report["links"] == []


def test_a_link_definition_of_a_moved_file_is_named_even_though_it_is_not_repointed(
    tmp_path: Path,
) -> None:
    """Not rewriting it is a ceiling; not saying so would be the silence this command is against.

    A definition stands in one place and is used from another, and the substitution here only
    ever edits an address where it stands -- so a file that moved keeps a definition pointing
    at where it used to be. That is a broken file, and a broken file the caller is told about
    is a different thing from a broken file nobody mentions. The row names both the address
    as written and the place to point it at.
    """
    root = destinations_tree(tmp_path)
    rule = tmp_path / "set" / "policy" / "tone.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("Be brief.\n", encoding="utf-8")
    roles = tmp_path / "set" / "roles"
    roles.mkdir(parents=True)
    (roles / "note-keeper.md").write_text(
        "---\nname: note-keeper\ndescription: keeps notes\nmodel: sonnet\n---\n\n"
        "Follow [tone][t] when writing.\n\n[t]: ../policy/tone.md\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(roles,), rules=(rule,)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    staged = (out / ".agents/agents/note-keeper.md").read_text(encoding="utf-8")

    assert "[t]: ../policy/tone.md\n" in staged
    assert result.report["links"] == []
    assert [
        line
        for line in result.report["advice"]
        if "../policy/tone.md" in line and "../rules/tone.md" in line
    ]


def translation_file(tmp_path: Path, translation: Rules) -> Path:
    """The translation rules on disk, where `--translation` can name them."""
    path = tmp_path / "translation.yaml"
    path.write_text(
        yaml.safe_dump(translation.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    return path


def a_set_on_disk(tmp_path: Path) -> dict[str, Path]:
    """A set laid out under names of its owner's own choosing, one part of every kind."""
    home = tmp_path / "set"
    skill(home / "bundles" / "note-taker", "name: note-taker\n")
    subagents(home / "roles")
    (home / "shortcuts").mkdir(parents=True)
    (home / "shortcuts" / "note.md").write_text("Take a note.\n", encoding="utf-8")
    (home / "policy").mkdir(parents=True)
    (home / "policy" / "tone.md").write_text("Be brief.\n", encoding="utf-8")
    return {name: home / name for name in ("bundles", "roles", "shortcuts", "policy")}


def test_the_composition_of_a_set_is_given_on_the_command_line(tmp_path: Path) -> None:
    """Every part of a set reaches the run through an option, from folders named anything.

    The modular half of the command has taken a composition since the reading of a set was
    written, and until there are options for it a person can still only ever name one skill
    folder. The names below are the owner's, not the target's and not this repository's:
    that a set laid out differently converts by the same rules is the whole reason the
    composition is data rather than a walk of a fixed tree.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "convert",
            "--skills",
            str(parts["bundles"]),
            "--agents",
            str(parts["roles"]),
            "--commands",
            str(parts["shortcuts"]),
            "--rules",
            str(parts["policy"] / "tone.md"),
            "--translation",
            str(translation_file(tmp_path, MOVING)),
            "--source",
            SOURCE,
            "--target",
            TARGET,
            "--specs",
            str(root),
            "--allow-stale",
            "--out",
            str(out),
        ],
    )
    report = json.loads(result.stdout)

    assert [entry["kind"] for entry in report["assets"]] == [
        "skill",
        "subagent",
        "command",
        "rules-file",
    ]
    assert report["rules_version"] == "2.0"
    # The other half of the same acceptance: a run that assembled says how to install what
    # it assembled, or the folder it made is as far as anybody gets.
    assert convert_module.INSTALL_WITH in report["advice"]
    assert (out / ".agents/skills/note-taker-antigravity/SKILL.md").exists()
    assert (out / ".agents/agents/note-keeper.md").exists()
    assert (out / ".agents/rules/tone.md").exists()


def test_install_writes_into_the_roots_the_target_description_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gap this whole track is about: on disk somewhere, and read by the environment.

    Both spellings a layout path can open with are exercised at once -- the skills root of
    this description says `<workspace-root>/` and its agents root says neither, which is the
    same root by a different spelling. Neither is written here or anywhere else in the
    module: the placeholder and the bare path are expanded where every other destination is.
    The workspace is a folder of this test's own, so what a live root means is decided by
    where the command runs and not by whose machine it runs on.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    result = convert_set(
        Inputs(
            translation=MOVING,
            skills=(parts["bundles"],),
            agents=(parts["roles"],),
            rules=(parts["policy"] / "tone.md",),
        ),
        SOURCE,
        TARGET,
        root=root,
        install=True,
        allow_stale=True,
    )
    announced = capsys.readouterr().err

    assert (workspace / ".agents/skills/note-taker-antigravity/SKILL.md").exists()
    assert "model: pro" in (workspace / ".agents/agents/note-keeper.md").read_text(encoding="utf-8")
    assert "trigger: always_on" in (workspace / ".agents/rules/tone.md").read_text(encoding="utf-8")
    assert str(workspace / ".agents/agents/note-keeper.md") in announced
    assert str(workspace / ".agents/rules/tone.md") in {
        entry["path"] for entry in result.report["written"]
    }


def test_a_second_install_names_what_is_already_there_and_replaces_none_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run twice over a live root, and the second run shows the places and touches nothing.

    This is also where the order is proved: the second run writes nothing at all, and the
    plan is on the error stream anyway. A plan printed after the writing would be a receipt,
    and a receipt is no help to somebody deciding whether to let a command near their own
    folders.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    inputs = Inputs(translation=MOVING, agents=(parts["roles"],))
    convert_set(inputs, SOURCE, TARGET, root=root, install=True, allow_stale=True)
    placed = workspace / ".agents/agents/note-keeper.md"
    first = placed.read_bytes()
    capsys.readouterr()
    subagents(parts["roles"], frontmatter="model: opus\ncolor: red\n")

    result = convert_set(inputs, SOURCE, TARGET, root=root, install=True, allow_stale=True)
    announced = capsys.readouterr().err

    assert result.exit_code == 8
    assert placed.read_bytes() == first
    assert f"{placed} <- " in announced
    assert "ALREADY THERE" in announced
    assert str(placed) in result.report["error"]


def test_install_and_out_together_are_refused_because_a_run_has_one_destination(
    tmp_path: Path,
) -> None:
    """Two destinations is not a question with an answer, and guessing one is the worse half.

    Refused before anything is read, and refused with a report like every other outcome: a
    caller that reads the report to find out what happened gets the reason there, not only
    on the stream a person reads.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, agents=(parts["roles"],)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        install=True,
        allow_stale=True,
    )

    assert result.exit_code == 7
    assert "--install" in result.report["error"] and "--out" in result.report["error"]
    assert not out.exists()


def test_translation_rules_that_do_not_read_end_in_a_report_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    """The file is an argument, and an argument to correct is not a stack trace.

    Left to itself this exits 1 -- the code for a transfer that lost something -- and says
    nothing a caller can parse, about a run that never judged anything at all.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    broken = tmp_path / "broken.yaml"
    broken.write_text("rules_version: 1.0\nundocumented: {}\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "convert",
            "--agents",
            str(parts["roles"]),
            "--translation",
            str(broken),
            "--source",
            SOURCE,
            "--target",
            TARGET,
            "--specs",
            str(root),
            "--allow-stale",
        ],
    )
    issued = json.loads(result.stdout)

    assert result.exit_code == 6
    assert issued["exit_code"] == 6
    assert str(broken) in issued["error"]
    assert "Traceback" not in result.stderr


def test_a_rule_file_the_target_names_a_root_for_does_not_cost_the_run_its_verdict(
    tmp_path: Path,
) -> None:
    """R19 and G02 are the transfer working, and a working transfer is not a loss.

    A rule file has no format of its own to ask a description about: what decides whether it
    crosses is whether the target names a root for rule files, and this description does --
    the same entry the assembly puts the file at. Asked under an id no description carries,
    the run copied the file exactly where the target says and called the transfer lossy,
    which is the row and the place saying different things.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    out = tmp_path / "out"

    result = convert_set(
        Inputs(translation=MOVING, rules=(parts["policy"] / "tone.md",)),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)
    assert rows(result.report)["rules.project"]["target_says"] == ".agents/rules/"
    assert (out / ".agents/rules/tone.md").exists()


def test_install_refuses_a_destination_that_leads_out_of_the_home_and_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one promise this command makes about a caller's filesystem, on the run that can break it.

    A layout path is measured from the home folder or from the workspace, and those two are
    the roots an installing run may write under. A path measured from neither -- a target
    description naming an absolute one, here or after a vendor edits their own -- is the
    same refusal `--out` answers with, and this is the only place in the project where the
    command writes into folders that are really somebody's.
    """
    escape = tmp_path / "escape"
    root = destinations_tree(tmp_path, agents_root=f"{escape}/")
    parts = a_set_on_disk(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    result = convert_set(
        Inputs(translation=MOVING, agents=(parts["roles"],)),
        SOURCE,
        TARGET,
        root=root,
        install=True,
        allow_stale=True,
    )

    assert not escape.exists()
    assert result.exit_code == 7


def test_install_at_the_user_level_writes_under_the_home_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The branch with the widest blast radius of anything here, and it had no test at all.

    The home folder is this test's own, so nothing of the machine it runs on is touched --
    which is also the only way to have the branch run at all.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    convert_set(
        Inputs(translation=MOVING, agents=(parts["roles"],)),
        SOURCE,
        TARGET,
        root=root,
        install=True,
        scope=Scope.USER,
        allow_stale=True,
    )

    assert (home / ".gemini/config/agents/note-keeper.md").exists()


def test_install_follows_a_link_the_caller_made_above_the_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody keeps their configuration in a repository of its own and links the root at it.

    The tree an installing run writes into is already theirs, and a link they made in it is
    their own statement about where their configuration lives -- so the run follows it and
    the files land where it points. What the refusal used to be was a lie as well as a stop:
    it measured the root as written and the destination through the link, and then called a
    path inside the home folder a path leading out of it.
    """
    root = destinations_tree(tmp_path)
    parts = a_set_on_disk(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    elsewhere = tmp_path / "configs"
    elsewhere.mkdir()
    (home / ".gemini").symlink_to(elsewhere)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    result = convert_set(
        Inputs(translation=MOVING, agents=(parts["roles"],)),
        SOURCE,
        TARGET,
        root=root,
        install=True,
        scope=Scope.USER,
        allow_stale=True,
    )

    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)
    assert (elsewhere / "config/agents/note-keeper.md").exists()


def manifest_tree(tmp_path: Path) -> Path:
    """Descriptions where the target documents a plugin manifest and one field of one.

    One field declared and the rest not: a manifest is judged field by field against the
    descriptions, so a run that read a list of fields out of this command instead would
    answer the same for both of them.
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
                "id": "settings.file.plugin-manifest",
                "kind": "settings-file",
                "support": "supported",
            },
            {
                "id": "settings.file.plugin-manifest.name",
                "kind": "settings-file",
                "support": "supported",
            },
        ],
        layout=[
            {"id": "skills.project", "path": "<workspace-root>/.agents/skills/"},
            {"id": "skill.file", "path": "<skill-name>/SKILL.md"},
            {"id": "plugins.project", "path": "<workspace-root>/.agents/plugins/"},
            {"id": "plugin.file", "path": "<plugin-name>/plugin.json"},
            {"id": "plugin.dir.skills", "path": "<plugin-name>/skills/"},
            {"id": "plugin.file.hooks", "path": "<plugin-name>/hooks.json"},
            {"id": "plugin.file.mcp-config", "path": "<plugin-name>/mcp_config.json"},
        ],
    )
    return root


def a_manifest(tmp_path: Path, text: str, *, skills: bool = False) -> Inputs:
    """A composition naming a manifest, in a folder of its own -- which names the plugin."""
    folder = tmp_path / "note-kit"
    folder.mkdir(parents=True, exist_ok=True)
    plugin = folder / "plugin.json"
    plugin.write_text(text, encoding="utf-8")
    if not skills:
        return Inputs(translation=TRANSLATION, plugin=plugin)
    skill(folder / "skills" / "taker", "name: taker\n")
    return Inputs(translation=TRANSLATION, plugin=plugin, skills=(folder / "skills",))


def test_every_field_of_a_manifest_is_a_row_and_the_descriptions_decide_which(
    tmp_path: Path,
) -> None:
    """A manifest is read as data, and each of its fields is asked about under its own id.

    `version` is a field of the set's own manifest that the target's format has no place
    for, and the row saying so is the whole of FR-32 that is not silence. It is `unknown`
    rather than `missing` because the target never said it rejects one -- and it is a row
    at all only because the fields are asked of the descriptions one by one instead of
    being matched against a list of names written down in this command.
    """
    root = manifest_tree(tmp_path)

    result = convert_set(
        a_manifest(tmp_path, json.dumps({"name": "kit", "version": "1.4.0"})),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )
    found = properties(result.report)

    assert found["settings.file.plugin-manifest.name"] == ("reproduced", "extension", "clean")
    assert found["settings.file.plugin-manifest.version"] == ("unknown", "extension", "lossy")
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


def test_the_manifest_crosses_carrying_only_the_fields_the_target_documents(
    tmp_path: Path,
) -> None:
    """The rewrite, and the one thing it must never do: invent a field or carry one blindly.

    The target's own manifest format carries `name` and nothing else this manifest holds,
    so `name` crosses and `version` does not -- and `version` is not dropped in silence, it
    is the `unknown` row above. Which fields cross is read off those rows, so the format is
    the description's to state and never a list of names kept in the command.
    """
    root = manifest_tree(tmp_path)
    out = tmp_path / "out"

    result = convert_set(
        a_manifest(tmp_path, json.dumps({"name": "kit", "version": "1.4.0"})),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    written = out / ".agents/plugins/note-kit/plugin.json"

    assert json.loads(written.read_text(encoding="utf-8")) == {"name": "kit"}
    assert {
        "from": "plugin.json",
        "to": ".agents/plugins/note-kit/plugin.json",
        "path": str(written),
    } in result.report["written"]


def test_a_set_that_names_a_manifest_is_laid_out_inside_the_plugin_folder(
    tmp_path: Path,
) -> None:
    """The environment finds a plugin's skills by its folder, so the skills go in it.

    Without this the run would write a plugin folder holding a manifest and nothing else,
    and the skills beside it in the root of their own kind -- an empty plugin, and the
    parts of it loaded twice over or not as part of it at all.
    """
    root = manifest_tree(tmp_path)
    out = tmp_path / "out"

    result = convert_set(
        a_manifest(tmp_path, json.dumps({"name": "kit"}), skills=True),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )

    assert (out / ".agents/plugins/note-kit/skills/taker-antigravity/SKILL.md").exists()
    assert not (out / ".agents/skills").exists()
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_a_manifest_that_is_not_data_is_refused_with_the_file_named(tmp_path: Path) -> None:
    """Somebody else's file, parsed here: a broken one is a refusal and never a traceback.

    Named by the path, because a manifest that will not parse is the caller's file to go
    and look at, and a stack trace names this module instead.
    """
    root = manifest_tree(tmp_path)
    inputs = a_manifest(tmp_path, "name = kit\n")

    result = convert_set(inputs, SOURCE, TARGET, root=root, allow_stale=True)

    assert result.exit_code == 6
    assert str(inputs.plugin) in (result.report["error"] or "")


def test_a_field_the_transfer_leaves_out_is_not_written_into_the_manifest(
    tmp_path: Path,
) -> None:
    """`out-of-scope` is clean, and clean is not the same as carried.

    A field the *source* does not support is out of the transfer's scope: it cost nothing
    precisely because nothing crosses. The target documenting a field of that name does not
    put it back -- read off the verdict rather than the outcome, this run would write the
    field into the manifest while its own row says it was left out of the comparison.
    """
    root = tmp_path / "specs"
    write(
        root,
        vendor="anthropic",
        environment="claude-code",
        capabilities=[
            {
                "id": "settings.file.plugin-manifest.legacy",
                "kind": "settings-file",
                "support": "unsupported",
            }
        ],
    )
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {
                "id": "settings.file.plugin-manifest.name",
                "kind": "settings-file",
                "support": "supported",
            },
            {
                "id": "settings.file.plugin-manifest.legacy",
                "kind": "settings-file",
                "support": "supported",
            },
        ],
        layout=[
            {"id": "plugins.project", "path": "<workspace-root>/.agents/plugins/"},
            {"id": "plugin.file", "path": "<plugin-name>/plugin.json"},
        ],
    )
    out = tmp_path / "out"

    result = convert_set(
        a_manifest(tmp_path, json.dumps({"name": "kit", "legacy": True})),
        SOURCE,
        TARGET,
        root=root,
        out=out,
        allow_stale=True,
    )
    written = out / ".agents/plugins/note-kit/plugin.json"

    assert properties(result.report)["settings.file.plugin-manifest.legacy"] == (
        "out-of-scope",
        "extension",
        "clean",
    )
    assert json.loads(written.read_text(encoding="utf-8")) == {"name": "kit"}


def test_the_plugin_folder_is_named_the_same_however_the_manifest_path_is_spelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam takes the path a caller passes, and a relative one names the same folder.

    `Path("plugin.json").parent` is `.` and its name is the empty string, which would put
    the plugin folder one level up -- every part of the set outside the plugin the run says
    it wrote. The command line expands its arguments and so never sees this; the seam is
    public, and a caller of it passes what they have.
    """
    root = manifest_tree(tmp_path)
    inputs = a_manifest(tmp_path, json.dumps({"name": "kit"}))
    monkeypatch.chdir(tmp_path / "note-kit")
    out = tmp_path / "out"

    result = convert_set(
        replace(inputs, plugin=Path("plugin.json")), SOURCE, TARGET, root=root, out=out
    )

    assert (out / ".agents/plugins/note-kit/plugin.json").exists()
    assert result.exit_code == 0


def test_a_plugins_own_files_beside_the_manifest_cross_into_the_plugin_folder(
    tmp_path: Path,
) -> None:
    """The hooks and the MCP servers of a plugin are part of it, and part of what crosses.

    The target reads both from the plugin folder and the manifest lists neither (D02), so
    the only thing that carries them is the folder this run is already writing. Left out,
    the set arrives as a plugin whose hooks do not fire, and the owner finds that out from
    the behaviour -- the silence this command exists to break. Copied whole and not merged:
    unlike a skill's hook entry, these are files of this plugin alone.
    """
    root = manifest_tree(tmp_path)
    inputs = a_manifest(tmp_path, json.dumps({"name": "kit"}))
    beside = tmp_path / "note-kit"
    (beside / "hooks.json").write_text('{"PreToolUse": []}', encoding="utf-8")
    (beside / "mcp_config.json").write_text('{"mcpServers": {}}', encoding="utf-8")
    out = tmp_path / "out"

    result = convert_set(inputs, SOURCE, TARGET, root=root, out=out, allow_stale=True)
    found = properties(result.report)

    assert found["plugin.file.hooks"] == ("reproduced", "extension", "clean")
    assert found["plugin.file.mcp-config"] == ("reproduced", "extension", "clean")
    assert sorted(entry["to"] for entry in result.report["written"]) == [
        ".agents/plugins/note-kit/hooks.json",
        ".agents/plugins/note-kit/mcp_config.json",
        ".agents/plugins/note-kit/plugin.json",
    ]
    assert (out / ".agents/plugins/note-kit/hooks.json").read_text(
        encoding="utf-8"
    ) == '{"PreToolUse": []}'
    # Carried is not vouched for: these two files become commands on somebody else's
    # machine, and `clean` is a verdict about the transfer and never about what is inside.
    assert [
        line
        for line in result.report["advice"]
        if "hooks.json" in line or "mcp_config.json" in line
    ]
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)


def test_a_plugin_file_the_set_does_not_hold_earns_no_row(tmp_path: Path) -> None:
    """The target documents both files; this set holds neither, so neither is mentioned.

    A row about a file that is not there is an invention, and it would tell the owner of a
    plugin without hooks that their hooks did not cross.
    """
    root = manifest_tree(tmp_path)

    result = convert_set(
        a_manifest(tmp_path, json.dumps({"name": "kit"})),
        SOURCE,
        TARGET,
        root=root,
        allow_stale=True,
    )

    assert not [entry for entry in properties(result.report) if entry.startswith("plugin.file.")]
    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 0)
