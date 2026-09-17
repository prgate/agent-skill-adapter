"""Tests for the two seams of the envspec core: text -> hash, and file -> EnvSpec."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_skill_adapter.envspec.loader import InvalidSpec, load
from agent_skill_adapter.envspec.model import Support
from agent_skill_adapter.envspec.normalize import AnchorError, digest, section_text


def test_digest_ignores_line_endings_trailing_spaces_and_blank_runs() -> None:
    noisy = "\r\n\r\nalpha   \r\n\r\n\r\n\r\nbeta\t\r\n\r\n"
    assert digest(noisy) == hashlib.sha256(b"alpha\n\nbeta").hexdigest()


def test_digest_changes_when_a_word_changes() -> None:
    assert digest("alpha\n\nbeta") != digest("alpha\n\ngamma")


SECTION_DOC = """# Page title

intro text

## Frontmatter   Fields

field text

### Nested detail

nested text

```bash
# not a heading
```

tail text

## Other section

other text
"""


def test_section_text_spans_until_the_next_heading_of_the_same_level() -> None:
    section = section_text(SECTION_DOC, "Frontmatter Fields")
    assert "field text" in section
    assert "nested text" in section, "a deeper heading belongs to the section"
    assert "not a heading" in section, "a hash inside a fenced block is not a heading"
    assert "tail text" in section
    assert "intro text" not in section
    assert "other text" not in section


def test_section_text_matches_the_anchor_ignoring_case_and_spacing() -> None:
    assert section_text(SECTION_DOC, "  frontmatter fields ") == section_text(
        SECTION_DOC, "Frontmatter   Fields"
    )


def test_section_text_refuses_an_ambiguous_or_missing_anchor() -> None:
    twice = "## Limits\n\nfirst\n\n## Limits\n\nsecond\n"
    with pytest.raises(AnchorError):
        section_text(twice, "Limits")
    with pytest.raises(AnchorError):
        section_text(SECTION_DOC, "No such heading")


def valid_spec() -> dict[str, Any]:
    """A description that satisfies the schema; each test breaks one thing in it."""
    return {
        "schema_version": 1,
        "vendor": "anthropic",
        "environment": "claude-code",
        "version_range": ">=2.1.0,<2.2.0",
        "checked_at": date(2026, 9, 14),
        "stale_after_days": 30,
        "normalization": "v1",
        "sources": [
            {
                "id": "skills-doc",
                "url": "https://example.test/skills",
                "markdown_url": "https://example.test/skills.md",
                "anchor": "Frontmatter fields",
                "sha256": "a" * 64,
                "checked_at": date(2026, 9, 14),
                "environment_version": "2.1.270",
            }
        ],
        "capabilities": [
            {
                "id": "skill.frontmatter.tool-allowlist",
                "kind": "skill-field",
                "support": "supported",
                "source_id": "skills-doc",
                "since_version": "2.1.246",
                "note": "limits the agent tool set",
            }
        ],
        "layout": [{"id": "skills.root", "path": ".claude/skills/", "source_id": "skills-doc"}],
        "limits": [
            {"id": "skill.file.size", "value": 15000, "unit": "bytes", "source_id": "skills-doc"}
        ],
        "invisible_sources": [
            {"id": "user-hooks", "path": "~/.claude/settings.json", "source_id": "skills-doc"}
        ],
        "discrepancies": [],
    }


def write_spec(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_reads_a_valid_spec(tmp_path: Path) -> None:
    spec = load(write_spec(tmp_path, valid_spec()))

    assert spec.checked_at == date(2026, 9, 14)
    assert spec.capabilities[0].support is Support.SUPPORTED
    assert spec.capabilities[0].since_version == "2.1.246"
    assert spec.limits[0].unit == "bytes"
    assert spec.layout[0].path == ".claude/skills/"
    assert spec.invisible_sources[0].path == "~/.claude/settings.json"


def test_load_rejects_an_unknown_field(tmp_path: Path) -> None:
    data = valid_spec()
    data["capabilities"][0]["supports"] = "supported"
    with pytest.raises(InvalidSpec):
        load(write_spec(tmp_path, data))


def test_load_rejects_a_duplicate_capability_id(tmp_path: Path) -> None:
    data = valid_spec()
    data["capabilities"].append(dict(data["capabilities"][0]))
    with pytest.raises(InvalidSpec):
        load(write_spec(tmp_path, data))


def test_load_rejects_a_source_id_with_no_such_source(tmp_path: Path) -> None:
    data = valid_spec()
    data["limits"][0]["source_id"] = "no-such-source"
    with pytest.raises(InvalidSpec):
        load(write_spec(tmp_path, data))


@pytest.mark.parametrize("field", ["anchor", "sha256"])
def test_load_rejects_a_source_without_anchor_or_hash(tmp_path: Path, field: str) -> None:
    data = valid_spec()
    del data["sources"][0][field]
    with pytest.raises(InvalidSpec):
        load(write_spec(tmp_path, data))


def test_digest_is_equal_for_decomposed_and_composed_forms() -> None:
    composed = "\u00e9"  # e with acute, one code point
    decomposed = "e\u0301"  # plain e followed by a combining acute
    assert composed != decomposed, "the two spellings must differ before hashing"
    assert digest(composed) == digest(decomposed)


def test_section_text_closes_a_fence_only_with_its_own_marker() -> None:
    doc = (
        "## Limits\n\n~~~\n```\n# not a heading\n~~~\n\nafter the block\n\n## Next\n\nother text\n"
    )
    section = section_text(doc, "Limits")
    assert "not a heading" in section
    assert "after the block" in section
    assert "other text" not in section


def test_load_rejects_a_spec_without_a_normalization_rule(tmp_path: Path) -> None:
    data = valid_spec()
    del data["normalization"]
    with pytest.raises(InvalidSpec):
        load(write_spec(tmp_path, data))


@pytest.mark.parametrize("broken", ["2.1.0", ">=2.1.0,<", "~>2.1.0", ">=2.1.0 <2.2.0", ">=v2.1.0"])
def test_load_rejects_a_malformed_version_range(tmp_path: Path, broken: str) -> None:
    data = valid_spec()
    data["version_range"] = broken
    with pytest.raises(InvalidSpec):
        load(write_spec(tmp_path, data))


def test_section_text_needs_a_closing_fence_as_long_as_the_opening_one() -> None:
    doc = (
        "## Limits\n\n````\n```\n# not a heading\n````\n\n"
        "after the block\n\n## Next\n\nother text\n"
    )
    section = section_text(doc, "Limits")
    assert "not a heading" in section, "a shorter marker does not close a longer fence"
    assert "after the block" in section
    assert "other text" not in section


@pytest.mark.parametrize(
    "broken",
    [
        "agentskills/agent-skills",  # no version
        "agent-skills@1.0",  # no vendor
        "agentskills/agent-skills@1.0-beta",  # not a dotted numeric version
        "agentskills/agent-skills@latest",
        "agentskills/agent skills@1.0",
        "agentskills/agent-skills@1.0 ",
    ],
)
def test_load_rejects_a_reference_that_is_not_vendor_environment_at_version(
    tmp_path: Path, broken: str
) -> None:
    """``extends`` must name one description exactly, or the loader has nowhere to go."""
    data = valid_spec()
    data["extends"] = broken
    with pytest.raises(InvalidSpec):
        load(write_spec(tmp_path, data))
