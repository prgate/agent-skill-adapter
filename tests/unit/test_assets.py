"""Reading an asset set off the disk: a folder tree in, a list of entities out.

Every set the tests build here is laid out under names nobody documented, because the point
of the seam is that the composition of the input decides what a path is, and never the name
a repository happened to give the folder.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_skill_adapter import assets
from agent_skill_adapter.rules import Rules, load

RULES = """
rules_version: "1.0"
ignore:
  - __pycache__
  - "*.py[co]"
undocumented:
  action: copy
  note: nothing declares this file
"""

SKILL = """\
---
name: alpha
description: does alpha things
hooks:
  PreToolUse: echo hi
---

The body of the skill.
"""

SUBAGENT = """\
---
name: helper
description: helps
model: sonnet
---

You are a helper.
"""


def rules_for(tmp_path: Path) -> Rules:
    path = tmp_path / "translation.yaml"
    path.write_text(RULES, encoding="utf-8")
    return load(path)


def build(tmp_path: Path) -> Path:
    """A set whose folders are named nothing like the ones any environment documents."""
    root = tmp_path / "set"
    skill = root / "bundles" / "alpha"
    (skill / "notes").mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (skill / "README.md").write_text("read me", encoding="utf-8")
    (skill / "notes" / "one.md").write_text("one", encoding="utf-8")

    (root / "people").mkdir()
    (root / "people" / "helper.md").write_text(SUBAGENT, encoding="utf-8")

    (root / "verbs").mkdir()
    (root / "verbs" / "do.md").write_text("do it", encoding="utf-8")

    (root / "laws").mkdir()
    (root / "laws" / "tone.md").write_text("be kind", encoding="utf-8")

    (root / "plugin.json").write_text(json.dumps({"name": "set"}), encoding="utf-8")
    return root


def whole(tmp_path: Path) -> assets.Inputs:
    root = build(tmp_path)
    return assets.Inputs(
        translation=rules_for(tmp_path),
        skills=(root / "bundles",),
        agents=(root / "people",),
        commands=(root / "verbs",),
        rules=(root / "laws" / "tone.md",),
        plugin=root / "plugin.json",
    )


def ids_of(asset: assets.Asset) -> set[str]:
    return {entry for finding in asset.findings for entry in finding.ids}


def only(read: tuple[assets.Asset, ...], kind: assets.Kind) -> assets.Asset:
    found = [asset for asset in read if asset.kind is kind and asset.name]
    assert len(found) == 1, f"expected one {kind.value}, got {[a.name for a in found]}"
    return found[0]


def test_every_part_of_the_set_is_read_as_its_own_kind(tmp_path: Path) -> None:
    read = assets.read(whole(tmp_path))

    assert {asset.kind for asset in read} == set(assets.Kind)
    assert only(read, assets.Kind.SKILL).name == "alpha"
    assert only(read, assets.Kind.SUBAGENT).name == "helper"
    assert only(read, assets.Kind.COMMAND).name == "do"
    assert only(read, assets.Kind.RULES).name == "tone"
    assert only(read, assets.Kind.MANIFEST).name == "plugin"


def test_each_entity_asks_the_descriptions_about_the_ids_of_its_own_kind(
    tmp_path: Path,
) -> None:
    read = assets.read(whole(tmp_path))

    assert ids_of(only(read, assets.Kind.SKILL)) == {
        "skill.frontmatter.name",
        "skill.frontmatter.description",
        "skill.frontmatter.hooks",
        "skill.dir.notes",
        "skill.top.README.md",
        "hook.event.PreToolUse",
        "hook.decision.block",
    }
    assert ids_of(only(read, assets.Kind.SUBAGENT)) == {
        "subagent.frontmatter.name",
        "subagent.frontmatter.description",
        "subagent.frontmatter.model",
        "subagent.system-prompt-body",
    }
    assert ids_of(only(read, assets.Kind.COMMAND)) == {"command.file"}
    assert ids_of(only(read, assets.Kind.RULES)) == {"rules.file"}
    assert ids_of(only(read, assets.Kind.MANIFEST)) == {"settings.file.plugin-manifest"}


def test_the_frontmatter_of_an_entity_is_carried_as_it_was_written(tmp_path: Path) -> None:
    read = assets.read(whole(tmp_path))

    assert only(read, assets.Kind.SUBAGENT).frontmatter["model"] == "sonnet"


def test_a_set_without_subagents_reads_exactly_as_one_with_them(tmp_path: Path) -> None:
    given = whole(tmp_path)
    without = assets.read(assets.Inputs(translation=given.translation, skills=given.skills))
    with_them = assets.read(given)

    assert [asset.name for asset in without] == [only(with_them, assets.Kind.SKILL).name]
    assert ids_of(without[0]) == ids_of(only(with_them, assets.Kind.SKILL))


def test_a_named_folder_that_is_empty_is_not_an_error_and_is_still_said_out_loud(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "nobody"
    empty.mkdir()

    read = assets.read(assets.Inputs(translation=rules_for(tmp_path), agents=(empty,)))

    assert [asset.name for asset in read] == [""]
    assert read[0].kind is assets.Kind.SUBAGENT
    assert read[0].path == empty
    assert any("empty" in (finding.note or "") for finding in read[0].findings)


def test_a_named_folder_that_is_not_there_is_refused_by_its_path(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere"

    with pytest.raises(assets.ReadError) as refusal:
        assets.read(assets.Inputs(translation=rules_for(tmp_path), skills=(missing,)))

    assert str(missing) in str(refusal.value)


def test_a_composition_named_by_no_option_at_all_is_refused_by_what_is_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(assets.ReadError) as refusal:
        assets.read(assets.Inputs(translation=rules_for(tmp_path)))

    said = str(refusal.value)
    assert "skills" in said and "subagents" in said and "manifest" in said


def test_what_the_rules_keep_out_is_dropped_at_reading_and_named_where_it_was(
    tmp_path: Path,
) -> None:
    root = build(tmp_path)
    skill = root / "bundles" / "alpha"
    (skill / "__pycache__").mkdir()
    (skill / "__pycache__" / "stale.pyc").write_bytes(b"\x00")
    (skill / "notes" / "draft.pyo").write_bytes(b"\x00")

    read = assets.read(assets.Inputs(translation=rules_for(tmp_path), skills=(root / "bundles",)))
    alpha = only(read, assets.Kind.SKILL)

    assert "skill.dir.__pycache__" not in ids_of(alpha)
    dropped = {finding.found_as for finding in alpha.findings if not finding.ids}
    assert "__pycache__/" in dropped
    assert "notes/draft.pyo" in dropped


def test_a_folder_reached_through_a_link_is_not_walked_and_is_still_said_out_loud(
    tmp_path: Path,
) -> None:
    root = build(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "ghost.md").write_text(SUBAGENT, encoding="utf-8")
    (root / "people" / "linked").symlink_to(elsewhere, target_is_directory=True)

    read = assets.read(assets.Inputs(translation=rules_for(tmp_path), agents=(root / "people",)))

    assert [asset.name for asset in read if asset.name] == ["helper"]
    said = {finding.found_as for asset in read for finding in asset.findings if not finding.ids}
    assert "linked/" in said


def test_a_folder_that_is_no_skill_beside_the_skills_is_a_row_and_not_a_refusal(
    tmp_path: Path,
) -> None:
    root = build(tmp_path)
    (root / "bundles" / "scratch").mkdir()
    (root / "bundles" / "scratch" / "note.txt").write_text("nothing", encoding="utf-8")

    read = assets.read(assets.Inputs(translation=rules_for(tmp_path), skills=(root / "bundles",)))

    assert only(read, assets.Kind.SKILL).name == "alpha"
    said = {finding.found_as for asset in read for finding in asset.findings if not finding.ids}
    assert "scratch/" in said


def test_a_skill_folder_the_person_named_is_still_refused_when_it_is_no_skill(
    tmp_path: Path,
) -> None:
    stray = tmp_path / "scratch"
    stray.mkdir()

    with pytest.raises(assets.ReadError) as refusal:
        assets.read(assets.Inputs(translation=rules_for(tmp_path), skill=(stray,)))

    assert str(stray) in str(refusal.value)


def test_a_link_deeper_than_the_top_of_a_skill_is_said_out_loud_too(tmp_path: Path) -> None:
    root = build(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "__pycache__").mkdir(parents=True)
    (elsewhere / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (root / "bundles" / "alpha" / "notes" / "linked").symlink_to(
        elsewhere, target_is_directory=True
    )

    read = assets.read(assets.Inputs(translation=rules_for(tmp_path), skills=(root / "bundles",)))
    alpha = only(read, assets.Kind.SKILL)

    said = {finding.found_as for finding in alpha.findings if not finding.ids}
    assert "notes/linked/" in said
