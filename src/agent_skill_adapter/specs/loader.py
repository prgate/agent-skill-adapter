"""Reading, selecting and serializing environment spec manifests."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agent_skill_adapter.specs.models import (
    BASELINE_ROLE,
    MANIFEST_REGISTRY,
    Manifest,
    Provenance,
)

_OPERATORS = (">=", "<=", "==", ">", "<")
_ANY_VERSION = "*"


class SpecError(Exception):
    """Base class for every spec failure."""


class SpecLoadError(SpecError):
    """A manifest exists but does not conform to the format."""

    def __init__(self, path: Path, loc: str, reason: str) -> None:
        super().__init__(f"{path}: {loc}: {reason}")
        self.path = path
        self.loc = loc
        self.reason = reason


class UnsupportedManifestError(SpecError):
    """The (apiVersion, kind) pair has no model."""

    def __init__(self, path: Path, api_version: str, kind: str) -> None:
        super().__init__(f"{path}: unsupported manifest ({api_version}, {kind})")
        self.path = path
        self.api_version = api_version
        self.kind = kind


class InsufficientDataError(SpecError):
    """No spec can answer the question asked; maps to exit code 3."""


class NoMatchingSpecError(InsufficientDataError):
    """No published document covers the requested environment version."""


class AmbiguousSpecError(InsufficientDataError):
    """More than one document covers the requested version and none was pinned."""


class StaleSpecError(InsufficientDataError):
    """The selected document is past its validity window or carries drift."""


def _format_loc(loc: tuple[int | str, ...]) -> str:
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}" if parts else str(item))
    return "".join(parts)


def _specs_dir(path: Path) -> Path:
    """specs/<environment>/<version>/spec.yaml -> specs/."""
    return path.parent.parent.parent


def _parse_extends(value: str) -> tuple[str, str]:
    name, separator, version = value.partition("@")
    if not separator or not name or not version:
        raise ValueError("extends must be '<name>@<version>'")
    for part in (name, version):
        if Path(part).is_absolute() or part in {".", ".."} or "/" in part or "\\" in part:
            raise ValueError(f"extends name/version must not be a path: {value!r}")
    return name, version


def _read(path: Path) -> dict[str, Any]:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SpecLoadError(path, "<root>", "manifest must be a mapping")
    return raw


def _validate(path: Path, raw: dict[str, Any]) -> Manifest:
    api_version = str(raw.get("apiVersion", ""))
    kind = str(raw.get("kind", ""))
    model = MANIFEST_REGISTRY.get((api_version, kind))
    if model is None:
        raise UnsupportedManifestError(path, api_version, kind)
    try:
        manifest = model.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        raise SpecLoadError(path, _format_loc(first["loc"]), first["msg"]) from error
    if manifest.metadata.version != path.parent.name:
        raise SpecLoadError(
            path,
            "metadata.version",
            f"{manifest.metadata.version!r} does not match directory {path.parent.name!r}",
        )
    return manifest


def load_manifest(path: Path) -> Manifest:
    """Load one manifest, refusing unknown kinds, malformed records and a bad `extends`."""
    manifest = _validate(path, _read(path))
    if manifest.spec.extends is not None:
        if manifest.metadata.labels.get("role") == BASELINE_ROLE:
            raise SpecLoadError(path, "spec.extends", "a baseline spec must not extend another")
        resolve_baseline(manifest, _specs_dir(path), _source=path)
    return manifest


def resolve_baseline(
    manifest: Manifest, specs_dir: Path, *, _source: Path | None = None
) -> Manifest | None:
    """Load the baseline named by `spec.extends`, or None when the spec extends nothing."""
    if manifest.spec.extends is None:
        return None
    source = _source if _source is not None else specs_dir
    try:
        name, version = _parse_extends(manifest.spec.extends)
    except ValueError as error:
        raise SpecLoadError(source, "spec.extends", str(error)) from error
    target = specs_dir / name / version / "spec.yaml"
    if not target.is_file():
        raise SpecLoadError(source, "spec.extends", f"{target} does not exist")
    baseline = _validate(target, _read(target))
    if baseline.metadata.labels.get("role") != BASELINE_ROLE:
        raise SpecLoadError(
            source, "spec.extends", f"{manifest.spec.extends} is not labelled role: baseline"
        )
    return baseline


def portable_fields(manifest: Manifest, baseline: Manifest) -> frozenset[str]:
    """Names of `skillFields` present in both: the derived `portable` flag of design D8.

    Every other field is raw material for the FR-48 gap list.
    """
    baseline_names = {record.name for record in baseline.spec.skill_fields}
    return frozenset(
        record.name for record in manifest.spec.skill_fields if record.name in baseline_names
    )


def _parse_version(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as error:
        raise SpecError(f"not a dotted-integer version: {value!r}") from error


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


def version_matches(version: str, ranges: str) -> bool:
    """True when version satisfies every comma-separated clause; `*` matches everything."""
    if ranges.strip() == _ANY_VERSION:
        return True
    target = _parse_version(version)
    for clause in (part.strip() for part in ranges.split(",") if part.strip()):
        for operator in _OPERATORS:
            if clause.startswith(operator):
                bound = _parse_version(clause[len(operator) :].strip())
                break
        else:
            raise SpecError(f"unsupported version clause: {clause!r}")
        order = _compare(target, bound)
        satisfied = {
            ">=": order >= 0,
            "<=": order <= 0,
            "==": order == 0,
            ">": order > 0,
            "<": order < 0,
        }[operator]
        if not satisfied:
            return False
    return True


def _iter_provenance(manifest: Manifest) -> list[Provenance]:
    spec = manifest.spec
    records: list[Provenance] = []
    for group in (spec.skill_fields, spec.agent_fields, spec.hooks):
        records.extend(record.provenance for record in group)
    records.extend(record.provenance for record in spec.tools)
    records.extend(record.provenance for record in spec.limits)
    records.extend(record.provenance for record in spec.invisible_sources)
    if spec.frontmatter is not None:
        records.append(spec.frontmatter.provenance)
    if spec.layout is not None:
        records.append(spec.layout.provenance)
    return records


def _is_stale(manifest: Manifest, today: date) -> bool:
    """Stale by `status.stale`, or by the oldest evidence plus `validForDays`."""
    if manifest.status.stale:
        return True
    reference = manifest.status.verified_at
    if reference is None:
        checked = [p.checked_at for p in _iter_provenance(manifest) if p.checked_at is not None]
        if not checked:
            return True
        reference = min(checked)
    return reference + timedelta(days=manifest.spec.valid_for_days) < today


def select_spec(
    specs_dir: Path,
    environment: str,
    version: str,
    *,
    today: date,
    pinned: str | None = None,
) -> Manifest:
    """Pick the document covering an environment version, refusing stale data."""
    candidates = [
        load_manifest(path) for path in sorted(specs_dir.glob(f"{environment}/*/spec.yaml"))
    ]
    matching = [m for m in candidates if version_matches(version, m.spec.environment.versions)]
    if not matching:
        raise NoMatchingSpecError(f"no {environment} spec covers version {version} in {specs_dir}")
    if len(matching) > 1:
        versions = ", ".join(m.metadata.version for m in matching)
        if pinned is None:
            raise AmbiguousSpecError(
                f"{len(matching)} {environment} specs cover version {version}: {versions}"
            )
        matching = [m for m in matching if m.metadata.version == pinned]
        if not matching:
            raise NoMatchingSpecError(
                f"pinned {environment} spec {pinned} does not cover version {version}"
            )
    selected = matching[0]
    if _is_stale(selected, today):
        raise StaleSpecError(
            f"{environment} spec {selected.metadata.version} is stale as of {today}"
        )
    return selected


_NAMED_LISTS = ("skillFields", "agentFields", "hooks", "tools", "limits")


def dump_manifest(manifest: Manifest) -> str:
    """Serialize canonically: model key order, named lists sorted by name (FR-29)."""
    data: dict[str, Any] = manifest.model_dump(mode="python", by_alias=True, exclude_none=True)
    spec: dict[str, Any] = data["spec"]
    for key in _NAMED_LISTS:
        if key in spec:
            spec[key] = sorted(spec[key], key=lambda record: str(record["name"]))
    if "invisibleSources" in spec:
        spec["invisibleSources"] = sorted(
            spec["invisibleSources"], key=lambda record: str(record["path"])
        )
    text: str = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )
    return text


def _pinned_content(file_path: Path) -> bytes:
    """The bytes a published directory pins for one file.

    `spec.yaml` mixes human-authored content with `status`, which the
    provenance script rewrites on every `verify` run (design section 4: `spec`
    is desired state, `status` is observed state). Pinning `status` would make
    FR-5 immutability and FR-7/FR-8 verification mutually exclusive, so only
    `apiVersion`/`kind`/`metadata`/`spec` are pinned; the file bytes stand in
    for every other file, which the format does not give a machine-written part.
    """
    if file_path.name != "spec.yaml":
        return file_path.read_bytes()
    raw = _read(file_path)
    pinned = {key: raw[key] for key in ("apiVersion", "kind", "metadata", "spec") if key in raw}
    return json.dumps(pinned, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def directory_hash(path: Path) -> str:
    """Hash a published version directory: sorted relative paths and pinned content.

    Symlinks are never dereferenced (FR-14): `p.is_file()` alone follows them,
    so a committed symlink could pull bytes from outside the directory the
    hash claims to pin.
    """
    digest = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink()):
        relative = file_path.relative_to(path).as_posix().encode("utf-8")
        content = _pinned_content(file_path)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"
