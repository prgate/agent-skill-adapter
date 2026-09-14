"""Tests for the loader seam: a tree of files -> selection by version -> staleness."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_skill_adapter.envspec.loader import (
    AmbiguousSpec,
    ExtendsCycle,
    InvalidSpec,
    InvalidVersion,
    SpecNotFound,
    StaleSpec,
    base_specs,
    capability,
    is_inherited,
    is_stale,
    load,
    load_all,
    select,
)
from agent_skill_adapter.envspec.model import Support

TODAY = date(2026, 9, 14)


def write_spec(
    root: Path,
    name: str,
    version_range: str,
    *,
    vendor: str = "anthropic",
    environment: str = "claude-code",
    checked_at: date = TODAY,
    stale_after_days: int = 30,
    discrepancies: list[dict[str, str]] | None = None,
    extends: str | None = None,
    capability_id: str = "skill.frontmatter.tool-allowlist",
    layout_id: str | None = None,
) -> Path:
    """Write one minimal valid description into ``root/vendor/name.yaml``."""
    data: dict[str, Any] = {
        "schema_version": 1,
        "vendor": vendor,
        "environment": environment,
        "version_range": version_range,
        "checked_at": checked_at,
        "stale_after_days": stale_after_days,
        "normalization": "v1",
        "sources": [
            {
                "id": "skills-doc",
                "url": "https://example.test/skills",
                "anchor": "Frontmatter fields",
                "sha256": "a" * 64,
                "checked_at": checked_at,
                "environment_version": "2.1.270",
            }
        ],
        "capabilities": [
            {
                "id": capability_id,
                "kind": "skill-field",
                "support": "supported",
                "source_id": "skills-doc",
            }
        ],
        "layout": (
            [{"id": layout_id, "path": ".claude/skills/", "source_id": "skills-doc"}]
            if layout_id
            else []
        ),
        "discrepancies": discrepancies or [],
    }
    if extends is not None:
        data["extends"] = extends
    path = root / vendor / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_select_returns_the_description_whose_range_covers_the_version(tmp_path: Path) -> None:
    write_spec(tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0")
    write_spec(tmp_path, "claude-code-2.2", ">=2.2.0,<2.3.0")

    assert len(load_all(tmp_path)) == 2
    assert select(tmp_path, "anthropic", "claude-code", "2.2.7", today=TODAY).version_range == (
        ">=2.2.0,<2.3.0"
    )
    assert select(tmp_path, "anthropic", "claude-code", "2.1.270", today=TODAY).version_range == (
        ">=2.1.0,<2.2.0"
    )


def test_select_refuses_a_version_outside_every_range(tmp_path: Path) -> None:
    write_spec(tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0")
    write_spec(tmp_path, "claude-code-2.2", ">=2.2.0,<2.3.0")

    with pytest.raises(SpecNotFound) as error:
        select(tmp_path, "anthropic", "claude-code", "3.0.0", today=TODAY)

    message = str(error.value)
    assert "3.0.0" in message
    assert ">=2.1.0,<2.2.0" in message, "the declared ranges are listed"
    assert ">=2.2.0,<2.3.0" in message


def test_select_refuses_when_two_ranges_cover_the_same_version(tmp_path: Path) -> None:
    first = write_spec(tmp_path, "claude-code-2.1", ">=2.1.0,<2.3.0")
    second = write_spec(tmp_path, "claude-code-2.2", ">=2.2.0,<2.3.0")

    with pytest.raises(AmbiguousSpec) as error:
        select(tmp_path, "anthropic", "claude-code", "2.2.7", today=TODAY)

    message = str(error.value)
    assert first.name in message
    assert second.name in message


def test_select_ignores_another_vendor_or_environment(tmp_path: Path) -> None:
    write_spec(
        tmp_path, "antigravity-2.1", ">=2.1.0,<2.2.0", vendor="google", environment="antigravity"
    )
    write_spec(tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0")

    assert select(tmp_path, "google", "antigravity", "2.1.0", today=TODAY).vendor == "google"
    with pytest.raises(SpecNotFound):
        select(tmp_path, "google", "claude-code", "2.1.0", today=TODAY)


def test_is_stale_by_date_alone_without_any_freshness_run(tmp_path: Path) -> None:
    path = write_spec(
        tmp_path,
        "claude-code-2.1",
        ">=2.1.0,<2.2.0",
        checked_at=TODAY - timedelta(days=30),
        stale_after_days=30,
    )
    spec = load(path)

    assert spec.discrepancies == [], "no freshness run has ever touched this description"
    assert is_stale(spec, TODAY) is False, "exactly stale_after_days old is still fresh"
    assert is_stale(spec, TODAY + timedelta(days=1)) is True


def test_is_stale_when_the_check_date_lies_in_the_future(tmp_path: Path) -> None:
    path = write_spec(
        tmp_path,
        "claude-code-2.1",
        ">=2.1.0,<2.2.0",
        checked_at=TODAY + timedelta(days=1),
    )
    spec = load(path)

    assert is_stale(spec, TODAY) is True, "a check dated ahead of today cannot be trusted"
    assert is_stale(spec, TODAY + timedelta(days=1)) is False, "on that day it is simply fresh"
    with pytest.raises(StaleSpec):
        select(tmp_path, "anthropic", "claude-code", "2.1.270", today=TODAY)


def test_is_stale_with_a_recorded_discrepancy_even_when_checked_today(tmp_path: Path) -> None:
    path = write_spec(
        tmp_path,
        "claude-code-2.1",
        ">=2.1.0,<2.2.0",
        discrepancies=[{"source_id": "skills-doc", "kind": "changed"}],
    )

    assert is_stale(load(path), TODAY) is True


def test_select_refuses_a_stale_description_unless_staleness_is_waived(tmp_path: Path) -> None:
    write_spec(
        tmp_path,
        "claude-code-2.1",
        ">=2.1.0,<2.2.0",
        checked_at=TODAY - timedelta(days=100),
    )

    with pytest.raises(StaleSpec):
        select(tmp_path, "anthropic", "claude-code", "2.1.270", today=TODAY)

    waived = select(tmp_path, "anthropic", "claude-code", "2.1.270", allow_stale=True, today=TODAY)
    assert waived.version_range == ">=2.1.0,<2.2.0"


def test_capability_is_unknown_when_the_description_has_no_such_entry(tmp_path: Path) -> None:
    spec = load(write_spec(tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0"))

    assert capability(spec, "skill.frontmatter.tool-allowlist") is Support.SUPPORTED
    assert capability(spec, "skill.frontmatter.no-such-field") is Support.UNKNOWN


def test_select_refuses_a_version_it_cannot_parse(tmp_path: Path) -> None:
    write_spec(tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0")

    for asked in ("2.1.0-beta", "latest", ""):
        with pytest.raises(InvalidVersion) as error:
            select(tmp_path, "anthropic", "claude-code", asked, today=TODAY)
        assert repr(asked) in str(error.value)


def test_load_refuses_a_version_range_it_cannot_parse(tmp_path: Path) -> None:
    path = write_spec(tmp_path, "claude-code-2.1", "2.1 or newer")

    with pytest.raises(InvalidSpec):
        load(path)
    with pytest.raises(InvalidSpec):
        load_all(tmp_path)  # a broken file fails the whole tree, it is not skipped


# Any of these in a module other than freshness breaks the offline promise (R29).
NETWORK = r"urllib|http|socket|requests|httpx"
REACHES_NETWORK = re.compile(
    rf"^\s*(?:import|from)\s+(?:{NETWORK})\b"
    rf"""|(?:import_module|__import__)\s*\(\s*["'](?:{NETWORK})\b""",
    re.MULTILINE,
)


def test_only_the_freshness_module_may_reach_the_network() -> None:
    package = Path(__file__).resolve().parents[2] / "src" / "agent_skill_adapter"
    allowed = package / "envspec" / "freshness.py"
    offenders = [
        str(module.relative_to(package))
        for module in package.rglob("*.py")
        if module != allowed and REACHES_NETWORK.search(module.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_base_specs_walks_the_whole_chain_and_tells_inherited_from_own(tmp_path: Path) -> None:
    """An entry of any description up the chain is inherited; the rest is the environment's own."""
    write_spec(
        tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0", extends="agentskills/agent-skills@1.0"
    )
    write_spec(
        tmp_path,
        "agent-skills-1.0",
        ">=1.0,<2.0",
        vendor="agentskills",
        environment="agent-skills",
        extends="agentskills/agent-skills-core@0.9",
        capability_id="skill.frontmatter.name",
        layout_id="skills.root",
    )
    write_spec(
        tmp_path,
        "agent-skills-core-0.9",
        ">=0.9,<1.0",
        vendor="agentskills",
        environment="agent-skills-core",
        capability_id="skill.frontmatter.description",
    )

    spec = select(tmp_path, "anthropic", "claude-code", "2.1.270", today=TODAY)
    bases = base_specs(spec, tmp_path, today=TODAY)

    assert [base.environment for base in bases] == ["agent-skills", "agent-skills-core"]
    assert base_specs(bases[-1], tmp_path, today=TODAY) == (), "a description extending nothing"
    assert is_inherited(bases, "skill.frontmatter.name", among="capabilities") is True
    assert is_inherited(bases, "skills.root", among="layout") is True, "a place is inherited too"
    assert is_inherited(bases, "skill.frontmatter.description", among="capabilities") is True, (
        "from further up the chain too"
    )
    assert is_inherited(bases, "skill.frontmatter.tool-allowlist", among="capabilities") is False, (
        "the vendor's own"
    )
    assert is_inherited(bases, "skills.root", among="capabilities") is False, (
        "a place of the base declares nothing about a field of that name"
    )
    assert is_inherited(bases, "skill.frontmatter.name", among="layout") is False, (
        "and a field of the base declares nothing about a place of that name"
    )


def test_base_specs_refuses_a_loop_instead_of_walking_forever(tmp_path: Path) -> None:
    write_spec(
        tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0", extends="agentskills/agent-skills@1.0"
    )
    write_spec(
        tmp_path,
        "agent-skills-1.0",
        ">=1.0,<2.0",
        vendor="agentskills",
        environment="agent-skills",
        extends="anthropic/claude-code@2.1.270",
    )
    spec = select(tmp_path, "anthropic", "claude-code", "2.1.270", today=TODAY)

    with pytest.raises(ExtendsCycle) as error:
        base_specs(spec, tmp_path, today=TODAY)

    assert "agentskills/agent-skills@1.0" in str(error.value), "the loop is named, not just found"


def test_base_specs_refuses_a_reference_no_description_covers(tmp_path: Path) -> None:
    path = write_spec(
        tmp_path, "claude-code-2.1", ">=2.1.0,<2.2.0", extends="agentskills/agent-skills@1.0"
    )

    with pytest.raises(SpecNotFound) as error:
        base_specs(load(path), tmp_path, today=TODAY)

    message = str(error.value)
    assert "agentskills/agent-skills@1.0" in message
    assert "anthropic/claude-code" in message, "and who asked for it"
