# Environment Spec Format and Claude Code Spec 1.0.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a versioned, provenance-carrying environment spec format with a deterministic loader, and publish Claude Code spec 1.0.0 authored from the official documentation.

**Architecture:** Pydantic v2 models are the single source of truth for a Kubernetes-style manifest envelope (`apiVersion`/`kind`/`metadata`/`spec`/`status`). A loader reads YAML through `yaml.safe_load`, dispatches on `(apiVersion, kind)`, and selects a spec by environment version range and staleness. A stdlib-only script fetches documentation sections, hashes their normalized text, and writes results into `status`. The JSON Schema is generated from the models, and published version directories are pinned by content hash.

**Order:** the provider documentation is downloaded to a local snapshot **first**; every later task reads records from that snapshot rather than from a live page, so authoring is reproducible and the engine is built against material that already exists.

**Tech Stack:** Python 3.10+, Pydantic v2, PyYAML, pytest, mypy strict, ruff, uv, Make.

**Spec:** `docs/superpowers/specs/2026-09-13-environment-spec-format-design.md`

## Global Constraints

- No new runtime or dev dependencies. `pydantic>=2.0.0` and `pyyaml>=6.0.0` are already declared; `packaging` must **not** be added — the loader implements its own dotted-integer comparator.
- Repository artifacts (code, docstrings, comments, docs, commit messages, PR text) are 100% English.
- Conventional Commits, every commit body ends with `Refs #2`.
- Work happens in `.worktrees/issue2` on branch `feature/environment-spec-format`; PR #45.
- Manifest key case is camelCase (`alias_generator=to_camel`, `populate_by_name=True`); unknown keys are rejected (`extra="forbid"`); models are `frozen=True`.
- `apiVersion` is exactly `adapter.prgate.io/v1alpha1`; `kind` is exactly `EnvironmentSpec`.
- Tests never touch the network.
- Out of scope (do not implement): subagent fields, hooks records, `ContractRegistry`, CI drift step, FR-8 auto-PR, Markdown body parsing, drift significance threshold.
- `make check` (ruff check, ruff format --check, mypy strict on `src` and `tests`, pytest) must pass before the PR leaves draft.

## File Structure

| File | Responsibility |
|------|----------------|
| `.cache/claude-code-docs/<date>/` | Local snapshot of the official documentation (gitignored); the raw material every record is authored from |
| `.gitignore` | Ignores `.cache/` |
| `src/agent_skill_adapter/specs/__init__.py` | Public re-exports: models, loader functions, error types |
| `src/agent_skill_adapter/specs/models.py` | Pydantic models, validators, `MANIFEST_REGISTRY`, `json_schema_text()` |
| `src/agent_skill_adapter/specs/loader.py` | `load_manifest`, `select_spec`, `dump_manifest`, `directory_hash`, version comparator, error types |
| `scripts/spec_provenance.py` | `fill` / `verify` subcommands, HTML section extraction, hash normalization |
| `specs/schema/environmentspec.v1alpha1.json` | Generated JSON Schema (committed) |
| `specs/claude-code/1.0.0/spec.yaml` | Claude Code spec 1.0.0 content |
| `specs/claude-code/CHANGELOG.md` | Human-readable diff between document versions |
| `specs/claude-code/versions.lock` | sha256 of each published version directory |
| `tests/unit/test_specs.py` | Loader, model, selection, serialization, schema, lock tests |
| `tests/unit/test_spec_provenance.py` | Hash normalization tests (offline) |
| `tests/fixtures/specs/*.yaml` | One minimal broken manifest per load error |
| `Makefile` | `spec-schema` target |

---

## Open points resolved by this plan

The design leaves three details underspecified. This plan fixes them; they are
fills, not revisions:

1. **Staleness reference date.** Design §6 says "stale when `checkedAt + validForDays < today`", while §4 puts `verifiedAt` in `status`. Resolution: the reference date is `status.verifiedAt` when set, otherwise the **oldest** `provenance.checkedAt` across all records; when neither exists the spec is stale. Rationale: a spec the verification script never touched still ages from its weakest record.
2. **`limits` units.** Design §4 allows only `bytes | chars | tokens`. Documented Claude Code limits that carry no such unit (for example "up to 6 stacked skills") are therefore **not** recorded in 1.0.0.
3. **`versions.lock` regeneration.** No new Make target: `directory_hash()` lives in `loader.py`, the test uses it, and `versions.lock` carries the regeneration one-liner as a comment header.

---

### Task 1: Local snapshot of the official Claude Code documentation

Nothing is implemented before the source material exists on disk. This task
downloads the provider documentation once, checks that every anchor a record
will cite is really present in the rendered HTML, and leaves a manifest of what
was fetched and when. Every later task reads these files; only
`scripts/spec_provenance.py fill` and `verify` go to the network again, and
Task 5 proves their result matches this snapshot.

**Files:**
- Create: `.cache/claude-code-docs/2026-09-13/*.md` and `*.html` (gitignored)
- Create: `.cache/claude-code-docs/2026-09-13/sources.tsv` (gitignored)
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: a snapshot directory whose layout later tasks rely on —
  `<slug>.md` (readable source), `<slug>.html` (what the hash contract applies
  to), and `sources.tsv` with columns `slug`, `url`, `sha256_html`, `fetched_at`.

**Pages** (the complete set of sources spec 1.0.0 may cite):

| Slug | URL | What it supplies |
|------|-----|------------------|
| `skills` | `https://code.claude.com/docs/en/skills` | `skillFields`, skill `limits` |
| `tools-reference` | `https://code.claude.com/docs/en/tools-reference` | `tools` |
| `settings` | `https://code.claude.com/docs/en/settings` | `invisibleSources` — settings files |
| `memory` | `https://code.claude.com/docs/en/memory` | `invisibleSources` — `CLAUDE.md` |
| `managed-settings` | `https://code.claude.com/docs/en/managed-settings` | `invisibleSources` — enterprise policy |
| `claude-directory` | `https://code.claude.com/docs/en/claude-directory` | `invisibleSources` — what `~/.claude` holds |

Every page is fetched twice: `.md` is the readable source used for authoring,
`.html` is what the hash contract in Task 3 applies to. The two must come from
the same fetch, or a record can cite a section that the hash never saw.

- [ ] **Step 1: Ignore the snapshot directory**

Append to `.gitignore`:

```gitignore

# Local snapshot of provider documentation (raw material for specs/)
.cache/
```

- [ ] **Step 2: Download the snapshot**

Write `scratch_snapshot.py` in a scratch directory (not in the repository) with
this content and run it from the worktree root:

```python
import hashlib
import urllib.request
from datetime import date
from pathlib import Path

PAGES = {
    "skills": "https://code.claude.com/docs/en/skills",
    "tools-reference": "https://code.claude.com/docs/en/tools-reference",
    "settings": "https://code.claude.com/docs/en/settings",
    "memory": "https://code.claude.com/docs/en/memory",
    "managed-settings": "https://code.claude.com/docs/en/managed-settings",
    "claude-directory": "https://code.claude.com/docs/en/claude-directory",
}
today = date.today().isoformat()
root = Path(".cache/claude-code-docs") / today
root.mkdir(parents=True, exist_ok=True)
headers = {"User-Agent": "agent-skill-adapter-spec-provenance/1.0"}
rows = ["slug\turl\tsha256_html\tfetched_at"]
for slug, url in PAGES.items():
    digest = ""
    for suffix, source in ((".html", url), (".md", url + ".md")):
        request = urllib.request.Request(source, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
        (root / (slug + suffix)).write_bytes(body)
        if suffix == ".html":
            digest = hashlib.sha256(body).hexdigest()
        print(f"{slug}{suffix}: {len(body)} bytes")
    rows.append(f"{slug}\t{url}\tsha256:{digest}\t{today}")
(root / "sources.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
```

Expected: six `.html` and six `.md` files plus `sources.tsv`. A non-200 response
raises `urllib.error.HTTPError` — check the URL against
`https://code.claude.com/docs/llms.txt`, which lists every published page, and
re-run.

- [ ] **Step 3: Confirm the anchors exist in the rendered HTML**

The hash contract cuts a section out of the HTML by heading `id`, so an anchor
that exists only in the Markdown source is useless. List what is actually there:

```bash
SNAP=.cache/claude-code-docs/$(date +%F)
for f in "$SNAP"/*.html; do
  echo "== $f"
  grep -oE '<h[1-6][^>]*id="[^"]+"' "$f" | grep -oE 'id="[^"]+"' | sort -u
done
```

Expected: `skills.html` contains `id="frontmatter-reference"`; `settings.html`
contains `id="settings-files-and-who-they-affect"`. Write down the real heading
`id` above the tool table in `tools-reference.html` — it is the one anchor this
plan cannot name in advance.

If a page renders its headings only in the browser, its `id` values are absent
here. That page then needs `selector` rather than `anchor`, which
`scripts/spec_provenance.py` does not support (see "Known gaps accepted"): drop
the page from 1.0.0 and record the omission in `CHANGELOG.md` rather than ship a
record with no verifiable address.

- [ ] **Step 4: Extract the authoring material**

```bash
SNAP=.cache/claude-code-docs/$(date +%F)
sed -n '/^### Frontmatter reference/,/^### Add supporting files/p' "$SNAP/skills.md" \
  > "$SNAP/frontmatter-reference.md"
wc -l "$SNAP/frontmatter-reference.md"
grep -oE '^\| *`[A-Za-z]+`' "$SNAP/tools-reference.md" | tr -d '| `' | sort -u \
  > "$SNAP/tool-names.txt"
wc -l "$SNAP/tool-names.txt"
```

Read `frontmatter-reference.md` in full. It, not this plan and not memory, is
the list of keys Task 5 records; the same holds for `tool-names.txt`. If the
`sed` range comes back empty the headings have been renamed — find the real
section headings with `grep -nE '^#{2,4} ' "$SNAP/skills.md"` and redo the cut.

- [ ] **Step 5: Note what the snapshot says, in the plan's own terms**

Write a short `NOTES.md` next to the snapshot recording, for the authoring pass
in Task 5: the frontmatter keys found and their kinds, which keys the page marks
as Agent Skills spec fields (these become `portable: true`), every `since`
version the page states, every size limit with its unit, and the settings and
memory file paths. Nothing here is committed; it exists so Task 5 does not need
the network.

- [ ] **Step 6: Commit the ignore rule**

The snapshot itself is never committed — provenance hashes, not a vendored copy
of someone else's documentation, are what make a record auditable.

```bash
git add .gitignore
git commit -m "chore(specs): ignore the local provider documentation snapshot

Refs #2"
```

---

### Task 2: Models and loader

**Files:**
- Create: `src/agent_skill_adapter/specs/__init__.py`
- Create: `src/agent_skill_adapter/specs/models.py`
- Create: `src/agent_skill_adapter/specs/loader.py`
- Create: `tests/unit/test_specs.py`
- Create: `tests/fixtures/specs/unknown_kind.yaml`
- Create: `tests/fixtures/specs/unknown_key.yaml`
- Create: `tests/fixtures/specs/duplicate_name.yaml`
- Create: `tests/fixtures/specs/enum_without_values.yaml`
- Create: `tests/fixtures/specs/both_anchor_and_selector.yaml`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `agent_skill_adapter.specs.models`: `Manifest`, `Metadata`, `EnvironmentSpec`, `EnvironmentRef`, `FieldRecord`, `ToolRecord`, `LimitRecord`, `InvisibleSource`, `Provenance`, `Status`, `DriftEntry`, `MANIFEST_REGISTRY: dict[tuple[str, str], type[Manifest]]`, `json_schema_text() -> str`
  - `agent_skill_adapter.specs.loader`: `load_manifest(path: Path) -> Manifest`, `select_spec(specs_dir: Path, environment: str, version: str, *, today: date, pinned: str | None = None) -> Manifest`, `dump_manifest(manifest: Manifest) -> str`, `directory_hash(path: Path) -> str`, `version_matches(version: str, ranges: str) -> bool`
  - Errors: `SpecError`, `SpecLoadError(path, loc)`, `UnsupportedManifestError(path, api_version, kind)`, `InsufficientDataError`, `NoMatchingSpecError`, `AmbiguousSpecError`, `StaleSpecError`

- [ ] **Step 1: Write the failing tests**

Create `tests/fixtures/specs/unknown_kind.yaml`:

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: ContractSpec
metadata:
  name: demo
  version: 1.0.0
spec:
  environment:
    versions: ">=2.1.200,<2.2.0"
  validForDays: 90
```

Create `tests/fixtures/specs/unknown_key.yaml`:

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: demo
  version: 1.0.0
spec:
  environment:
    versions: ">=2.1.200,<2.2.0"
  validForDays: 90
  skillFields:
    - name: context
      kind: enum
      values: [fork]
      effect: Runs the skill in a forked context.
      sinсe: "2.1.100"
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
```

> The key on the `sinсe` line contains a Cyrillic `с`. That is deliberate: it is the typo the `extra="forbid"` rule must catch.

Create `tests/fixtures/specs/duplicate_name.yaml`:

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: demo
  version: 1.0.0
spec:
  environment:
    versions: ">=2.1.200,<2.2.0"
  validForDays: 90
  skillFields:
    - name: model
      kind: string
      effect: Model to use when this skill is active.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
    - name: model
      kind: string
      effect: Duplicate record.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
```

Create `tests/fixtures/specs/enum_without_values.yaml`:

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: demo
  version: 1.0.0
spec:
  environment:
    versions: ">=2.1.200,<2.2.0"
  validForDays: 90
  skillFields:
    - name: effort
      kind: enum
      effect: Effort level when this skill is active.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
```

Create `tests/fixtures/specs/both_anchor_and_selector.yaml`:

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: demo
  version: 1.0.0
spec:
  environment:
    versions: ">=2.1.200,<2.2.0"
  validForDays: 90
  tools:
    - name: Bash
      provenance:
        url: https://code.claude.com/docs/en/tools-reference
        anchor: "#bash-tool-behavior"
        selector: "main > table"
```

Create `tests/unit/test_specs.py`:

```python
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
    select_spec,
    version_matches,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "specs"

MINIMAL = """\
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: {environment}
  version: {version}
spec:
  environment:
    versions: "{versions}"
  validForDays: {valid_for_days}
status:
  verifiedAt: {verified_at}
  stale: {stale}
"""


def write_spec(
    root: Path,
    environment: str = "claude-code",
    version: str = "1.0.0",
    versions: str = ">=2.1.200,<2.2.0",
    valid_for_days: int = 90,
    verified_at: str = "2026-09-01",
    stale: str = "false",
) -> Path:
    """Write a minimal valid manifest into root/<environment>/<version>/spec.yaml."""
    path = root / environment / version / "spec.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        MINIMAL.format(
            environment=environment,
            version=version,
            versions=versions,
            valid_for_days=valid_for_days,
            verified_at=verified_at,
            stale=stale,
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
        ("duplicate_name.yaml", "spec.skillFields"),
        ("enum_without_values.yaml", "spec.skillFields[0]"),
        ("both_anchor_and_selector.yaml", "spec.tools[0].provenance"),
    ],
)
def test_broken_manifest_reports_record_path(fixture: str, loc: str) -> None:
    with pytest.raises(SpecLoadError) as excinfo:
        load_manifest(FIXTURES / fixture)
    assert loc in str(excinfo.value)


def test_version_must_equal_directory_name(tmp_path: Path) -> None:
    path = write_spec(tmp_path, version="1.0.0")
    moved = tmp_path / "claude-code" / "1.0.1"
    moved.mkdir()
    path.rename(moved / "spec.yaml")
    with pytest.raises(SpecLoadError) as excinfo:
        load_manifest(moved / "spec.yaml")
    assert "metadata.version" in str(excinfo.value)


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
    ],
)
def test_version_matches(version: str, ranges: str, expected: bool) -> None:
    assert version_matches(version, ranges) is expected


def test_select_spec_no_match(tmp_path: Path) -> None:
    write_spec(tmp_path)
    with pytest.raises(NoMatchingSpecError):
        select_spec(tmp_path, "claude-code", "2.0.0", today=date(2026, 9, 13))


def test_select_spec_single_match(tmp_path: Path) -> None:
    write_spec(tmp_path)
    manifest = select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))
    assert manifest.metadata.version == "1.0.0"


def test_select_spec_ambiguous_lists_candidates(tmp_path: Path) -> None:
    write_spec(tmp_path, version="1.0.0")
    write_spec(tmp_path, version="1.0.1")
    with pytest.raises(AmbiguousSpecError) as excinfo:
        select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))
    assert "1.0.0" in str(excinfo.value)
    assert "1.0.1" in str(excinfo.value)


def test_select_spec_pinned_resolves_ambiguity(tmp_path: Path) -> None:
    write_spec(tmp_path, version="1.0.0")
    write_spec(tmp_path, version="1.0.1")
    manifest = select_spec(
        tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13), pinned="1.0.1"
    )
    assert manifest.metadata.version == "1.0.1"


def test_select_spec_stale_by_date(tmp_path: Path) -> None:
    write_spec(tmp_path, verified_at="2026-01-01", valid_for_days=90)
    with pytest.raises(StaleSpecError):
        select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))


def test_select_spec_stale_by_status(tmp_path: Path) -> None:
    write_spec(tmp_path, verified_at="2026-09-12", stale="true")
    with pytest.raises(StaleSpecError):
        select_spec(tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13))


def test_pinned_does_not_lift_staleness(tmp_path: Path) -> None:
    write_spec(tmp_path, version="1.0.0", verified_at="2026-01-01")
    write_spec(tmp_path, version="1.0.1", verified_at="2026-01-01")
    with pytest.raises(StaleSpecError):
        select_spec(
            tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13), pinned="1.0.1"
        )


def test_dump_manifest_round_trips(tmp_path: Path) -> None:
    path = write_spec(tmp_path)
    dumped = dump_manifest(load_manifest(path))
    path.write_text(dumped, encoding="utf-8")
    assert dump_manifest(load_manifest(path)) == dumped


def test_dump_manifest_sorts_named_lists(tmp_path: Path) -> None:
    path = write_spec(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8")
        + """\
  tools:
    - name: Read
      provenance:
        url: https://code.claude.com/docs/en/tools-reference
        anchor: "#read"
    - name: Bash
      provenance:
        url: https://code.claude.com/docs/en/tools-reference
        anchor: "#bash"
""",
        encoding="utf-8",
    )
    dumped = dump_manifest(load_manifest(path))
    assert dumped.index("name: Bash") < dumped.index("name: Read")
```

> The `tools:` block appended in the last test must land inside `spec:`; `status:` is the final key of `MINIMAL`, so append the block only after moving `status` — write `MINIMAL` with `status` last and the appended lines at the same indent as `validForDays`. If the resulting YAML does not parse, restructure the test to build the file from a dedicated template string instead of appending.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_specs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_skill_adapter.specs'`

- [ ] **Step 3: Write `models.py`**

```python
"""Pydantic models for environment spec manifests.

The models are the source of truth for the manifest format; the JSON Schema in
``specs/schema/`` is generated from them.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

API_VERSION = "adapter.prgate.io/v1alpha1"
KIND = "EnvironmentSpec"

Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
FieldKind = Literal["string", "bool", "int", "enum", "list[string]", "map"]
Unit = Literal["bytes", "chars", "tokens"]


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


class FieldRecord(_Base):
    """One frontmatter key the environment understands."""

    name: str
    kind: FieldKind
    values: list[str] = Field(default_factory=list)
    required: bool = False
    since: str | None = None
    portable: bool = False
    effect: str
    provenance: Provenance

    @model_validator(mode="after")
    def _values_match_kind(self) -> FieldRecord:
        if self.kind == "enum" and not self.values:
            raise ValueError("kind 'enum' requires a non-empty values list")
        if self.kind != "enum" and self.values:
            raise ValueError(f"kind {self.kind!r} must not carry values")
        return self


class ToolRecord(_Base):
    """One tool name the environment documents."""

    name: str
    provenance: Provenance


class LimitRecord(_Base):
    """One documented size limit, with an explicit unit."""

    name: str
    value: int
    unit: Unit
    provenance: Provenance


class InvisibleSource(_Base):
    """Configuration the environment reads from outside the repository."""

    path: str
    reason: str
    provenance: Provenance


class EnvironmentRef(_Base):
    """The environment version range this document describes."""

    versions: str


class EnvironmentSpec(_Base):
    """Desired state: the human-authored content of the document."""

    environment: EnvironmentRef
    valid_for_days: int
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
    """Manifest identity."""

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
```

- [ ] **Step 4: Write `loader.py`**

```python
"""Reading, selecting and serializing environment spec manifests."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agent_skill_adapter.specs.models import (
    MANIFEST_REGISTRY,
    Manifest,
    Provenance,
)

_OPERATORS = (">=", "<=", "==", ">", "<")


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
            parts.append(f".{item}" if parts else item)
    return "".join(parts)


def load_manifest(path: Path) -> Manifest:
    """Load one manifest file, refusing unknown kinds and malformed records."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SpecLoadError(path, "<root>", "manifest must be a mapping")
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
    """Return True when version satisfies every comma-separated clause of ranges."""
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
    return records


def _is_stale(manifest: Manifest, today: date) -> bool:
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
        raise NoMatchingSpecError(
            f"no {environment} spec covers version {version} in {specs_dir}"
        )
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
    """Serialize a manifest canonically: model key order, named lists sorted by name."""
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


def directory_hash(path: Path) -> str:
    """Hash a published version directory: sorted relative paths and file contents."""
    digest = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        relative = file_path.relative_to(path).as_posix().encode("utf-8")
        content = file_path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"
```

- [ ] **Step 5: Write `__init__.py`**

```python
"""Environment spec manifests: models, loading, selection and serialization."""

from agent_skill_adapter.specs.loader import (
    AmbiguousSpecError,
    InsufficientDataError,
    NoMatchingSpecError,
    SpecError,
    SpecLoadError,
    StaleSpecError,
    UnsupportedManifestError,
    directory_hash,
    dump_manifest,
    load_manifest,
    select_spec,
    version_matches,
)
from agent_skill_adapter.specs.models import (
    API_VERSION,
    KIND,
    DriftEntry,
    EnvironmentSpec,
    FieldRecord,
    InvisibleSource,
    LimitRecord,
    Manifest,
    Metadata,
    Provenance,
    Status,
    ToolRecord,
    json_schema_text,
)

__all__ = [
    "API_VERSION",
    "KIND",
    "AmbiguousSpecError",
    "DriftEntry",
    "EnvironmentSpec",
    "FieldRecord",
    "InsufficientDataError",
    "InvisibleSource",
    "LimitRecord",
    "Manifest",
    "Metadata",
    "NoMatchingSpecError",
    "Provenance",
    "SpecError",
    "SpecLoadError",
    "StaleSpecError",
    "Status",
    "ToolRecord",
    "UnsupportedManifestError",
    "directory_hash",
    "dump_manifest",
    "json_schema_text",
    "load_manifest",
    "select_spec",
    "version_matches",
]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_specs.py -v`
Expected: PASS. If a `loc` assertion fails, print the real message once and align the fixture expectation with what Pydantic reports — do not loosen the assertion to a bare `pytest.raises`.

- [ ] **Step 7: Run the quality gates**

Run: `make check`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add src/agent_skill_adapter/specs tests/unit/test_specs.py tests/fixtures/specs
git commit -m "feat(specs): add environment spec models and loader

Refs #2"
```

---

### Task 3: Provenance script

**Files:**
- Create: `scripts/spec_provenance.py`
- Create: `tests/unit/test_spec_provenance.py`

**Interfaces:**
- Consumes: `agent_skill_adapter.specs.loader.load_manifest`, `dump_manifest`; `agent_skill_adapter.specs.models.Manifest`.
- Produces: `normalize(html: str) -> str`, `extract_section(html: str, anchor: str) -> str | None`, `section_hash(text: str) -> str`, `iter_records(manifest: Manifest) -> Iterator[tuple[str, Provenance]]`, `fill(path: Path) -> int`, `verify(path: Path) -> int`, `main(argv: list[str] | None = None) -> int`.

**Hash contract** (fixed, also written in the module docstring):
1. HTML to text; tags dropped, `<code>` keeps its content; `<script>` and `<style>` content dropped.
2. Unicode NFC; `\r\n` to `\n`.
3. Runs of whitespace to one space; trim.
4. UTF-8 bytes to sha256, written with the `sha256:` prefix.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_spec_provenance.py`:

```python
"""Unit tests for the provenance script. No network access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import spec_provenance  # noqa: E402

SAME_TEXT_A = """
<html><body>
<h2 id="frontmatter-reference">Frontmatter reference</h2>
<p>The <code>model</code> field overrides the session model.</p>
<h2 id="next">Next</h2>
<p>Ignored.</p>
</body></html>
"""

SAME_TEXT_B = """
<html><body>
<h2 id="frontmatter-reference"><span class="x">Frontmatter</span>
   reference</h2>
<div><p>The    <code>model</code>
field overrides the session model.</p></div>
<h2 id="next">Next</h2><p>Ignored.</p>
</body></html>
"""

CHANGED_TEXT = SAME_TEXT_A.replace("overrides the session model", "overrides the session effort")


def test_same_text_different_markup_hashes_equal() -> None:
    a = spec_provenance.extract_section(SAME_TEXT_A, "#frontmatter-reference")
    b = spec_provenance.extract_section(SAME_TEXT_B, "#frontmatter-reference")
    assert a is not None and b is not None
    assert spec_provenance.section_hash(a) == spec_provenance.section_hash(b)


def test_changed_text_changes_hash() -> None:
    a = spec_provenance.extract_section(SAME_TEXT_A, "#frontmatter-reference")
    c = spec_provenance.extract_section(CHANGED_TEXT, "#frontmatter-reference")
    assert a is not None and c is not None
    assert spec_provenance.section_hash(a) != spec_provenance.section_hash(c)


def test_section_stops_at_next_heading_of_same_level() -> None:
    section = spec_provenance.extract_section(SAME_TEXT_A, "#frontmatter-reference")
    assert section is not None
    assert "Ignored." not in section


def test_missing_anchor_returns_none() -> None:
    assert spec_provenance.extract_section(SAME_TEXT_A, "#absent") is None


def test_hash_carries_prefix() -> None:
    assert spec_provenance.section_hash("text").startswith("sha256:")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_spec_provenance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'spec_provenance'`

- [ ] **Step 3: Write `scripts/spec_provenance.py`**

```python
#!/usr/bin/env python3
"""Fill and verify documentation provenance hashes in an environment spec.

Hash contract (changing any step invalidates every recorded hash):

1. HTML is reduced to text: tags are dropped, ``<code>`` keeps its content,
   ``<script>`` and ``<style>`` content is discarded.
2. Text is normalized to Unicode NFC and ``\\r\\n`` becomes ``\\n``.
3. Runs of whitespace collapse to one space; the result is trimmed.
4. The UTF-8 bytes are hashed with sha256 and written with a ``sha256:`` prefix.

Usage:

    python scripts/spec_provenance.py fill   specs/claude-code/1.0.0/spec.yaml
    python scripts/spec_provenance.py verify specs/claude-code/1.0.0/spec.yaml

``fill`` is the only command that writes hashes, and only for records that have
none: a human writes ``url`` and ``anchor``, the script fills the mechanics.
``verify`` recomputes every hash, records mismatches in ``status.drift`` and
exits 1 when drift is present.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
import urllib.request
from collections.abc import Iterator
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_skill_adapter.specs.loader import dump_manifest, load_manifest  # noqa: E402
from agent_skill_adapter.specs.models import Manifest, Provenance  # noqa: E402

_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_SKIPPED = {"script", "style"}
_USER_AGENT = "agent-skill-adapter-spec-provenance/1.0"


class _SectionExtractor(HTMLParser):
    """Collect the text between a heading with the given id and the next peer heading."""

    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.found = False
        self._level = 0
        self._collecting = False
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED:
            self._skip_depth += 1
            return
        if tag not in _HEADINGS:
            return
        level = int(tag[1])
        if self._collecting and level <= self._level:
            self._collecting = False
            return
        if not self.found and dict(attrs).get("id") == self.target_id:
            self.found = True
            self._level = level
            self._collecting = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._collecting and not self._skip_depth:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._parts)


def normalize(text: str) -> str:
    """Apply steps 2 and 3 of the hash contract."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n"))
    return re.sub(r"\s+", " ", text).strip()


def extract_section(html: str, anchor: str) -> str | None:
    """Return the normalized text of the section addressed by anchor, or None."""
    parser = _SectionExtractor(anchor.lstrip("#"))
    parser.feed(html)
    parser.close()
    if not parser.found:
        return None
    return normalize(parser.text)


def section_hash(text: str) -> str:
    """Apply step 4 of the hash contract."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch(url: str) -> str:
    """Fetch a documentation page as text."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        body: bytes = response.read()
    return body.decode(charset, errors="replace")


def iter_records(manifest: Manifest) -> Iterator[tuple[str, Provenance]]:
    """Yield (record path, provenance) for every record that carries one."""
    spec = manifest.spec
    groups: list[tuple[str, list[Any]]] = [
        ("skillFields", list(spec.skill_fields)),
        ("agentFields", list(spec.agent_fields)),
        ("hooks", list(spec.hooks)),
        ("tools", list(spec.tools)),
        ("limits", list(spec.limits)),
    ]
    for group_name, records in groups:
        for record in records:
            yield f"{group_name}/{record.name}", record.provenance
    for source in spec.invisible_sources:
        yield f"invisibleSources/{source.path}", source.provenance


def _address(provenance: Provenance) -> str:
    return provenance.anchor if provenance.anchor is not None else str(provenance.selector)


def _section_text(provenance: Provenance) -> tuple[str | None, str | None]:
    """Return (text, failure reason)."""
    if provenance.selector is not None:
        return None, "selector-not-supported"
    try:
        html = fetch(provenance.url)
    except OSError as error:
        return None, f"fetch-failed: {error}"
    text = extract_section(html, str(provenance.anchor))
    if text is None:
        return None, "anchor-not-found"
    return text, None


def _set_provenance(data: dict[str, Any], record_path: str, **updates: Any) -> None:
    group, _, name = record_path.partition("/")
    key = "path" if group == "invisibleSources" else "name"
    for record in data["spec"].get(group, []):
        if record[key] == name:
            record["provenance"].update(updates)
            return
    raise KeyError(record_path)


def fill(path: Path) -> int:
    """Fill hash and checkedAt for records that have no hash yet."""
    manifest = load_manifest(path)
    data: dict[str, Any] = manifest.model_dump(mode="python", by_alias=True, exclude_none=True)
    today = date.today()
    failures = 0
    for record_path, provenance in iter_records(manifest):
        if provenance.hash is not None:
            continue
        text, reason = _section_text(provenance)
        if text is None:
            print(f"{record_path}: {reason} ({provenance.url}{_address(provenance)})")
            failures += 1
            continue
        _set_provenance(data, record_path, hash=section_hash(text), checkedAt=today)
        print(f"{record_path}: filled")
    path.write_text(dump_manifest(Manifest.model_validate(data)), encoding="utf-8")
    return 1 if failures else 0


def verify(path: Path) -> int:
    """Recompute every hash and record mismatches in status.drift."""
    manifest = load_manifest(path)
    data: dict[str, Any] = manifest.model_dump(mode="python", by_alias=True, exclude_none=True)
    drift: list[dict[str, Any]] = []
    for record_path, provenance in iter_records(manifest):
        if provenance.hash is None:
            drift.append({"record": record_path, "reason": "hash-missing"})
            continue
        text, reason = _section_text(provenance)
        if text is None:
            drift.append(
                {"record": record_path, "expected": provenance.hash, "reason": str(reason)}
            )
            continue
        actual = section_hash(text)
        if actual != provenance.hash:
            drift.append(
                {
                    "record": record_path,
                    "expected": provenance.hash,
                    "actual": actual,
                    "reason": "section-text-changed",
                }
            )
    data["status"] = {
        "verifiedAt": date.today(),
        "stale": bool(drift),
        "drift": drift,
    }
    path.write_text(dump_manifest(Manifest.model_validate(data)), encoding="utf-8")
    for entry in drift:
        print(f"{entry['record']}: {entry['reason']}")
    return 1 if drift else 0


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fill", "verify"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    command = fill if args.command == "fill" else verify
    return command(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_spec_provenance.py -v`
Expected: PASS

- [ ] **Step 5: Keep mypy strict happy on the script**

`make check` runs mypy over `src` and `tests` only, so the script is not type-checked by default. Run it explicitly once and fix what it reports:

Run: `uv run mypy scripts/spec_provenance.py`
Expected: `Success: no issues found`

- [ ] **Step 6: Run the quality gates**

Run: `make check`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/spec_provenance.py tests/unit/test_spec_provenance.py
git commit -m "feat(specs): add documentation provenance fill and verify script

Refs #2"
```

---

### Task 4: Generated JSON Schema

**Files:**
- Create: `specs/schema/environmentspec.v1alpha1.json`
- Modify: `Makefile` (add `spec-schema` target)
- Modify: `tests/unit/test_specs.py` (add the schema test)

**Interfaces:**
- Consumes: `agent_skill_adapter.specs.models.json_schema_text`.
- Produces: the committed schema file; no new Python symbols.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_specs.py`:

```python
from agent_skill_adapter.specs.models import json_schema_text

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_schema_matches_models() -> None:
    """The committed JSON Schema must be what the models generate today."""
    committed = REPO_ROOT / "specs" / "schema" / "environmentspec.v1alpha1.json"
    assert committed.read_text(encoding="utf-8") == json_schema_text(), (
        "schema is out of date; run `make spec-schema`"
    )
```

Move the `json_schema_text` import up to the existing import block when adding it — a mid-file import fails ruff's `E402`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_specs.py::test_committed_schema_matches_models -v`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Add the Makefile target**

Insert after the `format` target in `Makefile`:

```makefile
.PHONY: spec-schema
spec-schema: ## Regenerate the manifest JSON Schema from the Pydantic models
	$(UV) run python -c "from pathlib import Path; \
from agent_skill_adapter.specs.models import json_schema_text; \
Path('specs/schema/environmentspec.v1alpha1.json').parent.mkdir(parents=True, exist_ok=True); \
Path('specs/schema/environmentspec.v1alpha1.json').write_text(json_schema_text(), encoding='utf-8')"
```

- [ ] **Step 4: Generate the schema**

Run: `make spec-schema`
Expected: `specs/schema/environmentspec.v1alpha1.json` exists and is valid JSON.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_specs.py::test_committed_schema_matches_models -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add Makefile specs/schema tests/unit/test_specs.py
git commit -m "feat(specs): generate and commit the manifest JSON Schema

Refs #2"
```

---

### Task 5: Claude Code spec 1.0.0 content

**Files:**
- Create: `specs/claude-code/1.0.0/spec.yaml`
- Delete: `specs/anthropic/.gitkeep` (design D6 renames the directory)
- Modify: `tests/unit/test_specs.py` (add the real-spec tests)

**Interfaces:**
- Consumes: the documentation snapshot from Task 1, the models and loader from Task 2, the script from Task 3.
- Produces: the only valid spec fixture the rest of the project reads.

**Sources** — the snapshot from Task 1, never a fresh fetch. Re-downloading
mid-task would let a record cite a page that differs from the one Task 1
inspected:

| Group | Snapshot file | URL recorded in `provenance` | Anchor |
|-------|---------------|------------------------------|--------|
| `skillFields` | `skills.md` / `skills.html` | `https://code.claude.com/docs/en/skills` | `#frontmatter-reference` |
| `tools` | `tools-reference.md` / `.html` | `https://code.claude.com/docs/en/tools-reference` | the heading `id` above the tool table, as written down in Task 1 step 3 |
| `limits` | `skills.md` / `skills.html` | `https://code.claude.com/docs/en/skills` | the section documenting each limit |
| `invisibleSources` | `settings.md` / `.html` | `https://code.claude.com/docs/en/settings` | `#settings-files-and-who-they-affect` |
| `invisibleSources` (CLAUDE.md) | `memory.md` / `.html` | `https://code.claude.com/docs/en/memory` | the section naming the user-level file |
| `invisibleSources` (managed policy) | `managed-settings.md` / `.html` | `https://code.claude.com/docs/en/managed-settings` | `#delivery-mechanisms` |

- [ ] **Step 1: Read the snapshot and write down the field list**

```bash
SNAP=.cache/claude-code-docs/$(ls .cache/claude-code-docs | sort | tail -1)
cat "$SNAP/frontmatter-reference.md"
cat "$SNAP/tool-names.txt"
cat "$SNAP/NOTES.md"
```

If `$SNAP` does not exist, Task 1 was skipped — go back and do it; do not
substitute a `curl` here.

Record one `FieldRecord` per frontmatter key the snapshot documents. At the time
this plan was written that was: `name`, `description`, `when_to_use`,
`argument-hint`, `arguments`, `disable-model-invocation`, `user-invocable`,
`allowed-tools`, `disallowed-tools`, `model`, `effort`, `context`, `agent`,
`background`, `hooks`, `paths`, `shell`, `metadata`, `license`,
`compatibility`. **Take the real list from `frontmatter-reference.md`** — the
snapshot is the source of truth, this plan is not. In particular, `isolation`
appears in the PRD but not in the documentation; a key with no documented
section has no provenance and is not recorded.

`portable: true` only for keys the open Agent Skills spec defines (`name`,
`description`, `license`, `compatibility` — check the documentation's own
"Using skill frontmatter outside Claude Code" section, which states which keys
other harnesses read). Everything else is `portable: false` and becomes FR-48
gap material.

`since` carries a version only where the documentation states one (for example
`background` requires v2.1.218+); otherwise omit it.

- [ ] **Step 2: Write `specs/claude-code/1.0.0/spec.yaml` with `url` and `anchor`, no hashes**

Shape (fill every documented key; this shows the first three records and one of
each other record type):

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: claude-code
  version: 1.0.0
  labels:
    vendor: anthropic
    role: source
  annotations:
    adapter.prgate.io/changelog: CHANGELOG.md
spec:
  environment:
    versions: ">=2.1.200,<2.2.0"
  validForDays: 90
  skillFields:
    - name: name
      kind: string
      required: false
      portable: true
      effect: Display name in skill listings; defaults to the directory name.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
    - name: context
      kind: enum
      values: [fork]
      required: false
      portable: false
      effect: Runs the skill in a forked subagent context.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
    - name: background
      kind: bool
      required: false
      since: "2.1.218"
      portable: false
      effect: >-
        With context fork, false waits for the forked subagent's result.
        Defaults to true.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
  tools:
    - name: Bash
      provenance:
        url: https://code.claude.com/docs/en/tools-reference
        anchor: "#TOOL-TABLE-ANCHOR"
  limits:
    - name: skill_description_chars
      value: 1536
      unit: chars
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#frontmatter-reference"
  invisibleSources:
    - path: ~/.claude/settings.json
      reason: user-level settings, permissions and hooks live outside the repository
      provenance:
        url: https://code.claude.com/docs/en/settings
        anchor: "#settings-files-and-who-they-affect"
status:
  stale: false
```

Set the environment version range from the version of Claude Code the
documentation describes; if the page does not state one, use the lowest version
any `since` on the page names and the next minor as the upper bound, and say so
in `CHANGELOG.md` (Task 6).

`limits` records only limits whose unit is `bytes`, `chars` or `tokens`. A
documented limit with any other unit (for example "up to 6 stacked skills") is
not recorded in 1.0.0.

- [ ] **Step 3: Verify the file loads before touching the network**

Run: `uv run python -c "from pathlib import Path; from agent_skill_adapter.specs import load_manifest; m = load_manifest(Path('specs/claude-code/1.0.0/spec.yaml')); print(len(m.spec.skill_fields), 'skill fields')"`
Expected: prints the record count; any `SpecLoadError` names the record to fix.

- [ ] **Step 4: Fill the hashes**

`fill` is the one step here that goes to the network. Before running it, prove
that the live page still equals the snapshot Task 1 inspected, so the hash it
writes describes the text that was actually read:

```bash
SNAP=.cache/claude-code-docs/$(ls .cache/claude-code-docs | sort | tail -1)
uv run python - "$SNAP" <<'SNAPCHECK'
import hashlib
import sys
import urllib.request
from pathlib import Path

snapshot = Path(sys.argv[1])
headers = {"User-Agent": "agent-skill-adapter-spec-provenance/1.0"}
for line in (snapshot / "sources.tsv").read_text(encoding="utf-8").splitlines()[1:]:
    slug, url, recorded, _ = line.split("\t")
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        live = "sha256:" + hashlib.sha256(response.read()).hexdigest()
    print(f"{slug}: {'same' if live == recorded else 'CHANGED'}")
SNAPCHECK
```

A `CHANGED` line is not automatically a problem — these pages carry build ids and
timestamps, so the raw bytes drift while the section text does not. It is a
warning: after `fill`, re-read that page's section in the snapshot and confirm
the record still says what the section says. If the section text itself moved,
re-run Task 1 and redo the authoring from the fresh snapshot.

Run: `uv run python scripts/spec_provenance.py fill specs/claude-code/1.0.0/spec.yaml`
Expected: one `filled` line per record, exit 0. An `anchor-not-found` line means the anchor is wrong — fix the anchor, do not delete the record.

- [ ] **Step 5: Canonicalize the file**

Run: `uv run python -c "from pathlib import Path; from agent_skill_adapter.specs import dump_manifest, load_manifest; p = Path('specs/claude-code/1.0.0/spec.yaml'); p.write_text(dump_manifest(load_manifest(p)), encoding='utf-8')"`
Expected: the file is now byte-identical to what `dump_manifest` produces.

- [ ] **Step 6: Add the real-spec tests**

Append to `tests/unit/test_specs.py`:

```python
CLAUDE_CODE_1_0_0 = REPO_ROOT / "specs" / "claude-code" / "1.0.0" / "spec.yaml"


def test_published_spec_loads() -> None:
    """The spec shipped in this repository must load."""
    manifest = load_manifest(CLAUDE_CODE_1_0_0)
    assert manifest.metadata.name == "claude-code"
    assert manifest.spec.skill_fields, "1.0.0 must record skill frontmatter fields"
    assert manifest.spec.tools, "1.0.0 must record tool names"


def test_published_spec_is_canonically_serialized() -> None:
    """A hand edit that breaks canonical form must fail here, not in a later diff."""
    manifest = load_manifest(CLAUDE_CODE_1_0_0)
    assert dump_manifest(manifest) == CLAUDE_CODE_1_0_0.read_text(encoding="utf-8")


def test_published_spec_records_carry_provenance_hashes() -> None:
    """An unverified record is not shippable (FR-2)."""
    spec = load_manifest(CLAUDE_CODE_1_0_0).spec
    records = (
        [(f.name, f.provenance) for f in spec.skill_fields]
        + [(t.name, t.provenance) for t in spec.tools]
        + [(limit.name, limit.provenance) for limit in spec.limits]
        + [(s.path, s.provenance) for s in spec.invisible_sources]
    )
    missing = [name for name, provenance in records if provenance.hash is None]
    assert not missing, f"records without a provenance hash: {missing}"
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/unit/test_specs.py -v`
Expected: PASS

- [ ] **Step 8: Remove the superseded directory placeholder**

```bash
git rm specs/anthropic/.gitkeep
```

- [ ] **Step 9: Run the quality gates and commit**

Run: `make check`

```bash
git add specs/claude-code tests/unit/test_specs.py
git commit -m "feat(specs): publish Claude Code environment spec 1.0.0

Refs #2"
```

---

### Task 6: Changelog, version lock and the immutability test

**Files:**
- Create: `specs/claude-code/CHANGELOG.md`
- Create: `specs/claude-code/versions.lock`
- Modify: `tests/unit/test_specs.py` (add the lock test)

**Interfaces:**
- Consumes: `agent_skill_adapter.specs.loader.directory_hash`.
- Produces: `versions.lock` lines of the form `<version> <sha256:hex>`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_specs.py`:

```python
from agent_skill_adapter.specs.loader import directory_hash

VERSIONS_LOCK = REPO_ROOT / "specs" / "claude-code" / "versions.lock"


def read_lock(path: Path) -> dict[str, str]:
    """Parse a versions.lock file, ignoring comment and blank lines."""
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        version, digest = stripped.split()
        entries[version] = digest
    return entries


def test_published_versions_are_immutable() -> None:
    """A published version directory must never change (FR-5); publish 1.0.1 instead."""
    entries = read_lock(VERSIONS_LOCK)
    assert entries, "versions.lock must pin at least one published version"
    for version, digest in entries.items():
        directory = VERSIONS_LOCK.parent / version
        assert directory.is_dir(), f"versions.lock pins missing directory {version}"
        assert directory_hash(directory) == digest, (
            f"{version} changed after publication; publish a new version directory instead"
        )
```

Move `directory_hash` into the existing import block from `agent_skill_adapter.specs.loader`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_specs.py::test_published_versions_are_immutable -v`
Expected: FAIL — `FileNotFoundError: .../versions.lock`

- [ ] **Step 3: Write `specs/claude-code/CHANGELOG.md`**

```markdown
# Claude Code environment spec — changelog

Each published version directory is immutable. A correction is a new version
next to the old one; `versions.lock` pins the content of every published
directory.

## 1.0.0 — 2026-09-13

First published document.

- Environment range: `>=2.1.200,<2.2.0` — <state where this range came from>.
- `skillFields`: every frontmatter key documented for `SKILL.md`.
- `tools`: every tool name in the tools reference.
- `limits`: documented size limits carrying a `bytes`, `chars` or `tokens`
  unit. Limits with other units (for example the number of stacked skills) are
  not recorded.
- `invisibleSources`: user settings, user memory and enterprise managed policy
  files.
- Not covered: subagent fields (1.1.0), hooks (1.2.0).
```

Replace `<state where this range came from>` with the actual justification from Task 5 step 2.

- [ ] **Step 4: Generate `versions.lock`**

```bash
uv run python - <<'PY'
from pathlib import Path

from agent_skill_adapter.specs.loader import directory_hash

root = Path("specs/claude-code")
header = (
    "# sha256 of each published spec version directory. A published directory is\n"
    "# immutable: to correct a record, publish a new version next to it.\n"
    "# Regenerate after publishing a new version with:\n"
    '#   uv run python -c "from pathlib import Path; '
    "from agent_skill_adapter.specs.loader import directory_hash; "
    "print(directory_hash(Path('specs/claude-code/<version>')))\"\n"
)
lines = [
    f"{d.name} {directory_hash(d)}"
    for d in sorted(p for p in root.iterdir() if p.is_dir())
]
(root / "versions.lock").write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
print((root / "versions.lock").read_text(encoding="utf-8"))
PY
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_specs.py::test_published_versions_are_immutable -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add specs/claude-code/CHANGELOG.md specs/claude-code/versions.lock tests/unit/test_specs.py
git commit -m "feat(specs): pin published spec versions and add the changelog

Refs #2"
```

---

### Task 7: Green gates and PR readiness

**Files:**
- Modify: `README.md` (one short section on the spec layout and the two commands) — only if `README.md` already documents repository layout; otherwise skip and note it.

- [ ] **Step 1: Run the full gate**

Run: `make check`
Expected: exit 0. Fix anything reported; do not weaken a rule to pass.

- [ ] **Step 2: Confirm the provenance script still agrees with the published hashes**

Run: `uv run python scripts/spec_provenance.py verify specs/claude-code/1.0.0/spec.yaml`
Expected: exit 0 and no drift lines. This run rewrites `status.verifiedAt`, so:

```bash
git diff --stat specs/claude-code/1.0.0/spec.yaml
```

If only `status` changed, keep the change and regenerate `versions.lock` (Task 6 step 4), then re-run `make check`. If `spec` changed, something is wrong with `dump_manifest` — fix it rather than committing the churn.

- [ ] **Step 3: Confirm no dependency was added**

Run: `git diff main -- pyproject.toml uv.lock`
Expected: empty.

- [ ] **Step 4: Commit any leftovers and push**

```bash
git add -A
git commit -m "chore(specs): refresh provenance verification timestamp

Refs #2"
git push
```

- [ ] **Step 5: Mark PR #45 ready for review**

```bash
gh pr ready 45
```

- [ ] **Step 6: Update the PR body**

Summarize: the manifest format and why the envelope is Kubernetes-shaped, the loader's three refusal modes, the provenance hash contract, what 1.0.0 covers and what is deferred to 1.1.0/1.2.0, and the immutability rule. Link the design document.

---

## Self-Review

**Spec coverage:**

| Design section | Task |
|----------------|------|
| §3 layout, immutability, `metadata.version` rule | 2 (version rule), 6 (lock) |
| §4 manifest format, camelCase, `extra="forbid"`, list-keyed-by-name | 2 |
| §5 provenance script, hash contract, edge rules | 3 |
| §6 models, validators, loader, comparator, `dump_manifest`, schema | 2, 4 |
| §7 tests | 2, 3, 4, 5, 6 |
| §8 spec 1.0.0 contents | 1 (raw material), 5 (records) |
| §9 scope, `spec-schema` target, issue comment | 4, 7 |

The issue #2 comment recording D6 and D3 is already posted, so §9's last item needs no task.

**Known gaps accepted:** the `selector` branch of the provenance script returns `selector-not-supported`; 1.0.0 uses anchors only, and the design defers selector support to pages that need it.
