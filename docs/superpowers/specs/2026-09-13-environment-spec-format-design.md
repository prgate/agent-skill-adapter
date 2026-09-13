# Environment Spec Format and Claude Code Spec 1.0.0 — Design

- Issue: #2 (scope narrowed, see "Scope")
- PRD requirements covered: FR-1, FR-2, FR-3, FR-4, FR-5, FR-9, FR-11 (source half), FR-12, FR-13 (layout half), FR-15 (YAML safety), FR-17, FR-29, FR-32, FR-48 (groundwork)
- Baseline: the open Agent Skills specification, https://github.com/agentskills/agentskills
- Status: approved design, implementation pending

## 1. Problem

The adapter's core input is an *environment spec*: a machine-readable, versioned
description of what an agent environment understands (frontmatter fields, tools,
limits, invisible configuration sources), where each record cites the official
documentation it was taken from. No such format exists yet, and there is no
loader that reads it deterministically. Issue #2 asks for the Anthropic spec; the
PRD (§1, FR-11) makes clear the source environment is **Claude Code** — the open
Agent Skills spec ([agentskills.io](https://agentskills.io), repo
[agentskills/agentskills](https://github.com/agentskills/agentskills)) defines
six frontmatter fields — `name`, `description`, `license`, `compatibility`,
`metadata`, `allowed-tools` — and the product's value lies in the Claude Code
extensions on top of them (`context`, `hooks`, `model`, …). The PRD's "two
fields" count in §1 is stale; the argument is unchanged.

## 2. Decisions

| # | Decision | Alternative rejected | Why |
|---|----------|----------------------|-----|
| D1 | Directory key is the **spec document version** (`specs/claude-code/1.0.0/`); the environment version range lives inside the document | Directory keyed by environment version range | A fix to a wrong record must produce a new document next to the old one (FR-5); keying by environment range would force overwriting |
| D2 | Provenance hashing script is **in scope** of #2 | Separate issue, ship with `hash: null` | Per FR-2 a record without anchor and hash is *unverified*; shipping 60 unverified records means reopening every one later |
| D3 | 1.0.0 covers **skill frontmatter, tools, limits, invisible sources** only; subagents → 1.1.0, hooks → 1.2.0 | Everything in 1.0.0 | Format gets validated on ~20 records before 60 are poured into it; each PR stays reviewable |
| D4 | **Pydantic models are the source of truth**; JSON Schema is generated from them and committed | Hand-written JSON Schema + `jsonschema` lib; or bare `yaml.safe_load` | One truth, typed object for the core, editor validation for authors, zero new dependencies |
| D5 | **Kubernetes-style manifest envelope** (`apiVersion`, `kind`, `metadata`, `spec`, `status`) | Flat document with `format_version` / `spec_version` | One envelope for specs, contracts (#4) and reports (FR-24); `spec` vs `status` separates human-authored content from machine-observed drift (FR-8); `v1alpha1` states honestly that the format is still moving |
| D6 | Path is `specs/claude-code/`, not `specs/anthropic/` as in the issue | Keep issue path | Environments are named by product; Anthropic may ship more than one |
| D7 | The open Agent Skills spec is a **third environment spec**, `specs/agentskills/1.0.0/`, `labels.role: baseline`, in scope of #2 | Hard-code the portable field list | Portability must be checkable against a cited source, and the baseline is the common denominator for every future target |
| D8 | `portable` is **derived** by the loader (`name` present in the baseline named by `spec.extends`), not authored | Hand-maintained `portable: bool` | A hand flag drifts silently; derivation is one set lookup and is tested |
| D9 | Record constraints, stability, limit enforcement, unknown-field policy and directory layout are **fields of the format** | Prose in `effect` | The open spec states hard constraints (`name` ≤ 64, regex, equals directory), soft limits (< 500 lines), an experimental field, and a strict reference validator; the core must branch on these, so they must be data |

## 3. Layout

```
specs/
  schema/
    environmentspec.v1alpha1.json    # generated from Pydantic; one file per (apiVersion, kind)
  agentskills/
    1.0.0/
      spec.yaml                      # baseline: the open Agent Skills spec, pinned to a repo commit
    CHANGELOG.md
    versions.lock
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
  extends: agentskills@1.0.0         # baseline spec; absent on the baseline itself
  environment:
    versions: ">=2.1.200,<2.2.0"     # environment version range (FR-3); "*" on the baseline
  validForDays: 90                   # after checkedAt + validForDays the spec is stale (FR-9)
  frontmatter:
    unknownFields: warn              # reject | warn | ignore — what the environment does with a key it does not know
    provenance: {…}
  layout:                            # where skills live (FR-13); each entry carries provenance
    skillFile: [SKILL.md, skill.md]
    skillsDirs:
      - {path: .claude/skills, scope: project}
      - {path: .agents/skills, scope: project}
      - {path: ~/.claude/skills, scope: user}
    conventionalDirs: [scripts, references, assets]
  skillFields:
    - name: name                     # frontmatter key verbatim
      kind: string                   # string | bool | int | enum | list[string] | map
      required: true
      constraints:                   # optional; only what the documentation states
        minLength: 1
        maxLength: 64
        pattern: "^[a-z0-9]+(-[a-z0-9]+)*$"
        matchesDirectoryName: true
      stability: stable              # stable | experimental
      since: null                    # first environment version with this field; null = always
      effect: Identifies the skill; loaded into the catalog at session start.
      provenance: {…}
    - name: metadata
      kind: map
      valueKind: string              # map only
      openKeys: true                 # map only: arbitrary keys allowed
      required: false
      stability: stable
      effect: Client-specific properties outside the open spec.
      provenance: {…}
    - name: context
      kind: enum
      values: [fork]                 # enum only
      required: false
      stability: stable
      since: "2.1.100"
      effect: Runs the skill in a forked context; conversation history is not shared.
      provenance:
        url: https://code.claude.com/docs/en/skills
        anchor: "#context"           # exactly one of anchor | selector
        hash: sha256:9f2a…           # sha256 of the normalized section text
        checkedAt: 2026-09-13
  agentFields: []                    # populated in 1.1.0
  hooks: []                          # populated in 1.2.0
  tools:
    - name: Bash
      provenance: {…}
  limits:
    - name: skill_file_lines
      value: 500
      unit: lines                    # bytes | chars | tokens | lines (FR-32)
      enforcement: recommended       # hard | recommended
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

- **Portability is derived, not authored.** `spec.extends` names the baseline
  (`agentskills@1.0.0`); the loader marks a `skillFields` record portable when a
  record with the same `name` exists in the baseline. Records that are not
  portable are the raw material of the FR-48 gap list: each one needs a
  decision in the mapping contract (#4). The baseline's `metadata` map
  (`openKeys: true`) is the open spec's official extension point and the
  obvious lowering target for those fields — a contract decision, recorded
  here only as a fact about the baseline.
- `constraints` carries only what the documentation states (length, pattern,
  directory match); `stability: experimental` marks fields the spec itself
  flags as unstable (`allowed-tools`). `limits[].enforcement` separates a hard
  limit from a recommendation (the open spec's "< 500 lines" is a
  recommendation; a target may make it hard).
- `frontmatter.unknownFields` records what the environment does with a key it
  does not know. The open spec's reference validator (`skills-ref`) rejects
  unknown keys; its client guide recommends warn-and-load. Both are cited; the
  baseline records the validator's behavior.
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
- `kind: map` requires `valueKind`; every other kind forbids `valueKind` and `openKeys`.
- `spec.extends`, when present, must resolve to an existing spec directory
  (`specs/<name>/<version>/spec.yaml`) whose `labels.role` is `baseline`; the
  baseline itself has no `extends`.

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
- `portable_fields(m, baseline) -> frozenset[str]` — names of `skillFields`
  present in both; the derived `portable` flag of D8.

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
| `specs/claude-code/1.0.0/spec.yaml` and `specs/agentskills/1.0.0/spec.yaml` load; `extends` resolves | a broken spec in the repo |
| duplicate `name`, unknown key, `enum` without `values`, `map` without `valueKind`, `version` ≠ directory, `extends` to a non-baseline → `SpecLoadError` with `loc` | silent swallowing |
| `portable_fields`: `name` in, `context` out | wrong derivation of the gap list |
| `select_spec`: 0 / 1 / 2 matches, `pinned`, stale by date, stale by `status` | FR-4, FR-5, FR-9 |
| `dump_manifest(load_manifest(x)) == x` for 1.0.0 | non-deterministic serialization |
| HTML normalization: different markup, same text → same hash; different text → different hash | the hash contract |
| committed JSON Schema == generated | schema and models drifting apart |
| `versions.lock`: hash of each published directory unchanged | immutability violation (FR-5) |

Fixtures in `tests/fixtures/specs/`: one minimal broken manifest per error. The
only valid fixtures are the real specs under `specs/`. Tests never
touch the network.

## 8. Contents of the 1.0.0 specs

### Baseline — `specs/agentskills/1.0.0/spec.yaml`

Source: `docs/specification.mdx` and `skills-ref/src/skills_ref/validator.py`
in [agentskills/agentskills](https://github.com/agentskills/agentskills),
pinned to one commit; provenance URLs point at `raw.githubusercontent.com`
blobs of that commit plus the rendered page on agentskills.io. The repo has no
tags, so `metadata.annotations.adapter.prgate.io/upstream-commit` records the
SHA.

- **skillFields** — `name` (required; 1–64, `^[a-z0-9]+(-[a-z0-9]+)*$`,
  equals directory), `description` (required; 1–1024), `license`,
  `compatibility` (1–500), `metadata` (`map`, `valueKind: string`,
  `openKeys: true`), `allowed-tools` (`experimental`; space-separated tool
  patterns).
- **frontmatter.unknownFields** — `reject` (reference validator
  `ALLOWED_FIELDS`).
- **layout** — `skillFile: [SKILL.md, skill.md]`; `skillsDirs`:
  `.agents/skills` (project), `~/.agents/skills` (user);
  `conventionalDirs: [scripts, references, assets]`.
- **limits** — `skill_file_lines` 500 (recommended), `skill_body_tokens` 5000
  (recommended), `catalog_entry_tokens` 100 (recommended).
- **tools**, **invisibleSources** — empty: the open spec names no tools and no
  out-of-repo configuration.

### Claude Code — `specs/claude-code/1.0.0/spec.yaml`

`extends: agentskills@1.0.0`. Taken from the official Claude Code
documentation (`code.claude.com/docs/en/skills` and neighbours) at the time of
writing, each record with provenance:

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
- **frontmatter.unknownFields** and **layout** — as documented
  (`.claude/skills`, `.agents/skills`, user-level equivalents).

## 9. Scope

In: everything in §3–§8 including the baseline spec, `Makefile` target `spec-schema`, a comment on issue #2
recording the path rename (D6) and the narrowed coverage (D3).

Out: subagent fields (1.1.0), hooks (1.2.0), the FR-7 CI step and FR-8
auto-PR, `ContractRegistry`, Markdown body parsing, drift significance
threshold (§5), any target-environment or contract work (#3, #4), running
`skills-ref validate` against adapter output (belongs to FR-43 / #4),
`strictyaml` as a dependency (FR-15 rules are implemented over
`yaml.safe_load`).

## 10. Files

- `specs/agentskills/1.0.0/spec.yaml`, `specs/agentskills/CHANGELOG.md`, `specs/agentskills/versions.lock`
- `specs/claude-code/1.0.0/spec.yaml`, `specs/claude-code/CHANGELOG.md`, `specs/claude-code/versions.lock`
- `specs/schema/environmentspec.v1alpha1.json`
- `src/agent_skill_adapter/specs/__init__.py`, `models.py`, `loader.py`
- `scripts/spec_provenance.py`
- `tests/unit/test_specs.py`, `tests/fixtures/specs/*.yaml`
- `Makefile` (+ `spec-schema`)

Estimate: ~2.5 days, half of it reading documentation and filling the two 1.0.0 specs.
