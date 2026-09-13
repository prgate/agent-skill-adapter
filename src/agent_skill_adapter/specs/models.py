"""Pydantic models for environment spec manifests.

The models are the source of truth for the manifest format; the JSON Schema in
``specs/schema/`` is generated from them. Portability is not a field here: it is
derived from the baseline named by ``spec.extends`` (design D8).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

API_VERSION = "adapter.prgate.io/v1alpha1"
KIND = "EnvironmentSpec"
BASELINE_ROLE = "baseline"

Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
FieldKind = Literal["string", "bool", "int", "enum", "list[string]", "map"]
Unit = Literal["bytes", "chars", "tokens", "lines"]
Enforcement = Literal["hard", "recommended"]
Stability = Literal["stable", "experimental"]
UnknownFieldPolicy = Literal["reject", "warn", "ignore"]
DirScope = Literal["project", "user", "enterprise"]


class _Base(BaseModel):
    """Shared configuration: camelCase aliases, no unknown keys, immutable."""

    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class Provenance(_Base):
    """Where a record was read from, and the hash of that section's text."""

    url: str
    anchor: str | None = None
    selector: str | None = None
    hash: Sha256 | None = None
    checked_at: date | None = None

    @model_validator(mode="after")
    def _exactly_one_address(self) -> Provenance:
        if (self.anchor is None) == (self.selector is None):
            raise ValueError("exactly one of anchor or selector must be set")
        return self


class FieldConstraints(_Base):
    """Only what the source documentation states about a field's value."""

    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    matches_directory_name: bool = False


class FieldRecord(_Base):
    """One frontmatter key the environment understands."""

    name: str
    kind: FieldKind
    values: list[str] = Field(default_factory=list)
    value_kind: FieldKind | None = None
    open_keys: bool | None = None
    required: bool = False
    constraints: FieldConstraints | None = None
    stability: Stability = "stable"
    since: str | None = None
    effect: str
    provenance: Provenance

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> FieldRecord:
        if self.kind == "enum" and not self.values:
            raise ValueError("kind 'enum' requires a non-empty values list")
        if self.kind != "enum" and self.values:
            raise ValueError(f"kind {self.kind!r} must not carry values")
        if self.kind == "map" and self.value_kind is None:
            raise ValueError("kind 'map' requires valueKind")
        if self.kind != "map" and (self.value_kind is not None or self.open_keys is not None):
            raise ValueError(f"kind {self.kind!r} must not carry valueKind or openKeys")
        return self


class ToolRecord(_Base):
    """One tool name the environment documents."""

    name: str
    provenance: Provenance


class LimitRecord(_Base):
    """One documented size limit, with an explicit unit and how hard it is."""

    name: str
    value: int
    unit: Unit
    enforcement: Enforcement
    provenance: Provenance


class InvisibleSource(_Base):
    """Configuration the environment reads from outside the repository."""

    path: str
    reason: str
    provenance: Provenance


class FrontmatterPolicy(_Base):
    """What the environment does with a frontmatter key it does not know."""

    unknown_fields: UnknownFieldPolicy
    provenance: Provenance


class SkillsDir(_Base):
    """One directory the environment scans for skills."""

    path: str
    scope: DirScope


class Layout(_Base):
    """Where skills live on disk (FR-13)."""

    skill_file: list[str]
    skills_dirs: list[SkillsDir] = Field(default_factory=list)
    conventional_dirs: list[str] = Field(default_factory=list)
    provenance: Provenance


class EnvironmentRef(_Base):
    """The environment version range this document describes."""

    versions: str


class EnvironmentSpec(_Base):
    """Desired state: the human-authored content of the document."""

    extends: str | None = None
    environment: EnvironmentRef
    valid_for_days: int
    frontmatter: FrontmatterPolicy | None = None
    layout: Layout | None = None
    skill_fields: list[FieldRecord] = Field(default_factory=list)
    agent_fields: list[FieldRecord] = Field(default_factory=list)
    hooks: list[FieldRecord] = Field(default_factory=list)
    tools: list[ToolRecord] = Field(default_factory=list)
    limits: list[LimitRecord] = Field(default_factory=list)
    invisible_sources: list[InvisibleSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _names_are_unique(self) -> EnvironmentSpec:
        for attr in ("skill_fields", "agent_fields", "hooks", "tools", "limits"):
            names = [record.name for record in getattr(self, attr)]
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                raise ValueError(f"duplicate name(s) in {attr}: {', '.join(duplicates)}")
        paths = [source.path for source in self.invisible_sources]
        duplicates = sorted({path for path in paths if paths.count(path) > 1})
        if duplicates:
            raise ValueError(f"duplicate path(s) in invisible_sources: {', '.join(duplicates)}")
        return self


class DriftEntry(_Base):
    """One record whose source section no longer matches its recorded hash."""

    record: str
    expected: str | None = None
    actual: str | None = None
    reason: str


class Status(_Base):
    """Observed state: written only by the provenance script."""

    verified_at: date | None = None
    stale: bool = False
    drift: list[DriftEntry] = Field(default_factory=list)


class Metadata(_Base):
    """Manifest identity. `labels.role` is one of baseline | source | target | both."""

    name: str
    version: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class Manifest(_Base):
    """The manifest envelope."""

    api_version: Literal["adapter.prgate.io/v1alpha1"]
    kind: Literal["EnvironmentSpec"]
    metadata: Metadata
    spec: EnvironmentSpec
    status: Status = Status()


MANIFEST_REGISTRY: dict[tuple[str, str], type[Manifest]] = {(API_VERSION, KIND): Manifest}


def json_schema_text() -> str:
    """Return the committed form of the manifest JSON Schema."""
    schema: dict[str, Any] = Manifest.model_json_schema(by_alias=True)
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
