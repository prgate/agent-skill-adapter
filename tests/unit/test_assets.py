"""Reading an asset set off the disk: a folder tree in, a list of entities out.

Every set the tests build here is laid out under names nobody documented, because the point
of the seam is that the composition of the input decides what a path is, and never the name
a repository happened to give the folder.
"""

from __future__ import annotations

import json
import re
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

COMMAND = """\
---
description: does it
---

Do it.
"""
"""One command file, opening with the header that makes it an entity of its folder.

A file in that folder without one says nothing about being a command, so it is read as a
path nobody declared rather than counted among them.
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
    (root / "verbs" / "do.md").write_text(COMMAND, encoding="utf-8")

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


def test_a_markdown_file_that_is_no_subagent_beside_the_subagents_is_a_row_and_not_a_refusal(
    tmp_path: Path,
) -> None:
    """The same rule as a stray folder beside the skills, one folder over (FR-3a).

    A `README.md` in a folder of subagents is a file about the folder and not one of its
    entities, and a run that refuses over it loses every subagent that was there. What tells
    the two apart is the file itself: a subagent opens with the line its header opens with.
    """
    root = build(tmp_path)
    (root / "people" / "README.md").write_text("These are the subagents.\n", encoding="utf-8")

    read = assets.read(assets.Inputs(translation=rules_for(tmp_path), agents=(root / "people",)))

    assert only(read, assets.Kind.SUBAGENT).name == "helper"
    said = {
        finding.found_as: finding.note
        for asset in read
        for finding in asset.findings
        if not finding.ids
    }
    assert said["README.md"] == assets.UNDECLARED


def test_a_file_with_no_header_beside_the_commands_is_not_counted_as_one(tmp_path: Path) -> None:
    """The row for it says nobody declared it, and the set holds exactly as many commands as before.

    A command may be written with no header and still be a command, but a file with no header
    is indistinguishable from any other Markdown in the folder -- so calling it one would put
    it in the report as the one thing this reading can be sure it is not, and every count
    taken over the commands of the set would count it.
    """

    def commands_of(read: tuple[assets.Asset, ...]) -> list[str]:
        return [asset.name for asset in read if asset.kind is assets.Kind.COMMAND and asset.name]

    root = build(tmp_path)
    inputs = assets.Inputs(translation=rules_for(tmp_path), commands=(root / "verbs",))
    before = commands_of(assets.read(inputs))

    (root / "verbs" / "README.md").write_text("These are the commands.\n", encoding="utf-8")

    read = assets.read(inputs)

    assert before == ["do"]
    assert commands_of(read) == before
    said = {
        finding.found_as: finding.note
        for asset in read
        for finding in asset.findings
        if not finding.ids
    }
    assert said["README.md"] == assets.UNDECLARED


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
"""Twenty-one ways a skill file is not one. Each must stop the reading rather than be read
halfway.

A set and a block of bytes are here because neither has a text it always reads back as: the
same header would put different bytes in the assembled file on every run, and a converter
whose output moves on a fixed input cannot be checked against anything. `.nan`, `.inf` and
`-.inf` are here for the other half of the same rule: JSON has no such number, and
`json.dumps` writes them as a bare `NaN` or `Infinity` that a strict reader refuses -- the
file would leave here looking assembled and arrive as something the target cannot load.
"""


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_folder_that_is_not_a_skill_is_refused_by_what_is_wrong_with_it(
    tmp_path: Path, case: str
) -> None:
    """A refusal naming the path, and never a header read halfway.

    A duplicate key is here because PyYAML keeps the last of the two without a word: read
    and not refused, the frontmatter would convert as a value nobody chose. Two keys that
    become one only once the header is carried across are the same duplicate, made by this
    command rather than by the person, and are refused the same way. An anchor and its alias
    are the same defect in another spelling -- what a reader sees in the file and what the
    parser builds stop being the same text (FR-15). A header without `description` is a
    missing required field, which FR-16 counts as a structural break and not as an optional
    field left out; `name` is not in that company.
    """
    folder = tmp_path / "example"
    folder.mkdir()
    content = BROKEN[case]
    if content is not None:
        (folder / "SKILL.md").write_bytes(content)

    with pytest.raises(assets.ReadError) as refusal:
        assets.read(assets.Inputs(translation=rules_for(tmp_path), skill=(folder,)))

    assert str(folder) in str(refusal.value)


def test_two_header_keys_that_carry_across_as_one_are_both_named(tmp_path: Path) -> None:
    """A date key and the quoted text of it are two keys in the file and one after carrying.

    Whichever of the two values is dropped, dropping it silently is the failure this command
    exists to prevent, so the reading stops. The message names the place inside the header and
    both keys as they are written there: "a key was lost" is nothing a person can act on
    without knowing which, and the two read the same once either is a plain string.
    """
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\ndescription: what it does\nhooks:\n  PreToolUse:\n"
        "    2026-09-14: from-date-key\n    '2026-09-14': from-string-key\n---\n\nBody.\n",
        encoding="utf-8",
    )

    with pytest.raises(assets.ReadError) as refusal:
        assets.read(assets.Inputs(translation=rules_for(tmp_path), skill=(folder,)))

    said = str(refusal.value)

    assert "frontmatter.hooks.PreToolUse" in said
    # As the header writes them: the date bare, the text quoted. A Python `repr` would name
    # the type instead -- `datetime.date(2026, 9, 14)` -- which is a string the file does not
    # contain, and the module refuses to name a value by its type.
    assert re.search(r"(?<!['\w])2026-09-14(?!['\w])", said)
    assert "'2026-09-14'" in said
    assert "datetime" not in said


def test_a_value_the_header_had_to_rewrite_to_cross_is_named(tmp_path: Path) -> None:
    """The reading says which value changed shape, what it was and what it became.

    Unsaid, the only trace of a value entering as a date and leaving as text would be the
    text itself, and nothing downstream could tell a rewritten value from a written one.
    """
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\ndescription: what it does\nmodel: 2026-09-14\n---\n\nBody.\n", encoding="utf-8"
    )

    read = assets.read(assets.Inputs(translation=rules_for(tmp_path), skill=(folder,)))
    said = [
        finding.note
        for finding in read[0].findings
        if finding.note and "frontmatter.model" in finding.note
    ]

    assert len(said) == 1
    assert "date" in said[0]
    assert "2026-09-14" in said[0]
