"""Unit tests for the environment spec models and loader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agent_skill_adapter.specs.loader import (
    AmbiguousSpecError,
    NoMatchingSpecError,
    SpecLoadError,
    StaleSpecError,
    UnsupportedManifestError,
    dump_manifest,
    load_manifest,
    portable_fields,
    resolve_baseline,
    select_spec,
    version_matches,
)
from agent_skill_adapter.specs.models import json_schema_text

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "specs"

BASELINE = """\
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: agentskills
  version: 1.0.0
  labels:
    role: baseline
spec:
  environment:
    versions: "*"
  validForDays: 3650
  skillFields:
    - name: name
      kind: string
      required: true
      effect: Identifies the skill.
      provenance:
        url: https://agentskills.io/specification
        anchor: "#name-field"
status:
  verifiedAt: 2026-09-01
  stale: false
"""

DERIVED = """\
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: {environment}
  version: {version}
  labels:
    role: source
spec:
  extends: {extends}
  environment:
    versions: "{versions}"
  validForDays: {valid_for_days}
  skillFields:
    - name: name
      kind: string
      required: true
      effect: Identifies the skill.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
    - name: context
      kind: enum
      values: [fork]
      effect: Runs the skill in a forked context.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
status:
  verifiedAt: {verified_at}
  stale: {stale}
"""


def write_baseline(root: Path) -> Path:
    path = root / "agentskills" / "1.0.0" / "spec.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BASELINE, encoding="utf-8")
    return path


def write_spec(
    root: Path,
    environment: str = "claude-code",
    version: str = "1.0.0",
    versions: str = ">=2.1.200,<2.2.0",
    valid_for_days: int = 90,
    verified_at: str = "2026-09-01",
    stale: str = "false",
    extends: str = "agentskills@1.0.0",
) -> Path:
    """Write a minimal valid derived manifest; the baseline must already exist."""
    path = root / environment / version / "spec.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        DERIVED.format(
            environment=environment,
            version=version,
            versions=versions,
            valid_for_days=valid_for_days,
            verified_at=verified_at,
            stale=stale,
            extends=extends,
        ),
        encoding="utf-8",
    )
    return path


def test_unknown_kind_is_refused() -> None:
    with pytest.raises(UnsupportedManifestError) as excinfo:
        load_manifest(FIXTURES / "unknown_kind.yaml")
    assert "ContractSpec" in str(excinfo.value)


@pytest.mark.parametrize(
    ("fixture", "loc"),
    [
        ("unknown_key.yaml", "spec.skillFields[0]"),
        ("duplicate_name.yaml", "spec"),
        ("enum_without_values.yaml", "spec.skillFields[0]"),
        ("map_without_value_kind.yaml", "spec.skillFields[0]"),
        ("both_anchor_and_selector.yaml", "spec.tools[0].provenance"),
    ],
)
def test_broken_manifest_reports_record_path(fixture: str, loc: str) -> None:
    with pytest.raises(SpecLoadError) as excinfo:
        load_manifest(FIXTURES / fixture)
    assert loc in str(excinfo.value)


def test_version_must_equal_directory_name(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    path = write_spec(tmp_path, version="1.0.0")
    moved = tmp_path / "claude-code" / "1.0.1"
    moved.mkdir()
    path.rename(moved / "spec.yaml")
    with pytest.raises(SpecLoadError) as excinfo:
        load_manifest(moved / "spec.yaml")
    assert "metadata.version" in str(excinfo.value)


def test_extends_must_resolve(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    path = write_spec(tmp_path, extends="agentskills@9.9.9")
    with pytest.raises(SpecLoadError) as excinfo:
        load_manifest(path)
    assert "spec.extends" in str(excinfo.value)


def test_extends_target_must_be_a_baseline(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path, environment="other", version="1.0.0")
    path = write_spec(tmp_path, extends="other@1.0.0")
    with pytest.raises(SpecLoadError) as excinfo:
        load_manifest(path)
    assert "spec.extends" in str(excinfo.value)


def test_baseline_must_not_extend(tmp_path: Path) -> None:
    path = tmp_path / "agentskills" / "1.0.0" / "spec.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        BASELINE.replace(
            "spec:\n  environment:", "spec:\n  extends: agentskills@1.0.0\n  environment:"
        ),
        encoding="utf-8",
    )
    with pytest.raises(SpecLoadError) as excinfo:
        load_manifest(path)
    assert "spec.extends" in str(excinfo.value)


def test_portable_fields_is_derived_from_the_baseline(tmp_path: Path) -> None:
    """`name` exists in the baseline, `context` does not: that is the FR-48 gap list."""
    write_baseline(tmp_path)
    manifest = load_manifest(write_spec(tmp_path))
    baseline = resolve_baseline(manifest, tmp_path)
    assert baseline is not None
    assert portable_fields(manifest, baseline) == frozenset({"name"})


@pytest.mark.parametrize(
    ("version", "ranges", "expected"),
    [
        ("2.1.200", ">=2.1.200,<2.2.0", True),
        ("2.1.199", ">=2.1.200,<2.2.0", False),
        ("2.2.0", ">=2.1.200,<2.2.0", False),
        ("2.1.250", ">=2.1.200,<2.2.0", True),
        ("2.1", ">=2.1.0", True),
        ("2.1.0", "==2.1.0", True),
        ("2.1.0", "<=2.1.0", True),
        ("2.1.0", ">2.1.0", False),
        ("0.0.1", "*", True),
        ("99.99.99", "*", True),
    ],
)
def test_version_matches(version: str, ranges: str, expected: bool) -> None:
    assert version_matches(version, ranges) is expected


def test_select_spec_no_match(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path)
    with pytest.raises(NoMatchingSpecError):
        select_spec(tmp_path, "claude-code", "2.0.0", today=date(2026, 9, 13))


def test_select_spec_single_match(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path)
    manifest = select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))
    assert manifest.metadata.version == "1.0.0"


def test_select_spec_ambiguous_lists_candidates(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path, version="1.0.0")
    write_spec(tmp_path, version="1.0.1")
    with pytest.raises(AmbiguousSpecError) as excinfo:
        select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))
    assert "1.0.0" in str(excinfo.value)
    assert "1.0.1" in str(excinfo.value)


def test_select_spec_pinned_resolves_ambiguity(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path, version="1.0.0")
    write_spec(tmp_path, version="1.0.1")
    manifest = select_spec(
        tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13), pinned="1.0.1"
    )
    assert manifest.metadata.version == "1.0.1"


def test_select_spec_stale_by_date(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path, verified_at="2026-01-01", valid_for_days=90)
    with pytest.raises(StaleSpecError):
        select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))


def test_select_spec_stale_by_status(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path, verified_at="2026-09-12", stale="true")
    with pytest.raises(StaleSpecError):
        select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))


def test_pinned_does_not_lift_staleness(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    write_spec(tmp_path, version="1.0.0", verified_at="2026-01-01")
    write_spec(tmp_path, version="1.0.1", verified_at="2026-01-01")
    with pytest.raises(StaleSpecError):
        select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13), pinned="1.0.1")


def test_dump_manifest_round_trips(tmp_path: Path) -> None:
    write_baseline(tmp_path)
    path = write_spec(tmp_path)
    dumped = dump_manifest(load_manifest(path))
    path.write_text(dumped, encoding="utf-8")
    assert dump_manifest(load_manifest(path)) == dumped


def test_dump_manifest_sorts_named_lists(tmp_path: Path) -> None:
    """Canonical form orders `skillFields` by name: context before name (FR-29)."""
    write_baseline(tmp_path)
    path = write_spec(tmp_path)
    dumped = dump_manifest(load_manifest(path))
    assert dumped.index("name: context") < dumped.index("name: name")


def test_committed_schema_matches_models() -> None:
    committed = REPO_ROOT / "specs" / "schema" / "environmentspec.v1alpha1.json"
    assert committed.read_text(encoding="utf-8") == json_schema_text(), (
        "schema is out of date; run `make spec-schema`"
    )


SPECS = REPO_ROOT / "specs"
AGENTSKILLS_1_0_0 = SPECS / "agentskills" / "1.0.0" / "spec.yaml"


def test_published_baseline_loads() -> None:
    manifest = load_manifest(AGENTSKILLS_1_0_0)
    assert manifest.metadata.labels["role"] == "baseline"
    assert manifest.spec.extends is None
    assert manifest.spec.frontmatter is not None
    assert manifest.spec.layout is not None
    assert {r.name for r in manifest.spec.skill_fields} >= {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
    }


@pytest.mark.parametrize("spec_path", sorted(SPECS.glob("*/*/spec.yaml")))
def test_published_spec_is_canonically_serialized(spec_path: Path) -> None:
    """A hand edit that breaks canonical form fails here, not in a later diff."""
    assert dump_manifest(load_manifest(spec_path)) == spec_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("spec_path", sorted(SPECS.glob("*/*/spec.yaml")))
def test_published_records_carry_provenance_hashes(spec_path: Path) -> None:
    """An unverified record is not shippable (FR-2)."""
    spec = load_manifest(spec_path).spec
    provenances = (
        [(f.name, f.provenance) for f in spec.skill_fields]
        + [(t.name, t.provenance) for t in spec.tools]
        + [(limit.name, limit.provenance) for limit in spec.limits]
        + [(s.path, s.provenance) for s in spec.invisible_sources]
    )
    if spec.frontmatter is not None:
        provenances.append(("frontmatter", spec.frontmatter.provenance))
    if spec.layout is not None:
        provenances.append(("layout", spec.layout.provenance))
    missing = [name for name, provenance in provenances if provenance.hash is None]
    assert not missing, f"{spec_path}: records without a provenance hash: {missing}"


CLAUDE_CODE_1_0_0 = SPECS / "claude-code" / "1.0.0" / "spec.yaml"


def test_published_claude_code_spec_extends_the_baseline() -> None:
    manifest = load_manifest(CLAUDE_CODE_1_0_0)
    assert manifest.spec.extends == "agentskills@1.0.0"
    assert manifest.spec.tools, "1.0.0 must record tool names"


def test_published_portability_is_derived() -> None:
    """`name` is in the open spec, `context` is a Claude Code extension (FR-48)."""
    manifest = load_manifest(CLAUDE_CODE_1_0_0)
    baseline = resolve_baseline(manifest, SPECS)
    assert baseline is not None
    portable = portable_fields(manifest, baseline)
    assert "name" in portable
    assert "context" not in portable
    assert "hooks" not in portable
