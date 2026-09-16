"""The rules seam: a rules file goes in, translation lookups come out."""

from __future__ import annotations

from pathlib import Path

from agent_skill_adapter import rules

RULES_FILE = Path(__file__).resolve().parents[2] / "rules" / "claude-code-to-antigravity-1.0.yaml"


def test_model_values_translate_to_the_one_the_target_documents() -> None:
    """Both Claude Code model values map onto the single Antigravity tier.

    The pair is a user decision recorded in the rules file, not a guess made in code:
    read it back through the public lookup.
    """
    loaded = rules.load(RULES_FILE)

    assert loaded.value_of("subagent.frontmatter.model", "opus") == "pro"
    assert loaded.value_of("subagent.frontmatter.model", "sonnet") == "pro"


def test_a_tool_name_without_a_documented_pair_is_answered_with_no_pair() -> None:
    """Three pairs are documented; every other name gets `None`, never one made up.

    `Edit` and `Glob` are the tempting ones: the target has `replace_file_content` and
    `find_by_name`, which sound like them and are paired with nothing.
    """
    loaded = rules.load(RULES_FILE)

    assert loaded.tool_name("Read") == "view_file"
    assert loaded.tool_name("Grep") == "grep_search"
    assert loaded.tool_name("Bash") == "run_command"
    assert loaded.tool_name("Edit") is None
    assert loaded.tool_name("Glob") is None


MINIMAL = """
rules_version: "0.1"
ignore:
  - scratch
rewrite:
  include: ["*.md"]
  exclude: ["CHANGELOG.md"]
undocumented:
  action: skip
  note: nothing declares this file
"""


def test_the_ignore_list_comes_from_the_file_and_nowhere_else(tmp_path: Path) -> None:
    """A rules file naming only `scratch` ignores `scratch` and nothing else.

    If the module carried a built-in list, the caches this project's own rules name would
    still be ignored here — and they are not.
    """
    path = tmp_path / "minimal.yaml"
    path.write_text(MINIMAL, encoding="utf-8")
    loaded = rules.load(path)

    assert loaded.ignored("scratch/notes.txt") is True
    assert loaded.ignored("__pycache__/mod.pyc") is False
    assert loaded.ignored("docs/guide.md") is False


def test_the_shipped_ignore_list_covers_caches_anywhere_in_the_path() -> None:
    """A cache directory is kept out wherever it sits, together with everything under it."""
    loaded = rules.load(RULES_FILE)

    assert loaded.ignored("skills/demo/__pycache__/mod.cpython-310.pyc") is True
    assert loaded.ignored(".pytest_cache/v/cache/lastfailed") is True
    assert loaded.ignored(".omc/state.json") is True
    assert loaded.ignored("skills/demo/SKILL.md") is False


def test_a_change_history_is_never_rewritten_although_it_is_markdown() -> None:
    """`CHANGELOG.md` matches the `*.md` that substitution rewrites, and is still excluded.

    A change history records what was written; rewriting its links would turn it into a
    record of what we wish had been written.
    """
    loaded = rules.load(RULES_FILE)

    assert loaded.rewritable("skills/demo/SKILL.md") is True
    assert loaded.rewritable("CHANGELOG.md") is False
    assert loaded.rewritable("skills/demo/CHANGELOG.md") is False
    assert loaded.rewritable("skills/demo/diagram.svg") is False


def test_an_undocumented_file_gets_one_rule_carrying_what_to_do_and_what_to_say() -> None:
    """The rule is a decision plus a reason, so the report row has something to print."""
    loaded = rules.load(RULES_FILE)

    assert loaded.undocumented.action == "copy"
    assert loaded.undocumented.note.strip() != ""


def test_a_rules_file_missing_its_version_is_refused(tmp_path: Path) -> None:
    """The version is what a repeated transfer is compared against; without it, no rules."""
    path = tmp_path / "broken.yaml"
    path.write_text(MINIMAL.replace('rules_version: "0.1"', ""), encoding="utf-8")

    try:
        rules.load(path)
    except rules.InvalidRules as error:
        assert "rules_version" in str(error)
    else:  # pragma: no cover - the assertion below reports the miss
        raise AssertionError("a rules file without a version was accepted")
