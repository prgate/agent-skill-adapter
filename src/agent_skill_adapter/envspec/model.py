"""The shape of an environment description.

Field names here describe the description itself, never a particular environment:
what an environment calls its own fields lives in the YAML data, not in this package.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_COMPARISON = r"(>=|<=|==|!=|>|<)\d+(\.\d+)*"
_VERSION_RANGE = re.compile(rf"\s*{_COMPARISON}\s*(,\s*{_COMPARISON}\s*)*")

REFERENCE = r"^[^/@\s]+/[^/@\s]+@\d+(\.\d+)*$"
"""How one description names another: ``<vendor>/<environment>@<version>``.

The version is dotted numbers, the same form :func:`loader.select` is asked for, so a
reference that the schema accepts is a reference the loader can go and resolve.
"""


class Support(str, Enum):
    """What the environment documentation says about a capability."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class DiscrepancyKind(str, Enum):
    """Why a source no longer confirms its entry. Both kinds come from a freshness run."""

    CHANGED = "changed"
    UNREACHABLE = "unreachable"


class _Strict(BaseModel):
    """An unknown field is a schema error, not a shrug."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _Identified(_Strict):
    id: str = Field(min_length=1)


class _Sourced(_Strict):
    source_id: str = Field(min_length=1)


class _Entry(_Identified, _Sourced):
    """An entry that carries its own id and names the source it is taken from."""


class Source(_Identified):
    """A documentation section an entry is taken from."""

    url: str = Field(min_length=1)
    markdown_url: str | None = None
    anchor: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checked_at: date
    environment_version: str = Field(min_length=1)
    retrieved_from: Literal["web", "shipped"] = "web"
    """Where the section was read: a public page, or a file the environment ships.

    A shipped section is documentation all the same, but there is no page to re-read, so
    the freshness run skips it rather than reaching for a URL that answers to nobody.
    """


class Capability(_Entry):
    """One documented property of the environment."""

    kind: Literal["skill-field", "subagent-field", "hook-event", "hook-decision", "settings-file"]
    """What the entry is about.

    ``hook-event`` is that the environment fires an event; ``hook-decision`` is what a hook
    of it may decide -- to stop what is about to happen, say. Two kinds because they are two
    claims: an environment can fire an event it lets no hook veto. Why the pair is split
    here rather than handled in the converter is ADR-0007.
    """

    support: Support
    values: list[str] | None = None
    """The closed set of values the documentation names for this field, in its own wording.

    Absent means the documentation names no set, never that any value will do: without a
    set there is nothing to translate a value onto, and the entry stays undecided. A set
    invented from what one asset happens to contain would be a rule read off an
    observation, which is exactly what a description is here to replace.
    """

    since_version: str | None = None
    note: str | None = None


class LayoutEntry(_Entry):
    """Where the environment keeps a kind of its files."""

    path: str = Field(min_length=1)


class Limit(_Entry):
    """A documented size limit, with the unit it is measured in."""

    value: int = Field(ge=0)
    unit: Literal["bytes", "characters", "tokens"]


class InvisibleSource(_Entry):
    """A configuration source the adapter cannot see."""

    path: str = Field(min_length=1)


class Discrepancy(_Sourced):
    """A source that no longer confirms its entry."""

    kind: DiscrepancyKind
    detail: str | None = None


def _unique_ids(entries: Sequence[_Identified], where: str) -> set[str]:
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            raise ValueError(f"duplicate id {entry.id!r} in {where}")
        seen.add(entry.id)
    return seen


class EnvSpec(_Strict):
    """One environment description, valid for one range of environment versions."""

    schema_version: int = Field(ge=1)
    vendor: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    version_range: str = Field(min_length=1)
    extends: str | None = Field(default=None, pattern=REFERENCE)
    """The description this one is a layer over, such as ``agentskills/agent-skills@1.0``.

    Absent is the normal case: a description that extends nothing stands on its own.
    Present, it says that every entry of the named description is part of this
    environment too, so an entry can be told apart from this environment's own additions.
    """

    checked_at: date
    stale_after_days: int = Field(default=30, ge=0)
    normalization: Literal["v1"]
    sources: list[Source]
    capabilities: list[Capability] = Field(default_factory=list)
    layout: list[LayoutEntry] = Field(default_factory=list)
    limits: list[Limit] = Field(default_factory=list)
    invisible_sources: list[InvisibleSource] = Field(default_factory=list)
    discrepancies: list[Discrepancy] = Field(default_factory=list)

    @field_validator("version_range")
    @classmethod
    def _check_version_range(cls, value: str) -> str:
        """A range is comma-separated comparisons of dotted numeric versions."""
        if _VERSION_RANGE.fullmatch(value) is None:
            raise ValueError(f"{value!r} is not a version range, such as '>=2.1.0,<2.2.0'")
        return value

    @model_validator(mode="after")
    def _check_ids_and_references(self) -> EnvSpec:
        """Ids are unique within their list, and every ``source_id`` names a declared source."""
        known = _unique_ids(self.sources, "sources")
        identified: list[tuple[str, Sequence[_Entry]]] = [
            ("capabilities", self.capabilities),
            ("layout", self.layout),
            ("limits", self.limits),
            ("invisible_sources", self.invisible_sources),
        ]
        for where, entries in identified:
            _unique_ids(entries, where)

        sourced: list[tuple[str, Sequence[_Sourced]]] = [
            *identified,
            ("discrepancies", self.discrepancies),
        ]
        for where, records in sourced:
            for record in records:
                if record.source_id not in known:
                    raise ValueError(f"{where}: source_id {record.source_id!r} has no such source")
        return self
