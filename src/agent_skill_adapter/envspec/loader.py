"""Reading environment descriptions: schema check, selection by version, staleness."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from agent_skill_adapter.envspec.model import EnvSpec, Support


class InvalidSpec(ValueError):
    """Raised when a spec file does not satisfy the schema."""


class InvalidVersion(ValueError):
    """Raised when the version asked for is not a dotted numeric version."""


class SpecNotFound(ValueError):
    """Raised when no description covers the requested environment version."""


class AmbiguousSpec(ValueError):
    """Raised when more than one description covers the requested environment version."""


class StaleSpec(ValueError):
    """Raised when the selected description is stale and staleness was not waived."""


def load(path: str | Path) -> EnvSpec:
    """Read the YAML spec at ``path`` and return it as an :class:`EnvSpec`."""
    file = Path(path)
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise InvalidSpec(f"{file}: not valid YAML: {error}") from error
    if not isinstance(raw, dict):
        raise InvalidSpec(f"{file}: expected a mapping at the top level, got {type(raw).__name__}")
    try:
        return EnvSpec.model_validate(raw)
    except ValidationError as error:
        raise InvalidSpec(f"{file}: {error}") from error


def _read_tree(root: str | Path) -> list[tuple[Path, EnvSpec]]:
    """Every description under ``root``, in a stable order, paired with its file."""
    base = Path(root)
    files = sorted(p for p in base.rglob("*.yaml") if p.is_file())
    return [(path, load(path)) for path in files]


def load_all(root: str | Path) -> list[EnvSpec]:
    """Read every description under ``root``. A file that fails the schema fails the load."""
    return [spec for _, spec in _read_tree(root)]


# Versions are dotted numbers: the two environments we describe use nothing else.
# ponytail: no pre-release or build metadata; add a real parser when a vendor ships one.
_VERSION = re.compile(r"^\d+(\.\d+)*$")
_CONSTRAINT = re.compile(r"^(>=|<=|==|!=|>|<)\s*(\S+)$")


def _version(text: str) -> tuple[int, ...]:
    stripped = text.strip()
    if not _VERSION.match(stripped):
        raise ValueError(f"{text!r} is not a dotted numeric version")
    return tuple(int(part) for part in stripped.split("."))


def _padded(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[list[int], list[int]]:
    """``2.1`` and ``2.1.0`` name the same version, so compare over a common length."""
    width = max(len(left), len(right))
    pad = [0] * width
    return (list(left) + pad)[:width], (list(right) + pad)[:width]


def _satisfies(version: tuple[int, ...], constraint: str) -> bool:
    match = _CONSTRAINT.match(constraint.strip())
    if match is None:
        raise ValueError(f"{constraint!r} is not a version constraint")
    operator, bound = match.group(1), _version(match.group(2))
    left, right = _padded(version, bound)
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    if operator == "==":
        return left == right
    return left != right


def _covers(version_range: str, version: tuple[int, ...]) -> bool:
    """``version_range`` is a comma-separated list of constraints; all of them must hold."""
    constraints = [part for part in version_range.split(",") if part.strip()]
    if not constraints:
        raise ValueError(f"{version_range!r} declares no constraint")
    return all(_satisfies(version, constraint) for constraint in constraints)


def is_stale(spec: EnvSpec, today: date) -> bool:
    """A description is stale once a discrepancy is recorded, or once its check is too old.

    The second half needs no network and no freshness run: it reads ``checked_at`` only.
    """
    if spec.discrepancies:
        return True
    return (today - spec.checked_at).days > spec.stale_after_days


def capability(spec: EnvSpec, capability_id: str) -> Support:
    """What ``spec`` says about ``capability_id``. No entry means unknown, never unsupported."""
    for entry in spec.capabilities:
        if entry.id == capability_id:
            return entry.support
    return Support.UNKNOWN


def select(
    root: str | Path,
    vendor: str,
    environment: str,
    version: str,
    *,
    allow_stale: bool = False,
    today: date | None = None,
) -> EnvSpec:
    """Return the single description under ``root`` that covers ``version``.

    No candidate raises :class:`SpecNotFound` — the nearest description is never
    substituted. More than one raises :class:`AmbiguousSpec` and names every candidate:
    the rule for choosing between them is not declared yet. A stale winner raises
    :class:`StaleSpec` unless ``allow_stale`` is set, which exists so an earlier
    transfer can be reproduced and permits nothing else. A ``version`` that is not a
    dotted number raises :class:`InvalidVersion`.
    """
    try:
        wanted = _version(version)
    except ValueError as error:
        raise InvalidVersion(
            f"cannot ask for version {version!r}: {error}. "
            "A version is dotted numbers, such as '2.1.270'"
        ) from error
    declared: list[str] = []
    matches: list[tuple[Path, EnvSpec]] = []
    for path, spec in _read_tree(root):
        if spec.vendor != vendor or spec.environment != environment:
            continue
        declared.append(spec.version_range)
        # The form of version_range is checked by the schema, so load() has already
        # refused anything _covers could choke on.
        if _covers(spec.version_range, wanted):
            matches.append((path, spec))

    if not matches:
        ranges = ", ".join(declared) if declared else "none"
        raise SpecNotFound(
            f"no description of {vendor}/{environment} covers version {version}; "
            f"declared ranges: {ranges}"
        )
    if len(matches) > 1:
        candidates = ", ".join(str(path) for path, _ in matches)
        raise AmbiguousSpec(
            f"{len(matches)} descriptions of {vendor}/{environment} cover version {version}: "
            f"{candidates}"
        )

    path, spec = matches[0]
    if not allow_stale and is_stale(spec, today or date.today()):
        raise StaleSpec(
            f"{path}: description is stale (checked_at {spec.checked_at}, "
            f"stale_after_days {spec.stale_after_days}, "
            f"discrepancies {len(spec.discrepancies)})"
        )
    return spec
