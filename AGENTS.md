# AI Agent Constitution

## 1. Core Rails
- **Think Before Coding**: Verify assumptions and formulate Definition of Done (DoD) before writing code.
- **Simplicity First (KISS / DRY)**: Minimum code to solve the task. Zero speculative abstractions or dead code.
- **Surgical Changes**: Touch only what is necessary. Never modify or reformat unrelated working code.
- **Continuous Verification**: Every code change must be validated by automated tests and static analyzers.

## 2. Multi-Agent Roles
- **Orchestrator**: Decomposes tasks, formulates implementation plans, manages state, coordinates subagents.
- **Coder**: Implements clean, production-ready code adhering strictly to specifications.
- **Validator**: Executes tests, linters, and type checkers to verify compliance.
- **Healer**: Diagnoses test failures/stack traces and applies targeted fixes (max 3 retries).
*Detailed role boundaries and contracts: `docs/governance/agent-roles.md`.*

## 3. Dual-Loop Execution Protocol
- **Outer Loop (Target & Contract Management)**:
  1. Input: Task/Issue specification.
  2. Plan: Draft implementation plan (`implementation_plan.md`) and obtain user approval.
  3. Execute: Perform surgical implementation via isolated subagents.
  4. Verify: Run quality gates and produce evidence in `walkthrough.md`.
- **Inner Loop (Autonomous Code Refinement)**:
  1. Trigger: File modification or test execution.
  2. Validate: Run `make check` (Ruff, Mypy Strict, Pytest).
  3. Self-Heal: On failure (exit code != 0), Healer inspects error traces and applies surgical fixes (max 3 attempts).
  4. Escalate: If failures persist after 3 retries, trigger CFP Level 3 Force Stop.

## 4. Cognitive Friction Protocol (CFP)
- **Level 1 (Autonomous / Low Risk)**: Read files, search codebase, run read-only commands, run tests, plan edits.
- **Level 2 (Notify / Medium Risk)**: Create new files, bump versions of already-declared dependencies. Log in summary.
- **Level 3 (Force Stop / Critical Risk)**: Require explicit human confirmation before:
  - Deleting >3 files.
  - Modifying `.env`, secret configurations, or database migrations.
  - Executing `git push` to remote repositories.
  - Adding a new third-party dependency (install-time code execution widens the supply-chain surface).

## 5. Mandatory Git & Worktree Discipline
- **Worktree Isolation**: All work on non-main branches must occur in a dedicated `.worktrees/<name>` worktree, where `<name>` is a short task slug (issue or PR number, e.g. `.worktrees/issue8`) — never the branch name, which contains `/`. The root directory must remain clean on `main`.
- **Branch Naming**: Strict Conventional Branch format: `<type>/<kebab-case>` (`feature/`, `bugfix/`, `hotfix/`, `release/`, `chore/`).
- **Commit Format**: Strict Conventional Commits: `<type>[(scope)]: <description>` (e.g., `feat(governance): add constitution`).
- **PR-Only Delivery**: All changes must land on `main` via reviewed Pull Requests with passing CI.
- **Cleanup**: Worktrees must be removed upon PR merge (`git worktree remove .worktrees/<name>`).

## 6. Language Policy
- **Repository Artifacts**: Code, docstrings, comments, documentation, commit messages, and PR titles must be 100% English, except where Russian is already the record: `.autopilot/` (the run record), `docs/prd/`, and the Russian READMEs — root `README.md`, paired with the English `README.en.md`, and `docs/README.md`. A link to another language version is labeled in that language and does not count as prose.
- **User Dialogue**: Interactive chat responses and planning discussions should match the user's preferred language.

## 7. Test Discipline
- **Write a test only when it can fail on wrong behavior**: branching, format parsing, computation, a trust boundary, money or permissions, or a fixed bug (regression test). Such a test is mandatory.
- **Do not test what is already visible**: file existence, a heading in a document, a plain getter, a library call with no logic of our own, a constant's value. Those tests catch no defects and turn documentation edits into test repair.
- **Rule of thumb**: if a test can fail only from renaming or rewriting text, and not from incorrect code behavior, it is noise — do not write it.
- **Minimum for nontrivial logic**: one runnable test, the smallest one that fails when the logic breaks. Not a suite per function, and no fixtures or frameworks beyond what the project already uses.
- **Documentation is not pinned by tests**: the structure and content of documents are verified by reading them in review.

<!-- autopilot:start -->
## Agent Skill Adapter

Reads vendor documentation of two agent environments into machine-checkable YAML descriptions, computes entry by entry what Google Antigravity does not reproduce from Claude Code, then carries a whole set of assets — skills, subagents, commands, rule files, a plugin manifest — over that comparison. Offline and deterministic: same descriptions in, same report bytes out.

### Commands
- `make install` — `uv sync`; `make pre-commit-run` — CI runs this before `make check`.
- `make check` — the gate: ruff, `ruff format --check`, mypy strict over `src tests`, pytest.
- `make test` / `make lint` / `make format` — subsets; one file is `uv run pytest tests/unit/test_convert.py`.
- `uv run agent-skill-adapter convert [skill-dir] --source anthropic/claude-code@2.1.0 --target google/antigravity@2.0.0 [--skills DIR] [--agents DIR] [--commands DIR] [--rules FILE] [--plugin FILE] [--translation FILE] [--specs specs] [--report FILE] [--out DIR | --install] [--scope project|user] [--allow-stale]` — the composition options are repeatable (`--plugin` and `--translation` are not) and any part may be absent; the positional argument is one skill folder. The JSON report goes to stdout (or to `--report`), the same run in words to stderr, and the verdict becomes exit code 0, 1 or 3 — a refusal replaces it with its own code (see Pitfalls). Without `--out` or `--install` nothing is written anywhere; `--install` writes into the target's live roots and prints the plan first.
- `uv run python -m agent_skill_adapter.envspec.gaps [--root specs] [--out specs/gaps]` — rebuild the gap report.
- `make schema` — regenerate `specs/schema/envspec.schema.json` from the model (`envspec/schema.py`).
- `uv run python -m agent_skill_adapter.envspec.freshness [--root specs] [--write]` — re-fetch vendor docs; the only command that uses the network.

### Structure
- `src/agent_skill_adapter/envspec/` — descriptions and their comparison; `rules.py`, `assets.py` and `convert.py` sit beside it and depend on it, never the reverse; `cli/main.py` is a typer app with `--version` and the one `convert` command. `specs/<vendor>/<environment>-<version>.yaml` — hand-written descriptions; `specs/gaps/` and `specs/schema/` — generated, never hand-edited. `rules/claude-code-to-antigravity-1.0.yaml` — the translation rules, versioned apart from the descriptions.
- `docs/adr/0001..0015` hold why each rule is what it is; `docs/converting-a-real-skill.md` records three real `convert` runs and `docs/live-acceptance.md` the procedure for asking the live Antigravity CLI what it loaded — their commands need `--allow-stale` from 2026-10-14, when the descriptions fall due for a re-check. `contracts/`, `examples/` and `tests/{e2e,transforms,fixtures}/` are `.gitkeep` placeholders; only `tests/unit/` holds tests.

### Key files
- `envspec/model.py` — the pydantic schema: `EnvSpec`, `Source`, `Capability` (`kind` is a closed `Literal`: `skill-field`, `subagent-field`, `hook-event`, `hook-decision`, `settings-file`; `values` is the closed value set the documentation names, absent meaning it names none), `LayoutEntry`, `Limit`, `InvisibleSource`, `Discrepancy`, `Support`, `DiscrepancyKind`.
- `envspec/normalize.py` — `section_text(markdown, anchor)`, `normalize(text)`, `digest(text)`, `AnchorError`.
- `envspec/loader.py` — `load(path)`, `load_all(root)`, `select(root, vendor, environment, version, *, allow_stale=False, today=None)`, `is_stale(spec, today)`, `capability(spec, capability_id) -> Support`, `base_specs(spec, root, ...) -> tuple[EnvSpec, ...]` (the chain the optional model field `extends: <vendor>/<environment>@<version>` names, nearest first, `()` when it names nothing), `is_inherited(bases, entry_id, *, among="capabilities"|"layout") -> bool` (membership by id inside that one list, never by the base's `support`); raises `InvalidSpec`, `InvalidVersion`, `SpecNotFound`, `AmbiguousSpec`, `StaleSpec`, `ExtendsCycle`.
- `envspec/gaps.py` — `compare(source, target, bases=()) -> GapReport`, `render_markdown`, `render_json`, `report_from(root)`, `main`; `Outcome` is `reproduced|missing|unknown|out-of-scope`, `Origin` is `specification|extension` (which of the source's entries the extended open specification declares).
- `rules.py` — `load(path) -> Rules`; `Rules.version`, `.value_of(entry_id, value)`, `.tool_name(name)`, `.ignored(rel)`, `.rewritable(rel)`, `.undocumented`; raises `InvalidRules`. What a value or a name becomes lives here, never in code.
- `assets.py` — `read(Inputs) -> tuple[Asset, ...]`; `Inputs(translation, skills=(), skill=(), agents=(), commands=(), rules=(), plugin=None)`, `Asset(kind, path, name, frontmatter, findings)`, `Kind` is `skill|subagent|command|rules-file|manifest`, `Finding(found_as, ids, note)`, `frontmatter(path, *, required=())`; raises `ReadError`. An `Asset` whose `name` is empty is the named part itself, not an entity.
- `convert.py` — `convert(inputs, source, target, *, root="specs", out=None, install=False, scope=Scope.PROJECT, allow_stale=False) -> Conversion(verdict, exit_code, report, summary)`; `Verdict` is `clean|lossy|undecidable` (no `blocked` value until FR-36 defines a prohibition), `verdict_of(outcome, origin)` is the assembly table, `worst(verdicts)` calls an empty set `clean`, `refusal(...)` builds the report for what never started; also `Assessed`, `ConvertError(message, exit_code)`, `Scope`, `ROOT_ENTRY`/`PLUGIN_INSIDE` (which layout id each kind is written under), `REPORT_SCHEMA` (2).
- `envspec/freshness.py` — `check(spec, *, fetch, today=None) -> list[Discrepancy]`, `record(path, discrepancies)`, `markdown_url(source)`, `main(argv=None, *, fetch=_fetch)`.

### Architecture
- An `EnvSpec` describes one environment over one `version_range`: `schema_version`, `vendor`, `environment`, `checked_at`, `stale_after_days` (30), `normalization: v1`, then `sources`, `capabilities`, `layout`, `limits`, `invisible_sources`, `discrepancies`. The schema is closed (`extra="forbid"`), ids are unique per list, and every `source_id` must name a declared source. Tool-name mapping is not a field here: it is a mapping, not a property of an environment.
- A `Source` pins one documentation section by `anchor` and the sha256 of its normalized text; hashes are taken from the markdown twin `<url>.md`, never from HTML, because HTML moves with styling. `retrieved_from` is `web` (the default) or `shipped` — a section read from a file the environment installs, which `freshness` skips because there is no page to re-fetch.
- Flow: `load` → `select` by dotted-numeric version (the nearest description is never substituted) → `compare` matches source entries to target entries by id, within `capabilities` and `layout` only. The outcome follows what the target documents: `supported` → reproduced, `unsupported` → missing, `unknown` or no such entry → unknown. Silence is never read as a denial, so an entry the target omits is never `missing`.
- Staleness needs no network — a recorded discrepancy, or `checked_at` older than `stale_after_days` — and `select` refuses a stale description unless `allow_stale=True`; `freshness` is the only module allowed to import network libraries, and it takes `fetch` as a parameter so nothing below it, and no test, needs a network.
- `assets` reads the named parts of the set into findings (every frontmatter key, bundled directory, top-level file, declared hook event, command file, rule file, manifest field), each spelled as an entry id (`skill.frontmatter.<key>`, `skill.dir.<name>`, `skill.top.<name>`, `subagent.frontmatter.<key>`, `command.file`, `rules.file`, `settings.file.plugin-manifest.<field>`, `hook.event.<name>`); `convert` only looks those ids up in `compare`'s result, swapping in the id of the *place* for a kind whose own id no description carries (`ASKS_ITS_PLACE`: a rule file is judged by `rules.project`, there being no `rules.file` anywhere) — it compares nothing itself and keeps no list of known names, so a name nobody documented becomes an `unknown`/`extension` row rather than vanishing. A declared hook asks two ids: its event, and `hook.decision.block` (ADR-0007 — firing an event is not the power to veto).
- The report is `report_schema: 2`: `outcome`, `exit_code`, `source`, `target`, `rules_version`, `translations` (every applied rule: what was written, what it became, by which rule), `links` (every rewritten address), `assets` (`{kind, path, name, assembled_name, verdict, properties}` per entity), `written`, `advice`, `error`. The run's verdict is the worst over the entities, an entity's over its rows; `summary` opens with `the set: <verdict> (exit N)`.
- The assembly table (PRD §5.2, ADR-0006): `reproduced`/`out-of-scope` → clean/0, `missing` → lossy/1, `unknown` → lossy/1 on an `extension` but undecidable/3 on a `specification` entry, because a target silent about a format it claims to implement leaves nothing to judge. A run's verdict is the worst of its properties.
- A value crosses only through the closed `values` set of the target's own entry: in the set → carried, outside it → the translation rules name the counterpart, and a counterpart the target's set does not carry is refused. The same ladder rewrites a rule file's `trigger` (ADR-0009), a subagent's `model` (ADR-0008) and its tool names, and the *form* of a value under `subagent.frontmatter.tools.form` — `comma-separated string` → `list`, which is what decides whether the target reads the subagent at all.
- With `--out` or `--install`, every destination comes from the target's `layout` (`skills.*`, `skill.file`, `skill.dir.*`, `agents.*`, `rules.project` at either level, `hooks.*`) with `<skill-name>`, `<plugin-name>`, `<workspace-root>` and `~` expanded — no path is ever spelled in the converter. A command has no entry anywhere and is written nowhere; a kind the target names no root for earns a row plus `lossy`, never a refusal, which would cost the rest of the set its rows; a path no description declares is staged under `--out` beside the part it came from and never in a root the target scans for entities. The whole plan is checked for collisions and for escapes out of its root before the first byte is written, an `undecidable` run assembles nothing, and a hook entry is staged beside the skill for a person to merge by hand.
- A composition that names a manifest crosses as a plugin: the manifest is rewritten to the fields the target's description declares and nothing else, and every other kind leaves its own root for the plugin folder (`plugin.dir.skills|agents|rules` under `plugins.project`/`plugins.user`). The plugin's own `hooks.json` and `mcp_config.json` are found through the `plugin.file.*` layout entries rather than by name, cross whole, and earn a line of advice: their contents become commands on somebody else's machine.

### Code conventions
- English everywhere except `.autopilot/` (Russian, the run record; excluded from ruff); ruff `line-length = 100`, target py310, rules `E W F I B UP`; mypy strict covers `src` and `tests`.
- Field names describe the description format, never one vendor's vocabulary — what an environment calls its own fields belongs in the YAML data; a deliberate simplification carries a `# ponytail:` comment naming its ceiling and upgrade path.

### Environment
- Python 3.10 (`.python-version`), uv-managed `.venv`; no environment variables, services or secrets. Dependencies: pydantic, pyyaml, typer, rich; dev: pytest, mypy, ruff, pre-commit — adding another is CFP Level 3.

### Tests
- Seven seams: `normalize` (text → hash), `loader` (tree → selection → staleness), `gaps` (`compare` on two tiny descriptions), `freshness` (injected `fetch`), `rules` (a rules file → its lookups), `assets` (a temporary set folder → entities), `convert` (a temporary set against two tiny descriptions — the internal steps are never tested apart from it).

### Pitfalls
- `AGENTS.md` must stay at 120 lines or fewer and `CLAUDE.md`/`GEMINI.md` must remain symlinks to it, or `tests/unit/test_governance.py` fails.
- Editing `model.py` leaves `specs/schema/envspec.schema.json` behind; `test_committed_schema_matches_the_model` catches it and the fix is `make schema`.
- Editing a description leaves `specs/gaps/*` behind; `test_committed_report_matches_the_descriptions_it_was_built_from` catches it and the fix is to re-run the `gaps` command.
- Importing `urllib`/`http`/`socket`/`requests`/`httpx` anywhere but `freshness.py` fails `test_only_the_freshness_module_may_reach_the_network`.
- Version comparison is dotted numbers only — no pre-release, no build metadata.
- Exit codes read backwards on purpose: `gaps.main` returns 1 when nothing is missing or unknown (the transfer would be a file copy), while `freshness.main` returns 0 even with discrepancies found, and 2 only for a missing or empty root.
- `convert` exits 0/1/3 with the verdict, 6 when an input was not read — a named path that is missing, a dangling or looping symlink, a file that is not UTF-8, a frontmatter value of the wrong type, a manifest that is not a JSON mapping, or the translation rules file failing to load — 7 when assembly could not write (a destination outside the root, `--out` together with `--install`, or a filesystem error mid-copy), 8 on a collision, 11 when `--report` could not be written; the last four are refusals, not verdicts, and leave the computed one alone — and 11 yields to any of the others. There is no code 2, and every outcome — refusals included — still prints a report, whose `error` field says why it is thin.
- Measured against the live `agy` 1.2.4 on 2026-09-17 (`docs/live-acceptance.md`), and stated in no vendor document: a subagent whose `tools` is one comma-separated string is not loaded at all, while the same file with `tools` as a list is — this is what the `subagent.frontmatter.tools.form` translation exists for.
- A file under `.agents/rules/` reaches the environment only with `trigger: always_on` in its header; without that key it sits on disk and is never read.
- The only way to ask the environment what it loaded is `agy --new-project -p='<question>'` from inside the workspace: without `--new-project` the workspace rules are not loaded at all, and the `agy agents` subcommand prints nothing and exits 0 whatever is on disk.

### How Autopilot works here
The build runs under the `/autopilot` skill: requirements, specification and tickets live in `.autopilot/`, progress in `.autopilot/dashboard.html`, state in `.autopilot/state.js` — asking to continue the autopilot restores it. Only the user may drop a requirement from `manifest.md`.
<!-- autopilot:end -->
