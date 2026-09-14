"""Reading environment descriptions: schema check, selection by version, staleness."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Literal

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


class ExtendsCycle(ValueError):
    """Raised when descriptions extend one another in a loop."""


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
    A check dated after today is stale as well: it is either a typo in the file or a clock
    that drifted, and under both the entries are unverifiable, so we refuse rather than pass.
    """
    if spec.discrepancies:
        return True
    age = (today - spec.checked_at).days
    return age < 0 or age > spec.stale_after_days


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


def base_specs(
    spec: EnvSpec,
    root: str | Path,
    *,
    allow_stale: bool = False,
    today: date | None = None,
) -> tuple[EnvSpec, ...]:
    """The descriptions ``spec`` extends, nearest first; empty when it extends nothing.

    The whole chain, not one step: a description that is a layer over an open specification
    may itself be layered over, and an entry of the furthest description is inherited just
    the same. Resolution is :func:`select` on the ``<vendor>/<environment>@<version>``
    reference, so its refusals stand -- a reference no description covers raises
    :class:`SpecNotFound`, and a stale base raises :class:`StaleSpec` unless waived.
    A chain that comes back to a reference already followed raises :class:`ExtendsCycle`
    rather than walking forever.
    """
    chain: list[EnvSpec] = []
    followed: list[str] = []
    current = spec
    while current.extends is not None:
        reference = current.extends
        holder = f"{current.vendor}/{current.environment}"
        if reference in followed:
            raise ExtendsCycle(
                f"{spec.vendor}/{spec.environment} extends itself through "
                f"{' -> '.join([*followed, reference])}"
            )
        followed.append(reference)
        # The form of the reference is checked by the schema, so the split cannot surprise us.
        vendor_environment, _, version = reference.partition("@")
        vendor, _, environment = vendor_environment.partition("/")
        try:
            current = select(
                root, vendor, environment, version, allow_stale=allow_stale, today=today
            )
        except SpecNotFound as error:
            raise SpecNotFound(f"{holder} extends {reference!r}: {error}") from error
        chain.append(current)
    return tuple(chain)


Entries = Literal["capabilities", "layout"]
"""Which list of a description an entry sits in. Ids are unique inside one list, not across."""


def is_inherited(bases: Sequence[EnvSpec], entry_id: str, *, among: Entries) -> bool:
    """Whether ``among`` of one of ``bases`` declares ``entry_id``.

    True means the entry belongs to the specification the environment is a layer over, so
    every other implementation of that specification is expected to carry it; false means
    the entry is that environment's own extension, which nobody else ever promised. The two
    are different news about a target environment that says nothing about the entry, and
    without this the report cannot tell them apart.

    ``among`` is required because a description's ids are unique per list and nothing stops
    the same name from naming a capability in one list and a place in the other. A layout
    entry is inherited from the base's ``layout`` alone, a capability from its
    ``capabilities`` alone: a format that declares a *field* called ``skill.body.content``
    has said nothing about a *directory* of that name, and one shared id space would report
    it as though it had.
    """
    return any(
        entry_id
        in {entry.id for entry in (base.capabilities if among == "capabilities" else base.layout)}
        for base in bases
    )
