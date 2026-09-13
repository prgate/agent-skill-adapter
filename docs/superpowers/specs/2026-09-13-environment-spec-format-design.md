# Environment Spec Format and Claude Code Spec 1.0.0 — Design

- Issue: #2 (scope narrowed, see "Scope")
- PRD requirements covered: FR-1, FR-2, FR-3, FR-4, FR-5, FR-9, FR-11 (source half), FR-12, FR-15 (YAML safety), FR-17, FR-29, FR-32, FR-48 (groundwork)
- Status: approved design, implementation pending

## 1. Problem

The adapter's core input is an *environment spec*: a machine-readable, versioned
description of what an agent environment understands (frontmatter fields, tools,
limits, invisible configuration sources), where each record cites the official
documentation it was taken from. No such format exists yet, and there is no
loader that reads it deterministically. Issue #2 asks for the Anthropic spec; the
PRD (§1, FR-11) makes clear the source environment is **Claude Code** — the open
Agent Skills spec covers only `name` and `description`, and the product's value
lies in the Claude Code extensions on top of it.

## 2. Decisions

| # | Decision | Alternative rejected | Why |
|---|----------|----------------------|-----|
| D1 | Directory key is the **spec document version** (`specs/claude-code/1.0.0/`); the environment version range lives inside the document | Directory keyed by environment version range | A fix to a wrong record must produce a new document next to the old one (FR-5); keying by environment range would force overwriting |
| D2 | Provenance hashing script is **in scope** of #2 | Separate issue, ship with `hash: null` | Per FR-2 a record without anchor and hash is *unverified*; shipping 60 unverified records means reopening every one later |
| D3 | 1.0.0 covers **skill frontmatter, tools, limits, invisible sources** only; subagents → 1.1.0, hooks → 1.2.0 | Everything in 1.0.0 | Format gets validated on ~20 records before 60 are poured into it; each PR stays reviewable |
| D4 | **Pydantic models are the source of truth**; JSON Schema is generated from them and committed | Hand-written JSON Schema + `jsonschema` lib; or bare `yaml.safe_load` | One truth, typed object for the core, editor validation for authors, zero new dependencies |
| D5 | **Kubernetes-style manifest envelope** (`apiVersion`, `kind`, `metadata`, `spec`, `status`) | Flat document with `format_version` / `spec_version` | One envelope for specs, contracts (#4) and reports (FR-24); `spec` vs `status` separates human-authored content from machine-observed drift (FR-8); `v1alpha1` states honestly that the format is still moving |
| D6 | Path is `specs/claude-code/`, not `specs/anthropic/` as in the issue | Keep issue path | Environments are named by product; Anthropic may ship more than one |

## 3. Layout

```
specs/
  schema/
    environmentspec.v1alpha1.json    # generated from Pydantic; one file per (apiVersion, kind)
  claude-code/
    1.0.0/
      spec.yaml                      # one resource per file, no `---`
    CHANGELOG.md                     # human-readable diff between document versions
    versions.lock                    # sha256 of each published version directory
```

Rules:

- A published version directory is **immutable**. A correction is a new
  `1.0.1` next to it. `versions.lock` pins the content hash of every published
  directory; a test fails when a pinned directory changes. This is the one
  "text-pinning" test in the project and it is justified: it catches an FR-5
  violation, not a rename.
- `metadata.version` must equal the directory name; mismatch is a load error.

## 4. Manifest format (`apiVersion: adapter.prgate.io/v1alpha1`, `kind: EnvironmentSpec`)

```yaml
apiVersion: adapter.prgate.io/v1alpha1
kind: EnvironmentSpec
metadata:
  name: claude-code
  version: 1.0.0
  labels:
    vendor: anthropic
    role: source                     # source | target | both
  annotations:
    adapter.prgate.io/changelog: CHANGELOG.md
spec:                                # desired state — authored by humans (LLM draft, human review; FR-10)
  environment:
    versions: ">=2.1.200,<2.2.0"     # environment version range (FR-3)
  validForDays: 90                   # after checkedAt + validForDays the spec is stale (FR-9)
  skillFields:
    - name: context                  # frontmatter key verbatim
      kind: enum                     # string | bool | int | enum | list[string] | map
      values: [fork]                 # enum only
      required: false
      since: "2.1.100"               # first environment version with this field; null = always
      portable: false                # part of the open agentskills.io spec?
      effect: Runs the skill in a forked context; conversation history is not shared.
      provenance:
        url: https://docs.anthropic.com/.../skills
        anchor: "#context"           # exactly one of anchor | selector
        hash: sha256:9f2a…           # sha256 of the normalized section text
        checkedAt: 2026-09-13
  agentFields: []                    # populated in 1.1.0
  hooks: []                          # populated in 1.2.0
  tools:
    - name: Bash
      provenance: {…}
  limits:
    - name: skill_file_size
      value: 15000
      unit: bytes                    # bytes | chars | tokens (FR-32)
      provenance: {…}
  invisibleSources:                  # FR-17
    - path: ~/.claude/settings.json
      reason: user-level hooks and permissions live outside the repository
      provenance: {…}
status:                              # observed state — written only by the provenance script (FR-7/FR-8)
  verifiedAt: 2026-09-13
  stale: false
  drift: []                          # [{record: skillFields/context, expected: sha256:…, actual: sha256:…, reason: …}]
```

Borrowed from Kubernetes and why:

- `apiVersion`/`kind` — the loader picks the Pydantic model by this pair; an
  unknown pair is a refusal, not a crash on an unknown key. Maturity ladder:
  `v1alpha1` now, `v1` once three record classes (skill, agent, hook) have
  survived the format unchanged.
- `spec` vs `status` — drift found by the verification script is written into
  the file (FR-8) but into `status`, never mixed with content. In PR review a
  `spec` diff is read by a human, a `status` diff is mechanical.
- Lists keyed by `name` (`listType=map`) — duplicate `name` is a load error;
  canonical serialization sorts by `name` (FR-29).
- camelCase keys, as in Kubernetes and in Claude Code itself (`permissionMode`,
  `maxTurns`). Pydantic `alias_generator=to_camel`.
- Schema file plays the role of a CRD `openAPIV3Schema`: one per `kind` +
  `apiVersion`.
- One resource per file: diff and blame track one entity.

Not borrowed: `namespace`, `finalizers`, `ownerReferences`, `generation` —
nothing here needs them.

Record semantics:

- `portable: false` marks a Claude Code extension over the open spec. The set
  of such records is the raw material of the FR-48 gap list: each one needs a
  decision in the mapping contract (#4).
- `effect` is for humans and for the report ("what is lost"); the core never
  branches on it.
- There is **no support status** on a source record. Support is a property of
  the target environment and of the contract — the §5 vocabulary stays
  untouched.
- Unknown keys are rejected (`extra="forbid"`). A typo like `sinсe` fails the
  load with the record path, it does not become a silent `null`.

## 5. Provenance script — `scripts/spec_provenance.py`

Stdlib only (`urllib.request`, `html.parser`, `hashlib`, `argparse`). The core
stays offline (NFR-1); only this script touches the network.

```
python scripts/spec_provenance.py fill   specs/claude-code/1.0.0/spec.yaml
python scripts/spec_provenance.py verify specs/claude-code/1.0.0/spec.yaml
```

- `fill` — for every record whose `provenance.hash` is empty: fetch `url`, cut
  the section from the heading carrying `anchor` up to the next heading of the
  same or higher level, normalize, `sha256`, write `hash` and `checkedAt`.
  Records with a hash are left alone: a human writes `url` + `anchor`, the
  script fills in the mechanics.
- `verify` — recompute every hash and compare. A mismatch or an unreachable URL
  becomes an entry in `status.drift` and sets `status.stale: true`;
  `status.verifiedAt` is updated either way. Exit code 1 when drift is present,
  for the future FR-7 CI step (the CI step and the auto-PR of FR-8 are out of
  scope here).

Normalization — part of the hash contract, fixed in the script docstring:

1. HTML → text; tags dropped, `<code>` keeps its content.
2. Unicode NFC; `\r\n` → `\n`.
3. Runs of whitespace → one space; trim.
4. UTF-8 bytes → `sha256`, written with the `sha256:` prefix.

The hash changes only when section text changes, not when page layout does —
what the PRD calls a significant difference (FR-7).

Edge rules: anchor not found → `drift` entry with `reason: anchor-not-found`,
never skipped. Pages without anchors (SPA) may set `anchor: null` only together
with `selector` (a CSS path to the section); otherwise the load fails — FR-2
requires a section address. No significance threshold (§5): every mismatch is
drift; a threshold can come later.

Both commands write the file only through `dump_manifest` (see §6) so the diff
after a script run contains only the fields that changed.

## 6. Loader — `src/agent_skill_adapter/specs/`

**`models.py`** — Pydantic v2: `Manifest` (envelope), `Metadata`,
`EnvironmentSpec`, `FieldRecord`, `ToolRecord`, `LimitRecord`,
`InvisibleSource`, `Provenance`, `Status`, `DriftEntry`. Shared
`ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True, frozen=True)`.

Validators:

- `metadata.version` equals the parent directory name (checked in the loader,
  which knows the path).
- `name` unique within each list.
- `kind: enum` requires non-empty `values`; every other kind forbids `values`.
- exactly one of `provenance.anchor` / `provenance.selector`.

**`loader.py`**:

- `load_manifest(path) -> Manifest` — `yaml.safe_load` (no `!!python` tags,
  FR-15); `(apiVersion, kind)` looked up in a registry
  `{("adapter.prgate.io/v1alpha1", "EnvironmentSpec"): EnvironmentSpec}`;
  unknown pair → `UnsupportedManifestError(path)`. Pydantic errors are wrapped
  in `SpecLoadError(path, loc)` where `loc` is the record path
  (`spec.skillFields[3].since`).
- `select_spec(specs_dir, environment, version, *, today, pinned=None) -> Manifest`
  — reads `specs/<environment>/*/spec.yaml`, keeps those whose
  `spec.environment.versions` contains `version`. Zero → `NoMatchingSpecError`;
  more than one without `pinned` → `AmbiguousSpecError` listing the candidates;
  `pinned` selects one but does not lift staleness. Stale
  (`status.stale` or `checkedAt + validForDays < today`) → `StaleSpecError`.
  All three subclass `InsufficientDataError`, later mapped to exit code 3
  (FR-27). `today` is a parameter, never `date.today()` inside — otherwise the
  staleness test is nondeterministic.
- `dump_manifest(m) -> str` — canonical YAML: keys in model order, `name`-keyed
  lists sorted by `name`, `\n` line endings, UTF-8, no anchors/aliases.

Version range comparison: `packaging` is not a runtime dependency of the
project, so a minimal comparator over dotted integers with `>=`, `>`, `<`, `<=`,
`==` operators is implemented in the loader (~15 lines). No new dependency.

**`specs/schema/environmentspec.v1alpha1.json`** — produced by
`Manifest.model_json_schema()` via `make spec-schema`; a test asserts the
committed file equals the generated one.

No `ContractRegistry` (#5): `select_spec` covers the only query that exists
today. A registry appears when the contract (#4) starts looking up a pair of
specs.

## 7. Tests

Only tests that fail on wrong behavior:

| Test | Catches |
|------|---------|
| `specs/claude-code/1.0.0/spec.yaml` loads | a broken spec in the repo |
| duplicate `name`, unknown key, `enum` without `values`, `version` ≠ directory → `SpecLoadError` with `loc` | silent swallowing |
| `select_spec`: 0 / 1 / 2 matches, `pinned`, stale by date, stale by `status` | FR-4, FR-5, FR-9 |
| `dump_manifest(load_manifest(x)) == x` for 1.0.0 | non-deterministic serialization |
| HTML normalization: different markup, same text → same hash; different text → different hash | the hash contract |
| committed JSON Schema == generated | schema and models drifting apart |
| `versions.lock`: hash of `1.0.0/` unchanged | immutability violation (FR-5) |

Fixtures in `tests/fixtures/specs/`: one minimal broken manifest per error. The
only valid fixture is the real `specs/claude-code/1.0.0/spec.yaml`. Tests never
touch the network.

## 8. Contents of Claude Code spec 1.0.0

Taken from the official Claude Code documentation at the time of writing, each
with provenance:

- **skillFields** — every frontmatter key Claude Code documents for
  `SKILL.md` (the PRD counts eighteen: `name`, `description`, `allowed-tools`,
  `model`, `effort`, `context`, `agent`, `arguments`, `hooks`,
  `disable-model-invocation`, `user-invocable`, `background`, `isolation`, …).
  The exact list comes from the documentation, not from this document.
- **tools** — documented tool names (`Bash`, `Read`, `Edit`, `Write`, `Grep`,
  `Glob`, `Agent`, …).
- **limits** — documented size limits on `SKILL.md`, on the skill list, on
  total volume, where documented, with explicit units.
- **invisibleSources** — `~/.claude/settings.json`, `~/.claude/CLAUDE.md`,
  enterprise managed policy files.

## 9. Scope

In: everything in §3–§8, `Makefile` target `spec-schema`, a comment on issue #2
recording the path rename (D6) and the narrowed coverage (D3).

Out: subagent fields (1.1.0), hooks (1.2.0), the FR-7 CI step and FR-8
auto-PR, `ContractRegistry`, Markdown body parsing, drift significance
threshold (§5), any target-environment or contract work (#3, #4).

## 10. Files

- `specs/claude-code/1.0.0/spec.yaml`
- `specs/claude-code/CHANGELOG.md`
- `specs/claude-code/versions.lock`
- `specs/schema/environmentspec.v1alpha1.json`
- `src/agent_skill_adapter/specs/__init__.py`, `models.py`, `loader.py`
- `scripts/spec_provenance.py`
- `tests/unit/test_specs.py`, `tests/fixtures/specs/*.yaml`
- `Makefile` (+ `spec-schema`)

Estimate: ~2 days, half of it reading documentation and filling 1.0.0.
