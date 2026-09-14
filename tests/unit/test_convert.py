"""Tests for the convert seam: one skill folder, two descriptions -> report and exit code."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_skill_adapter.convert import Scope, Verdict, convert
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
        "skill.frontmatter.hooks": ("reproduced", "extension", "clean"),
        "hook.event.PreToolUse": ("reproduced", "extension", "clean"),
        "hook.decision.block": ("unknown", "extension", "lossy"),
    }
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)
    assert len(result.report["advice"]) == 3
    assert "pre-commit" in " ".join(result.report["advice"])


def assembly_tree(tmp_path: Path) -> Path:
    """The four-row descriptions, plus a target that names where a skill of it lives."""
    root = four_row_tree(tmp_path)
    write(
        root,
        vendor="google",
        environment="antigravity",
        capabilities=[
            {"id": "skill.frontmatter.name", "support": "supported"},
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
    on a guess -- it keeps its row in the report and stays where it is.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n", directories=("scripts", "sandbox"))
    (folder / "scripts" / "run.sh").write_text("echo hi\n", encoding="utf-8")
    (folder / "sandbox" / "toy.txt").write_text("toy\n", encoding="utf-8")
    out = tmp_path / "out"

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert [(entry["from"], entry["to"]) for entry in result.report["written"]] == [
        ("SKILL.md", ".agents/skills/example/SKILL.md"),
        ("scripts/", ".agents/skills/example/scripts/"),
    ]
    carried = out / ".agents/skills/example/scripts/run.sh"
    assert carried.read_text(encoding="utf-8") == "echo hi\n"
    assert (out / ".agents/skills/example/SKILL.md").is_file()
    assert not (out / ".agents/skills/example/sandbox").exists()
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)


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
    occupied = out / ".agents/skills/example/scripts"
    occupied.mkdir(parents=True)
    (occupied / "run.sh").write_text("mine\n", encoding="utf-8")

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert (result.verdict, result.exit_code) == (Verdict.CLEAN, 8)
    assert result.report["outcome"] == "clean"
    assert (occupied / "run.sh").read_text(encoding="utf-8") == "mine\n"
    assert not (out / ".agents/skills/example/SKILL.md").exists()
    assert result.report["written"] == []
    assert result.report["error"]


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
            "to": f"{home}/.gemini/config/skills/example/SKILL.md",
            "path": str(out / ".gemini/config/skills/example/SKILL.md"),
        }
    ]
    assert (out / ".gemini/config/skills/example/SKILL.md").is_file()
    assert not home.exists()


def test_a_destination_the_description_puts_outside_out_is_refused(tmp_path: Path) -> None:
    """A layout path that is absolute leads out of `out`, and the run refuses to follow it.

    `Path(out) / "/somewhere"` is `/somewhere`: joining an absolute path throws the root
    away without a word. A description is data like any other, and the promise that this
    command writes only under `out` cannot rest on every description being well behaved.
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
    assert result.exit_code != 0


def test_a_dangling_link_at_the_destination_is_an_occupied_place(tmp_path: Path) -> None:
    """A symbolic link pointing nowhere is not an empty place, and is not written through.

    `exists()` answers `False` for a link whose target is missing, and writing to the link
    then creates that target -- outside `out`, under a name the caller never named. The
    place is taken by the link itself, whatever it points at.
    """
    root = assembly_tree(tmp_path)
    folder = skill(tmp_path / "example", "name: example\n")
    out = tmp_path / "out"
    (out / ".agents/skills/example").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (out / ".agents/skills/example/SKILL.md").symlink_to(elsewhere / "SKILL.md")

    result = convert(folder, SOURCE, TARGET, root=root, out=out, allow_stale=True)

    assert result.exit_code == 8
    assert list(elsewhere.iterdir()) == []
    assert result.report["written"] == []


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
        "skill.top.README.md": ("unknown", "extension", "lossy"),
    }
    assert rows["skill.top.README.md"]["found_as"] == "top-level file `README.md`"
    assert (result.verdict, result.exit_code) == (Verdict.LOSSY, 1)
