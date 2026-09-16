"""Translation rules: what we decided to do about what the descriptions state.

A description says what an environment documents; these rules say how one environment's
values are spelled in another's vocabulary, what never travels, and what may be rewritten.
The two answer different questions and move at different times, so the rules carry their
own version and live in their own file.

The module knows entry ids and path patterns, never the names of any particular asset set:
every name it matches on comes out of the file it was given.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

TOOL_NAMES_ENTRY = "subagent.frontmatter.tools"
"""The description entry whose value is a tool name.

A tool name is a field with a closed value set, like a model tier, and translates through
the same table; :meth:`Rules.tool_name` is the spelling of that one lookup.
"""


class InvalidRules(ValueError):
    """Raised when a rules file does not satisfy the schema."""


class _Strict(BaseModel):
    """An unknown field is a schema error, not a shrug."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Rewrite(_Strict):
    """Which files link substitution may rewrite. ``exclude`` wins over ``include``."""

    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class Undocumented(_Strict):
    """The one rule for a file no description declares, and the reason to print for it."""

    action: Literal["copy", "skip"]
    note: str = Field(min_length=1)


class Rules(_Strict):
    """One rules file, already checked."""

    version: str = Field(alias="rules_version", min_length=1)
    value_maps: dict[str, dict[str, str]] = Field(default_factory=dict)
    ignore: list[str] = Field(default_factory=list)
    rewrite: Rewrite = Field(default_factory=Rewrite)
    undocumented: Undocumented

    def value_of(self, entry_id: str, value: str) -> str | None:
        """The target spelling of ``value`` for description entry ``entry_id``.

        ``None`` means the rules name no counterpart — which is an answer worth reporting,
        never a licence to pass the source spelling through as if it had been translated.
        """
        return self.value_maps.get(entry_id, {}).get(value)

    def tool_name(self, name: str) -> str | None:
        """The target's spelling of tool ``name``, or ``None`` when the rules name no pair."""
        return self.value_of(TOOL_NAMES_ENTRY, name)

    def ignored(self, rel: str | PurePosixPath) -> bool:
        """Whether ``rel`` sits under, or is, something the rules keep out of the transfer.

        Matched part by part, so naming a directory covers everything below it.
        """
        return any(
            fnmatch(part, pattern) for part in PurePosixPath(rel).parts for pattern in self.ignore
        )

    def rewritable(self, rel: str | PurePosixPath) -> bool:
        """Whether link substitution may touch ``rel``."""
        path = PurePosixPath(rel)
        if any(path.match(pattern) for pattern in self.rewrite.exclude):
            return False
        return any(path.match(pattern) for pattern in self.rewrite.include)


def load(path: str | Path) -> Rules:
    """Read the YAML rules at ``path`` and return them as :class:`Rules`."""
    file = Path(path)
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise InvalidRules(f"{file}: not valid YAML: {error}") from error
    if not isinstance(raw, dict):
        raise InvalidRules(f"{file}: expected a mapping at the top level, got {type(raw).__name__}")
    try:
        return Rules.model_validate(raw)
    except ValidationError as error:
        raise InvalidRules(f"{file}: {error}") from error
