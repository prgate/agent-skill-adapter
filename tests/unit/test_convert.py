"""Tests for the convert seam: one skill folder, two descriptions -> report and exit code."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from agent_skill_adapter.cli.main import app
from agent_skill_adapter.convert import Scope, Verdict, convert
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
"""Thirteen ways a skill file is not one. Each must stop the run rather than be read halfway."""


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_folder_that_is_not_a_skill_stops_the_run_and_still_reports(
    tmp_path: Path, case: str
) -> None:
    """Exit code 6, no properties, and a report that names the file it could not read.

    A duplicate key is here because PyYAML keeps the last of the two without a word: read
    and not refused, the frontmatter would convert as a value nobody chose. An anchor and
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


def test_a_field_the_descriptions_call_optional_is_not_demanded_here(tmp_path: Path) -> None:
    """A skill file without `name` converts: both environments default it to the folder name.

    Requiring it would be this command inventing a rule about environments it only reads
    about -- and inventing it in the harshest form there is, a refusal to read the file at
    all. What a field is worth is written in the descriptions, and `name` says "optional".
    """
    root = four_row_tree(tmp_path)
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "SKILL.md").write_text("---\ndescription: what it does\n---\n\nBody.\n")

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
    assert len(set(result.report["advice"])) == 3


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
    assert len(set(unheard_of.report["advice"])) == 3


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

    assert [(entry["from"], entry["to"]) for entry in result.report["written"]] == [
        ("SKILL.md", ".agents/skills/example/SKILL.md"),
        ("scripts/", ".agents/skills/example/scripts/"),
    ]
    carried = out / ".agents/skills/example/scripts/run.sh"
    assert carried.read_text(encoding="utf-8") == "echo hi\n"
    assert (out / ".agents/skills/example/SKILL.md").is_file()
    assert not (out / ".agents/skills/example/sandbox").exists()
    assert any("sandbox/" in line for line in result.report["advice"])
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
        "skill.frontmatter.description": ("reproduced", "extension", "clean"),
        "skill.top.README.md": ("unknown", "extension", "lossy"),
    }
    assert rows["skill.top.README.md"]["found_as"] == "top-level file `README.md`"
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
