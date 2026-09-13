# Environment Spec Format, Agent Skills Baseline and Claude Code Spec 1.0.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a versioned, provenance-carrying environment spec format with a deterministic loader, publish the open Agent Skills specification as the baseline spec, and publish Claude Code spec 1.0.0 that extends it.

**Architecture:** Pydantic v2 models are the single source of truth for a Kubernetes-style manifest envelope (`apiVersion`/`kind`/`metadata`/`spec`/`status`). A loader reads YAML through `yaml.safe_load`, dispatches on `(apiVersion, kind)`, resolves `spec.extends` to a baseline manifest, and selects a spec by environment version range and staleness. Portability is **derived** from the baseline, never authored. A stdlib-only script fetches documentation sections, hashes their normalized text, and writes results into `status`. The JSON Schema is generated from the models, and published version directories are pinned by content hash.

**Order:** the upstream sources are downloaded to a local snapshot **first**; every later task authors records from that snapshot rather than from a live page, so authoring is reproducible and the engine is built against material that already exists.

**Tech Stack:** Python 3.10+, Pydantic v2, PyYAML, pytest, mypy strict, ruff, uv, Make.

**Spec:** `docs/superpowers/specs/2026-09-13-environment-spec-format-design.md` at commit `57a5940` or later. Read it before Task 2; it is the source of truth and this plan is subordinate to it.

## Global Constraints

- No new runtime or dev dependencies. `pydantic>=2.0.0` and `pyyaml>=6.0.0` are already declared; `packaging` and `strictyaml` must **not** be added — the loader implements its own dotted-integer comparator and FR-15 rules sit on `yaml.safe_load`.
- Repository artifacts (code, docstrings, comments, docs, commit messages, PR text) are 100% English.
- Conventional Commits, every commit body ends with `Refs #2`.
- Work happens in `.worktrees/issue2` on branch `feature/environment-spec-format`; PR #45.
- Manifest key case is camelCase (`alias_generator=to_camel`, `populate_by_name=True`); unknown keys are rejected (`extra="forbid"`); models are `frozen=True`.
- `apiVersion` is exactly `adapter.prgate.io/v1alpha1`; `kind` is exactly `EnvironmentSpec`.
- **`portable` is never a field.** It is derived by `portable_fields(manifest, baseline)` (design D8). A hand-written portability flag anywhere under `specs/` is a defect.
- Tests never touch the network.
- Out of scope (do not implement): subagent fields, hooks records, `ContractRegistry`, CI drift step, FR-8 auto-PR, Markdown body parsing, drift significance threshold, running `skills-ref validate` against adapter output.
- `make check` (ruff check, ruff format --check, mypy strict on `src` and `tests`, pytest) must pass before the PR leaves draft.

## File Structure

| File | Responsibility |
|------|----------------|
| `.cache/spec-sources/<date>/` | Local snapshot of the upstream sources (gitignored); the raw material every record is authored from |
| `.gitignore` | Ignores `.cache/` |
| `src/agent_skill_adapter/specs/__init__.py` | Public re-exports |
| `src/agent_skill_adapter/specs/models.py` | Pydantic models, validators, `MANIFEST_REGISTRY`, `json_schema_text()` |
| `src/agent_skill_adapter/specs/loader.py` | `load_manifest`, `resolve_baseline`, `portable_fields`, `select_spec`, `dump_manifest`, `directory_hash`, version comparator, errors |
| `scripts/spec_provenance.py` | `fill` / `verify`, HTML section extraction, hash normalization |
| `specs/schema/environmentspec.v1alpha1.json` | Generated JSON Schema (committed) |
| `specs/agentskills/1.0.0/spec.yaml` | Baseline: the open Agent Skills specification |
| `specs/agentskills/CHANGELOG.md`, `versions.lock` | Baseline history and immutability pin |
| `specs/claude-code/1.0.0/spec.yaml` | Claude Code spec 1.0.0, `extends: agentskills@1.0.0` |
| `specs/claude-code/CHANGELOG.md`, `versions.lock` | Claude Code history and immutability pin |
| `tests/unit/test_specs.py` | Models, loader, selection, serialization, portability, schema, lock |
| `tests/unit/test_spec_provenance.py` | Hash normalization (offline) |
| `tests/fixtures/specs/*.yaml` | One minimal broken manifest per load error |
| `Makefile` | `spec-schema` target |

## Open points resolved by this plan

The design leaves four details underspecified. These are fills, not revisions.

1. **Staleness reference date.** Design §6 says "stale when `checkedAt + validForDays < today`", while §4 puts `verifiedAt` in `status`. Resolution: the reference date is `status.verifiedAt` when set, otherwise the **oldest** `provenance.checkedAt` across all records; when neither exists the spec is stale. A spec the verification script never touched still ages from its weakest record.
2. **Limit units.** The design's unit set is `bytes | chars | tokens | lines`, with `enforcement: hard | recommended`. A documented limit whose unit is none of these (for example "up to 6 stacked skills") is **not** recorded in 1.0.0.
3. **`versions.lock` regeneration.** No new Make target: `directory_hash()` lives in `loader.py`, the test uses it, and each `versions.lock` carries the regeneration one-liner as a comment header.
4. **Provenance granularity of `layout`.** Design §4 says "each entry carries provenance" while its example shows none. Resolution: one `provenance` on the `layout` block, because each environment states its layout in one documentation section. Per-entry provenance can arrive when an environment splits its directories across sections.

---

### Task 1: Local snapshot of the upstream sources

Nothing is implemented before the source material exists on disk. This task downloads every upstream source once, checks that the anchors the records will cite are really present in the rendered HTML, and leaves a manifest of what was fetched.

**Files:**
- Create: `.cache/spec-sources/<YYYY-MM-DD>/*.md`, `*.html`, `agentskills-validator.py`, `sources.tsv` (gitignored)
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `<slug>.md` (readable), `<slug>.html` (what the hash contract applies to), `sources.tsv` with columns `slug`, `url`, `sha256_html`, `fetched_at`.

**Sources:**

| Slug | URL | Supplies |
|------|-----|----------|
| `agentskills-specification` | `https://agentskills.io/specification` | baseline `skillFields`, `limits`, `layout`, `frontmatter` |
| `agentskills-validator` | `https://raw.githubusercontent.com/agentskills/agentskills/<SHA>/skills-ref/src/skills_ref/validator.py` | evidence for `frontmatter.unknownFields: reject` (`ALLOWED_FIELDS`) and the numeric caps |
| `skills` | `https://code.claude.com/docs/en/skills` | Claude Code `skillFields`, `limits`, `layout` |
| `tools-reference` | `https://code.claude.com/docs/en/tools-reference` | Claude Code `tools` |
| `settings` | `https://code.claude.com/docs/en/settings` | `invisibleSources` — settings files |
| `memory` | `https://code.claude.com/docs/en/memory` | `invisibleSources` — `CLAUDE.md` |
| `managed-settings` | `https://code.claude.com/docs/en/managed-settings` | `invisibleSources` — enterprise policy |
| `claude-directory` | `https://code.claude.com/docs/en/claude-directory` | `invisibleSources` — what `~/.claude` holds |

`<SHA>` is the `agentskills/agentskills` commit the baseline is pinned to. Resolve it once and record it; at the time of writing it is `69ef37e9424c0a7ea9dd2293b559e43ec8176379`.

- [ ] **Step 1: Ignore the snapshot directory**

Append to `.gitignore`:

```gitignore

# Local snapshot of upstream specification sources (raw material for specs/)
.cache/
```

- [ ] **Step 2: Resolve and record the upstream commit**

```bash
curl -s https://api.github.com/repos/agentskills/agentskills/commits/main \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['sha'], d['commit']['committer']['date'])"
```

Use the SHA it prints, not the one written above, unless they agree. It goes into `metadata.annotations.adapter.prgate.io/upstream-commit` of the baseline spec (Task 5) — the repo has no tags, so the commit is the version.

- [ ] **Step 3: Download the snapshot**

Write `snapshot.py` in a scratch directory (not in the repository) and run it from the worktree root:

```python
import hashlib
import urllib.request
from datetime import date
from pathlib import Path

SHA = "<the SHA from step 2>"
PAGES = {
    "agentskills-specification": "https://agentskills.io/specification",
    "skills": "https://code.claude.com/docs/en/skills",
    "tools-reference": "https://code.claude.com/docs/en/tools-reference",
    "settings": "https://code.claude.com/docs/en/settings",
    "memory": "https://code.claude.com/docs/en/memory",
    "managed-settings": "https://code.claude.com/docs/en/managed-settings",
    "claude-directory": "https://code.claude.com/docs/en/claude-directory",
}
RAW = {
    "agentskills-validator": (
        f"https://raw.githubusercontent.com/agentskills/agentskills/{SHA}"
        "/skills-ref/src/skills_ref/validator.py"
    ),
}
today = date.today().isoformat()
root = Path(".cache/spec-sources") / today
root.mkdir(parents=True, exist_ok=True)
headers = {"User-Agent": "agent-skill-adapter-spec-provenance/1.0"}
rows = ["slug\turl\tsha256_html\tfetched_at"]


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


for slug, url in PAGES.items():
    html = get(url)
    (root / f"{slug}.html").write_bytes(html)
    (root / f"{slug}.md").write_bytes(get(url + ".md"))
    rows.append(f"{slug}\t{url}\tsha256:{hashlib.sha256(html).hexdigest()}\t{today}")
    print(f"{slug}: {len(html)} bytes")

for slug, url in RAW.items():
    body = get(url)
    (root / f"{slug}.py").write_bytes(body)
    rows.append(f"{slug}\t{url}\tsha256:{hashlib.sha256(body).hexdigest()}\t{today}")
    print(f"{slug}: {len(body)} bytes")

(root / "sources.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
```

A non-200 response raises `urllib.error.HTTPError` — check the URL against `https://code.claude.com/docs/llms.txt` or `https://agentskills.io/llms.txt`, which list every published page, and re-run.

- [ ] **Step 4: Confirm the anchors exist in the rendered HTML**

The hash contract cuts a section out of the HTML by heading `id`, so an anchor that exists only in the Markdown source is useless.

```bash
SNAP=.cache/spec-sources/$(ls .cache/spec-sources | sort | tail -1)
for f in "$SNAP"/*.html; do
  echo "== $f"
  grep -oE '<h[1-6][^>]*id="[^"]+"' "$f" | grep -oE 'id="[^"]+"' | sort -u
done
```

Expected: `agentskills-specification.html` carries one anchor per baseline field — `#name-field`, `#description-field`, `#license-field`, `#compatibility-field`, `#metadata-field`, `#allowed-tools-field` — plus `#frontmatter`, `#directory-structure`, `#optional-directories`, `#progressive-disclosure`, `#validation`. `skills.html` carries `#frontmatter-reference`; `settings.html` carries `#settings-files-and-who-they-affect`. Write down the real heading `id` above the tool table in `tools-reference.html` — it is the one anchor this plan cannot name in advance.

`agentskills-validator.py` is not HTML and has no anchors. It is read to confirm `unknownFields: reject` and the numeric caps; the record stating that policy cites the rendered `#validation` section, which the hash contract can address. The raw blob is evidence for the reviewer, not a provenance target.

If a page renders its headings only in the browser, its `id` values are absent here. That page then needs `selector` rather than `anchor`, which `scripts/spec_provenance.py` does not support (see "Known gaps accepted"): drop the page from 1.0.0 and record the omission in `CHANGELOG.md` rather than ship a record with no verifiable address.

- [ ] **Step 5: Extract the authoring material**

```bash
SNAP=.cache/spec-sources/$(ls .cache/spec-sources | sort | tail -1)
sed -n '/^### Frontmatter reference/,/^### Add supporting files/p' "$SNAP/skills.md" \
  > "$SNAP/cc-frontmatter.md"
grep -oE '^\| *`[A-Za-z]+`' "$SNAP/tools-reference.md" | tr -d '| `' | sort -u \
  > "$SNAP/cc-tool-names.txt"
sed -n '/^### Frontmatter/,/^## Optional directories/p' "$SNAP/agentskills-specification.md" \
  > "$SNAP/as-frontmatter.md"
grep -nE 'ALLOWED_FIELDS|MAX_[A-Z_]+ *=' "$SNAP/agentskills-validator.py"
wc -l "$SNAP"/cc-frontmatter.md "$SNAP"/cc-tool-names.txt "$SNAP"/as-frontmatter.md
```

Read `as-frontmatter.md` and `cc-frontmatter.md` in full. They, not this plan and not memory, are the lists of keys Tasks 5 and 6 record. If a `sed` range comes back empty the headings have been renamed — find the real ones with `grep -nE '^#{2,4} ' "$SNAP/<file>.md"` and redo the cut.

- [ ] **Step 6: Write `NOTES.md` next to the snapshot**

Record, for the authoring passes in Tasks 5 and 6: every frontmatter key with its kind, required flag, stability, and the constraints the source states (length, pattern, directory match); every `since` version; every limit with its unit and whether the source calls it a requirement or a recommendation; the unknown-field policy with the line that states it; the skill file names, skills directories with their scope, and conventional directories; the settings and memory file paths. Nothing here is committed; it exists so Tasks 5 and 6 never need the network.

- [ ] **Step 7: Commit the ignore rule**

The snapshot itself is never committed — provenance hashes, not a vendored copy of someone else's documentation, are what make a record auditable.

```bash
git add .gitignore
git commit -m "chore(specs): ignore the local upstream source snapshot

Refs #2"
```

---

### Task 2: Models and loader

**Files:**
- Create: `src/agent_skill_adapter/specs/__init__.py`, `models.py`, `loader.py`
- Create: `tests/unit/test_specs.py`
- Create: `tests/fixtures/specs/{unknown_kind,unknown_key,duplicate_name,enum_without_values,map_without_value_kind,both_anchor_and_selector}.yaml`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `models`: `Manifest`, `Metadata`, `EnvironmentSpec`, `EnvironmentRef`, `FrontmatterPolicy`, `Layout`, `SkillsDir`, `FieldRecord`, `FieldConstraints`, `ToolRecord`, `LimitRecord`, `InvisibleSource`, `Provenance`, `Status`, `DriftEntry`, `MANIFEST_REGISTRY`, `BASELINE_ROLE`, `json_schema_text() -> str`
  - `loader`: `load_manifest(path) -> Manifest`, `resolve_baseline(manifest, specs_dir) -> Manifest | None`, `portable_fields(manifest, baseline) -> frozenset[str]`, `select_spec(specs_dir, environment, version, *, today, pinned=None) -> Manifest`, `dump_manifest(manifest) -> str`, `directory_hash(path) -> str`, `version_matches(version, ranges) -> bool`
  - Errors: `SpecError`, `SpecLoadError(path, loc, reason)`, `UnsupportedManifestError(path, api_version, kind)`, `InsufficientDataError`, `NoMatchingSpecError`, `AmbiguousSpecError`, `StaleSpecError`

- [ ] **Step 1: Write the fixtures**

`tests/fixtures/specs/unknown_kind.yaml`:

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

`tests/fixtures/specs/unknown_key.yaml` — the key on the `sinсe` line contains a Cyrillic `с`, deliberately: it is the typo `extra="forbid"` must catch.

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

`tests/fixtures/specs/duplicate_name.yaml` — same envelope, two `skillFields` entries both named `model`, `kind: string`, differing `effect`, each with `provenance: {url: https://code.claude.com/docs/en/skills, anchor: "#frontmatter-reference"}`.

`tests/fixtures/specs/enum_without_values.yaml` — one entry `name: effort`, `kind: enum`, no `values`.

`tests/fixtures/specs/map_without_value_kind.yaml` — one entry `name: metadata`, `kind: map`, no `valueKind`.

`tests/fixtures/specs/both_anchor_and_selector.yaml` — one `tools` entry `name: Bash` whose `provenance` carries both `anchor: "#bash-tool-behavior"` and `selector: "main > table"`.

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_specs.py`:

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
    directory_hash,
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
        ("duplicate_name.yaml", "spec.skillFields"),
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
        select_spec(
            tmp_path, "claude-code", "2.1.220", today=date(2026, 9, 13), pinned="1.0.1"
        )


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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_specs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_skill_adapter.specs'`

- [ ] **Step 4: Write `models.py`**

```python
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
```

- [ ] **Step 5: Write `loader.py`**

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

- [ ] **Step 6: Write `__init__.py`**

Re-export every name listed under "Interfaces" above, with an explicit `__all__` sorted alphabetically. Nothing else.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/unit/test_specs.py -v`
Expected: every test passes except `test_committed_schema_matches_models`, which fails with `FileNotFoundError` until Task 4. If a `loc` assertion fails, print the real message once and align the expectation with what Pydantic reports — do not loosen the assertion to a bare `pytest.raises`.

- [ ] **Step 8: Commit**

```bash
git add src/agent_skill_adapter/specs tests/unit/test_specs.py tests/fixtures/specs
git commit -m "feat(specs): add environment spec models and loader

Refs #2"
```

---

### Task 3: Provenance script

**Files:**
- Create: `scripts/spec_provenance.py`, `tests/unit/test_spec_provenance.py`

**Interfaces:**
- Consumes: `loader.load_manifest`, `loader.dump_manifest`, `models.Manifest`, `models.Provenance`.
- Produces: `normalize(text) -> str`, `extract_section(html, anchor) -> str | None`, `section_hash(text) -> str`, `iter_records(manifest) -> Iterator[tuple[str, Provenance]]`, `fill(path) -> int`, `verify(path) -> int`, `main(argv=None) -> int`.

**Hash contract** (fixed, repeated verbatim in the module docstring):
1. HTML to text; tags dropped, `<code>` keeps its content, `<script>`/`<style>` content discarded.
2. Unicode NFC; `\r\n` to `\n`.
3. Runs of whitespace to one space; trim.
4. UTF-8 bytes to sha256, written with the `sha256:` prefix.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_spec_provenance.py`:

```python
"""Unit tests for the provenance script. No network access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import spec_provenance  # noqa: E402

SAME_TEXT_A = """
<html><body>
<h2 id="name-field">name field</h2>
<p>Must be <code>1-64</code> characters.</p>
<h2 id="next">Next</h2>
<p>Ignored.</p>
</body></html>
"""

SAME_TEXT_B = """
<html><body>
<h2 id="name-field"><span class="x">name</span>
   field</h2>
<div><p>Must be    <code>1-64</code>
characters.</p></div>
<h2 id="next">Next</h2><p>Ignored.</p>
</body></html>
"""

CHANGED_TEXT = SAME_TEXT_A.replace("1-64", "1-128")


def test_same_text_different_markup_hashes_equal() -> None:
    a = spec_provenance.extract_section(SAME_TEXT_A, "#name-field")
    b = spec_provenance.extract_section(SAME_TEXT_B, "#name-field")
    assert a is not None and b is not None
    assert spec_provenance.section_hash(a) == spec_provenance.section_hash(b)


def test_changed_text_changes_hash() -> None:
    a = spec_provenance.extract_section(SAME_TEXT_A, "#name-field")
    c = spec_provenance.extract_section(CHANGED_TEXT, "#name-field")
    assert a is not None and c is not None
    assert spec_provenance.section_hash(a) != spec_provenance.section_hash(c)


def test_section_stops_at_next_heading_of_same_level() -> None:
    section = spec_provenance.extract_section(SAME_TEXT_A, "#name-field")
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

Structure, in order:

1. Module docstring carrying the four-step hash contract verbatim and the two usage lines.
2. `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))` before importing the package, with `# noqa: E402` on the package imports.
3. `_SectionExtractor(HTMLParser)` — `handle_starttag` opens collection when a heading's `id` equals the target and closes it at the next heading of the same or higher level; `<script>`/`<style>` bodies are skipped through a depth counter; `handle_data` appends text only while collecting and not skipping.
4. `normalize`, `extract_section`, `section_hash`, `fetch` (urllib, 30 s timeout, project User-Agent).
5. `iter_records(manifest)` yielding `("skillFields/<name>", provenance)` for `skillFields`, `agentFields`, `hooks`, `tools`, `limits`; `("invisibleSources/<path>", …)`; and `("frontmatter", …)` / `("layout", …)` for the two singleton blocks.
6. `_section_text(provenance) -> tuple[str | None, str | None]` returning `(text, reason)`: `selector` is unsupported and returns `"selector-not-supported"`, a fetch failure returns `"fetch-failed: …"`, a missing anchor returns `"anchor-not-found"`.
7. `fill(path)` — loads, dumps to a dict, fills `hash` and `checkedAt` only for records whose `hash` is `None`, revalidates through `Manifest.model_validate`, writes through `dump_manifest`, returns 1 if any record failed.
8. `verify(path)` — recomputes every hash, builds `status.drift` entries (`hash-missing`, `anchor-not-found`, `fetch-failed: …`, `section-text-changed`), sets `status.stale` to `bool(drift)` and `status.verifiedAt` to today, writes through `dump_manifest`, returns 1 if drift is present.
9. `main(argv)` — `argparse` with `fill` and `verify` subcommands, each taking a `path`; `raise SystemExit(main())` under `__main__`.

A record is addressed inside the dumped dict by group and key: `name` for every list except `invisibleSources`, which uses `path`; `frontmatter` and `layout` are single mappings, not lists.

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_spec_provenance.py -v`
Expected: PASS

- [ ] **Step 5: Type-check the script**

`make check` runs mypy over `src` and `tests` only. Run it explicitly once:

Run: `uv run mypy scripts/spec_provenance.py`
Expected: `Success: no issues found`

- [ ] **Step 6: Commit**

```bash
git add scripts/spec_provenance.py tests/unit/test_spec_provenance.py
git commit -m "feat(specs): add documentation provenance fill and verify script

Refs #2"
```

---

### Task 4: Generated JSON Schema

**Files:**
- Create: `specs/schema/environmentspec.v1alpha1.json`
- Modify: `Makefile`

The test already exists (Task 2, `test_committed_schema_matches_models`).

- [ ] **Step 1: Add the Makefile target**

Insert after `format`:

```makefile
.PHONY: spec-schema
spec-schema: ## Regenerate the manifest JSON Schema from the Pydantic models
	$(UV) run python -c "from pathlib import Path; \
from agent_skill_adapter.specs.models import json_schema_text; \
p = Path('specs/schema/environmentspec.v1alpha1.json'); \
p.parent.mkdir(parents=True, exist_ok=True); \
p.write_text(json_schema_text(), encoding='utf-8')"
```

- [ ] **Step 2: Generate and verify**

Run: `make spec-schema && uv run pytest tests/unit/test_specs.py::test_committed_schema_matches_models -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add Makefile specs/schema
git commit -m "feat(specs): generate and commit the manifest JSON Schema

Refs #2"
```

---

### Task 5: Baseline spec — `specs/agentskills/1.0.0`

The baseline comes first: Claude Code's `extends` cannot resolve without it, and portability is derived from it.

**Files:**
- Create: `specs/agentskills/1.0.0/spec.yaml`
- Modify: `tests/unit/test_specs.py`

**Sources** — the snapshot from Task 1, never a fresh fetch:

| Block | Snapshot file | `provenance.url` | Anchor |
|-------|---------------|------------------|--------|
| `skillFields` | `agentskills-specification.*` | `https://agentskills.io/specification` | `#name-field`, `#description-field`, `#license-field`, `#compatibility-field`, `#metadata-field`, `#allowed-tools-field` |
| `frontmatter` | `agentskills-validator.py` (evidence) + `.html` | `https://agentskills.io/specification` | `#validation` |
| `layout` | `agentskills-specification.*` | `https://agentskills.io/specification` | `#directory-structure` |
| `limits` | `agentskills-specification.*` | `https://agentskills.io/specification` | `#progressive-disclosure` |

- [ ] **Step 1: Read the snapshot**

```bash
SNAP=.cache/spec-sources/$(ls .cache/spec-sources | sort | tail -1)
cat "$SNAP/as-frontmatter.md"
cat "$SNAP/NOTES.md"
grep -nE 'ALLOWED_FIELDS|MAX_[A-Z_]+ *=' "$SNAP/agentskills-validator.py"
```

If `$SNAP` does not exist, Task 1 was skipped — go back and do it; do not substitute a `curl` here.

- [ ] **Step 2: Write `specs/agentskills/1.0.0/spec.yaml` with `url` and `anchor`, no hashes**

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: agentskills
  version: 1.0.0
  labels:
    vendor: agentskills
    role: baseline
  annotations:
    adapter.prgate.io/changelog: CHANGELOG.md
    adapter.prgate.io/upstream-commit: <SHA from Task 1 step 2>
spec:
  environment:
    versions: "*"
  validForDays: 90
  frontmatter:
    unknownFields: reject
    provenance:
      url: https://agentskills.io/specification
      anchor: "#validation"
  layout:
    skillFile: [SKILL.md, skill.md]
    skillsDirs:
      - {path: .agents/skills, scope: project}
      - {path: ~/.agents/skills, scope: user}
    conventionalDirs: [scripts, references, assets]
    provenance:
      url: https://agentskills.io/specification
      anchor: "#directory-structure"
  skillFields:
    - name: name
      kind: string
      required: true
      constraints:
        minLength: 1
        maxLength: 64
        pattern: "^[a-z0-9]+(-[a-z0-9]+)*$"
        matchesDirectoryName: true
      stability: stable
      effect: Identifies the skill; loaded into the catalog at session start.
      provenance:
        url: https://agentskills.io/specification
        anchor: "#name-field"
    - name: metadata
      kind: map
      valueKind: string
      openKeys: true
      required: false
      stability: stable
      effect: Client-specific properties outside the open spec.
      provenance:
        url: https://agentskills.io/specification
        anchor: "#metadata-field"
    - name: allowed-tools
      kind: string
      required: false
      stability: experimental
      effect: Space-separated tool patterns the skill may use without approval.
      provenance:
        url: https://agentskills.io/specification
        anchor: "#allowed-tools-field"
  limits:
    - name: skill_file_lines
      value: 500
      unit: lines
      enforcement: recommended
      provenance:
        url: https://agentskills.io/specification
        anchor: "#progressive-disclosure"
    - name: skill_body_tokens
      value: 5000
      unit: tokens
      enforcement: recommended
      provenance:
        url: https://agentskills.io/specification
        anchor: "#progressive-disclosure"
    - name: catalog_entry_tokens
      value: 100
      unit: tokens
      enforcement: recommended
      provenance:
        url: https://agentskills.io/specification
        anchor: "#progressive-disclosure"
status:
  stale: false
```

Add the remaining `skillFields` — `description` (required, 1–1024), `license`, `compatibility` (1–500) — in the same shape, each with its own anchor. `tools` and `invisibleSources` stay absent: the open specification names no tools and no out-of-repository configuration, and an empty list would claim it had been checked.

`validForDays: 90` applies here too: the open specification moves, and a baseline nobody re-verified is exactly as untrustworthy as a stale source spec.

- [ ] **Step 3: Confirm the snapshot still matches the live pages**

`fill` is the one networked step here. Before running it, prove the live pages still equal the snapshot, so the hash it writes describes the text that was actually read:

```bash
SNAP=.cache/spec-sources/$(ls .cache/spec-sources | sort | tail -1)
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

A `CHANGED` line is not automatically a problem — these pages carry build ids and timestamps, so the raw bytes drift while the section text does not. It is a warning: after `fill`, re-read that page's section in the snapshot and confirm the record still says what the section says. If the section text itself moved, re-run Task 1 and redo the authoring from the fresh snapshot.

- [ ] **Step 4: Verify it loads, fill the hashes, canonicalize**

```bash
uv run python -c "from pathlib import Path; from agent_skill_adapter.specs import load_manifest; \
m = load_manifest(Path('specs/agentskills/1.0.0/spec.yaml')); print(len(m.spec.skill_fields), 'fields')"
uv run python scripts/spec_provenance.py fill specs/agentskills/1.0.0/spec.yaml
uv run python -c "from pathlib import Path; from agent_skill_adapter.specs import dump_manifest, load_manifest; \
p = Path('specs/agentskills/1.0.0/spec.yaml'); p.write_text(dump_manifest(load_manifest(p)), encoding='utf-8')"
```

Expected: the record count prints, then one `filled` line per record, exit 0. An `anchor-not-found` line means the anchor is wrong — fix the anchor, do not delete the record.

- [ ] **Step 5: Add the baseline tests**

Append to `tests/unit/test_specs.py`:

```python
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
```

- [ ] **Step 6: Run and commit**

Run: `make check`

```bash
git add specs/agentskills tests/unit/test_specs.py
git commit -m "feat(specs): publish the Agent Skills baseline spec 1.0.0

Refs #2"
```

---

### Task 6: Claude Code spec — `specs/claude-code/1.0.0`

**Files:**
- Create: `specs/claude-code/1.0.0/spec.yaml`
- Delete: `specs/anthropic/.gitkeep` (design D6 renames the directory)
- Modify: `tests/unit/test_specs.py`

**Sources** — the snapshot from Task 1:

| Block | `provenance.url` | Anchor |
|-------|------------------|--------|
| `skillFields`, `limits`, `frontmatter`, `layout` | `https://code.claude.com/docs/en/skills` | `#frontmatter-reference` and the neighbouring sections |
| `tools` | `https://code.claude.com/docs/en/tools-reference` | the heading `id` above the tool table, written down in Task 1 step 4 |
| `invisibleSources` | `https://code.claude.com/docs/en/settings` | `#settings-files-and-who-they-affect` |
| `invisibleSources` (CLAUDE.md) | `https://code.claude.com/docs/en/memory` | the section naming the user-level file |
| `invisibleSources` (managed policy) | `https://code.claude.com/docs/en/managed-settings` | `#delivery-mechanisms` |

- [ ] **Step 1: Read the snapshot**

```bash
SNAP=.cache/spec-sources/$(ls .cache/spec-sources | sort | tail -1)
cat "$SNAP/cc-frontmatter.md"
cat "$SNAP/cc-tool-names.txt"
cat "$SNAP/NOTES.md"
```

Record one `FieldRecord` per frontmatter key the snapshot documents. At the time this plan was written that was: `name`, `description`, `when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`, `user-invocable`, `allowed-tools`, `disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`, `hooks`, `paths`, `shell`, `metadata`, `license`, `compatibility`. **Take the real list from `cc-frontmatter.md`** — the snapshot is the source of truth, this plan is not. In particular `isolation` appears in the PRD but not in the documentation; a key with no documented section has no provenance and is not recorded.

Do **not** write a `portable` flag on any record. Portability is derived (design D8) and the models have no field to read it from; an authored flag is an `extra="forbid"` load error.

`since` carries a version only where the documentation states one (for example `background` requires v2.1.218+); otherwise omit it. `stability: experimental` only where the documentation itself flags the field as unstable.

- [ ] **Step 2: Write `specs/claude-code/1.0.0/spec.yaml`**

Same shape as the baseline, with `metadata.labels.role: source`, `metadata.labels.vendor: anthropic`, `spec.extends: agentskills@1.0.0`, and `spec.environment.versions` set from the version of Claude Code the documentation describes. If the page states no range, use the lowest version any `since` on the page names as the lower bound and the next minor as the upper bound, and say so in `CHANGELOG.md` (Task 7).

`limits` records only limits whose unit is `bytes`, `chars`, `tokens` or `lines`, each with `enforcement: hard` or `recommended` as the documentation states. A documented limit with any other unit (for example "up to 6 stacked skills") is not recorded in 1.0.0.

`tools` records one entry per name in `cc-tool-names.txt`, all citing the same tool-table anchor.

- [ ] **Step 3: Verify, fill, canonicalize**

The same commands as Task 5 steps 3 and 4, with the Claude Code path. The load step now also exercises `extends`: a failure naming `spec.extends` means the baseline directory or its `role` label is wrong, not that the Claude Code spec is.

- [ ] **Step 4: Add the derived-portability test**

Append to `tests/unit/test_specs.py`:

```python
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
```

- [ ] **Step 5: Remove the superseded placeholder, run and commit**

```bash
git rm specs/anthropic/.gitkeep
make check
git add specs/claude-code tests/unit/test_specs.py
git commit -m "feat(specs): publish Claude Code environment spec 1.0.0

Refs #2"
```

---

### Task 7: Changelogs, version locks and the immutability test

**Files:**
- Create: `specs/agentskills/CHANGELOG.md`, `specs/agentskills/versions.lock`
- Create: `specs/claude-code/CHANGELOG.md`, `specs/claude-code/versions.lock`
- Modify: `tests/unit/test_specs.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_specs.py`:

```python
LOCKS = sorted(SPECS.glob("*/versions.lock"))


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


def test_every_published_environment_has_a_lock() -> None:
    environments = {p.parent.parent.name for p in SPECS.glob("*/*/spec.yaml")}
    locked = {p.parent.name for p in LOCKS}
    assert environments == locked, f"unlocked environments: {sorted(environments - locked)}"


@pytest.mark.parametrize("lock_path", LOCKS)
def test_published_versions_are_immutable(lock_path: Path) -> None:
    """A published version directory must never change (FR-5); publish a new one instead."""
    entries = read_lock(lock_path)
    assert entries, f"{lock_path} must pin at least one published version"
    for version, digest in entries.items():
        directory = lock_path.parent / version
        assert directory.is_dir(), f"{lock_path} pins missing directory {version}"
        assert directory_hash(directory) == digest, (
            f"{directory} changed after publication; publish a new version directory instead"
        )
```

- [ ] **Step 2: Write both changelogs**

`specs/agentskills/CHANGELOG.md`:

```markdown
# Agent Skills baseline spec — changelog

Each published version directory is immutable. A correction is a new version
next to the old one; `versions.lock` pins the content of every published
directory.

## 1.0.0 — 2026-09-13

First published document. Baseline for `spec.extends`; the portability of every
other environment's frontmatter is derived from it (design D8).

- Upstream: `agentskills/agentskills` at commit `<SHA>`; the repo has no tags,
  so the commit is the version. Recorded in
  `metadata.annotations.adapter.prgate.io/upstream-commit`.
- `environment.versions: "*"` — the open specification is not versioned per
  environment release.
- `skillFields`: the six keys the specification defines.
- `frontmatter.unknownFields: reject` — the behaviour of the reference
  validator (`skills-ref`, `ALLOWED_FIELDS`). The client guide's
  warn-and-load recommendation is a different claim and is not recorded here.
- `limits`: the three recommendations under progressive disclosure.
- `tools`, `invisibleSources`: absent — the specification names neither.
```

`specs/claude-code/CHANGELOG.md` follows the same shape: the environment range with its justification, what each block covers, that portability is derived rather than authored, which limits were dropped for want of a usable unit, and that subagent fields (1.1.0) and hooks (1.2.0) are not covered.

- [ ] **Step 3: Generate both locks**

```bash
uv run python - <<'LOCKS'
from pathlib import Path

from agent_skill_adapter.specs.loader import directory_hash

HEADER = (
    "# sha256 of each published spec version directory. A published directory is\n"
    "# immutable: to correct a record, publish a new version next to it.\n"
    "# Regenerate after publishing a new version with:\n"
    '#   uv run python -c "from pathlib import Path; '
    "from agent_skill_adapter.specs.loader import directory_hash; "
    "print(directory_hash(Path('specs/<env>/<version>')))\"\n"
)
for env in sorted({p.parent.parent for p in Path("specs").glob("*/*/spec.yaml")}):
    versions = sorted(p for p in env.iterdir() if p.is_dir())
    lines = [f"{d.name} {directory_hash(d)}" for d in versions]
    (env / "versions.lock").write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    print(env / "versions.lock")
LOCKS
```

- [ ] **Step 4: Run and commit**

Run: `uv run pytest tests/unit/test_specs.py -v && make check`

```bash
git add specs/agentskills/CHANGELOG.md specs/agentskills/versions.lock \
        specs/claude-code/CHANGELOG.md specs/claude-code/versions.lock \
        tests/unit/test_specs.py
git commit -m "feat(specs): pin published spec versions and add the changelogs

Refs #2"
```

---

### Task 8: Green gates and PR readiness

- [ ] **Step 1: Run the full gate**

Run: `make check`
Expected: exit 0. Fix anything reported; do not weaken a rule to pass.

- [ ] **Step 2: Confirm the provenance script still agrees with both published specs**

```bash
uv run python scripts/spec_provenance.py verify specs/agentskills/1.0.0/spec.yaml
uv run python scripts/spec_provenance.py verify specs/claude-code/1.0.0/spec.yaml
git diff --stat specs/
```

Expected: exit 0 each, no drift lines. Both runs rewrite `status.verifiedAt`. If only `status` changed, keep the change, regenerate both locks (Task 7 step 3), and re-run `make check`. If `spec` changed, `dump_manifest` is wrong — fix it rather than commit the churn.

- [ ] **Step 3: Confirm no dependency was added**

Run: `git diff main -- pyproject.toml uv.lock`
Expected: empty.

- [ ] **Step 4: Commit leftovers and push**

```bash
git add -A
git commit -m "chore(specs): refresh provenance verification timestamps

Refs #2"
git push
```

- [ ] **Step 5: Mark PR #45 ready and update its body**

```bash
gh pr ready 45
```

Summarize in the body: the manifest envelope and why it is Kubernetes-shaped; the baseline spec and derived portability (D7, D8); the loader's refusal modes; the provenance hash contract; what the two 1.0.0 documents cover and what is deferred to 1.1.0/1.2.0; the immutability rule. Link the design document.

---

## Self-Review

**Spec coverage:**

| Design section | Task |
|----------------|------|
| §3 layout, immutability, `metadata.version` rule | 2 (version rule), 7 (locks) |
| §4 envelope, camelCase, `extra="forbid"`, `constraints`/`stability`/`enforcement`/`frontmatter`/`layout` | 2 |
| §4 derived portability (D8) | 2 (`portable_fields`), 6 (test) |
| §5 provenance script, hash contract, edge rules | 3 |
| §6 models, validators, loader, comparator, `dump_manifest`, schema | 2, 4 |
| §7 tests | 2, 3, 5, 6, 7 |
| §8 baseline contents | 1 (raw material), 5 (records) |
| §8 Claude Code contents | 1 (raw material), 6 (records) |
| §9 scope, `spec-schema` target, issue comment | 4, 8 |

The issue #2 comment recording D6 and D3 is already posted, so §9's last item needs no task.

**Known gaps accepted:** the `selector` branch of the provenance script returns `selector-not-supported`; both 1.0.0 documents use anchors only, and the design defers selector support to pages that need it. The baseline's `agentskills-validator.py` is read as evidence but never hashed: it is not HTML, and the record stating the unknown-field policy cites the rendered `#validation` section instead.
