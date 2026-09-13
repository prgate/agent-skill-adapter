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
- **Repository Artifacts**: Code, docstrings, comments, documentation, commit messages, and PR titles must be 100% English.
- **User Dialogue**: Interactive chat responses and planning discussions should match the user's preferred language.

## 7. Test Discipline
- **Write a test only when it can fail on wrong behavior**: branching, format parsing, computation, a trust boundary, money or permissions, or a fixed bug (regression test). Such a test is mandatory.
- **Do not test what is already visible**: file existence, a heading in a document, a plain getter, a library call with no logic of our own, a constant's value. Those tests catch no defects and turn documentation edits into test repair.
- **Rule of thumb**: if a test can fail only from renaming or rewriting text, and not from incorrect code behavior, it is noise — do not write it.
- **Minimum for nontrivial logic**: one runnable test, the smallest one that fails when the logic breaks. Not a suite per function, and no fixtures or frameworks beyond what the project already uses.
- **Documentation is not pinned by tests**: the structure and content of documents are verified by reading them in review.

<!-- autopilot:start -->
## Agent Skill Adapter

Reads vendor documentation of two agent environments into machine-checkable YAML descriptions, then computes entry by entry what Google Antigravity does not reproduce from Claude Code. Offline and deterministic: same descriptions in, same report bytes out.

### Commands
- `make install` — `uv sync`.
- `make check` — the gate: ruff, `ruff format --check`, mypy strict over `src tests`, pytest.
- `make test` / `make lint` / `make format` — subsets; one file is `uv run pytest tests/unit/test_envspec_gaps.py`.
- `make pre-commit-run` — CI runs this before `make check`.
- `uv run python -m agent_skill_adapter.envspec.gaps [--root specs] [--out specs/gaps]` — rebuild the gap report.
- `uv run python -m agent_skill_adapter.envspec.freshness [--root specs] [--write]` — re-fetch vendor docs; the only command that uses the network.
- `uv run agent-skill-adapter --version` — the installed CLI does nothing else yet.

### Structure
- `src/agent_skill_adapter/envspec/` — all working code; `cli/main.py` is a typer app with no subcommands.
- `specs/<vendor>/<environment>-<version>.yaml` — hand-written descriptions; `specs/gaps/` — generated, never hand-edited.
- `contracts/`, `examples/`, `docs/adr/`, `tests/{e2e,transforms,fixtures}/` — `.gitkeep` placeholders; only `tests/unit/` holds tests.

### Key files
- `envspec/model.py` — the pydantic schema: `EnvSpec`, `Source`, `Capability`, `LayoutEntry`, `Limit`, `ToolName`, `InvisibleSource`, `Discrepancy`, `Support`, `DiscrepancyKind`.
- `envspec/normalize.py` — `section_text(markdown, anchor)`, `normalize(text)`, `digest(text)`, `AnchorError`.
- `envspec/loader.py` — `load(path)`, `load_all(root)`, `select(root, vendor, environment, version, *, allow_stale=False, today=None)`, `is_stale(spec, today)`, `capability(spec, capability_id) -> Support`; raises `InvalidSpec`, `InvalidVersion`, `SpecNotFound`, `AmbiguousSpec`, `StaleSpec`.
- `envspec/gaps.py` — `compare(source, target) -> GapReport`, `render_markdown`, `render_json`, `report_from(root)`, `main`; `Outcome` is `reproduced|missing|unknown`.
- `envspec/freshness.py` — `check(spec, *, fetch, today=None) -> list[Discrepancy]`, `record(path, discrepancies)`, `markdown_url(source)`, `main(argv=None, *, fetch=_fetch)`.

### Architecture
- An `EnvSpec` describes one environment over one `version_range`: `schema_version`, `vendor`, `environment`, `checked_at`, `stale_after_days` (30), `normalization: v1`, then `sources`, `capabilities`, `layout`, `limits`, `tool_names`, `invisible_sources`, `discrepancies`. The schema is closed (`extra="forbid"`), ids are unique per list, every `source_id` must name a declared source, and `ToolName` is `from`/`to` in YAML but `from_name`/`to_name` in Python.
- A `Source` pins one documentation section by `anchor` and the sha256 of its normalized text; hashes are taken from the markdown twin `<url>.md`, never from HTML, because HTML moves with styling.
- Flow: `load` → `select` by dotted-numeric version (the nearest description is never substituted) → `compare` matches source entries to target entries by id, within `capabilities` and `layout` only.
- The outcome follows what the target documents: `supported` → reproduced, `unsupported` → missing, `unknown` or no such entry → unknown. Silence is never read as a denial, so an entry the target omits is never `missing`.
- Staleness needs no network: a recorded discrepancy, or `checked_at` older than `stale_after_days`. `select` refuses a stale description unless `allow_stale=True`.
- `freshness` is the only module allowed to import network libraries, and it takes `fetch` as a parameter so nothing below it — and no test — needs a network.

### Code conventions
- English everywhere except `.autopilot/` (Russian, the run record; excluded from ruff).
- ruff `line-length = 100`, target py310, rules `E W F I B UP`; mypy strict covers `src` and `tests`.
- Field names describe the description format, never one vendor's vocabulary — what an environment calls its own fields belongs in the YAML data.
- A deliberate simplification carries a `# ponytail:` comment naming its ceiling and upgrade path.

### Environment
- Python 3.10 (`.python-version`), uv-managed `.venv`; no environment variables, no services, no secrets in the repository.
- Dependencies: pydantic, pyyaml, typer, rich; dev: pytest, mypy, ruff, pre-commit. Adding another is CFP Level 3.

### Tests
- `make check` → ruff + mypy strict + 53 passed.
- Four seams: `normalize` (text → hash), `loader` (tree → selection → staleness), `gaps` (`compare` on two tiny descriptions), `freshness` (injected `fetch`).

### Pitfalls
- `AGENTS.md` must stay at 120 lines or fewer and `CLAUDE.md`/`GEMINI.md` must remain symlinks to it, or `tests/unit/test_governance.py` fails.
- Editing a description leaves `specs/gaps/*` behind; `test_committed_report_matches_the_descriptions_it_was_built_from` catches it and the fix is to re-run the `gaps` command.
- Importing `urllib`/`http`/`socket`/`requests`/`httpx` anywhere but `freshness.py` fails `test_only_the_freshness_module_may_reach_the_network`.
- Version comparison is dotted numbers only — no pre-release, no build metadata.
- Exit codes read backwards on purpose: `gaps.main` returns 1 when nothing is missing or unknown (the transfer would be a file copy), while `freshness.main` returns 0 even with discrepancies found, and 2 only for a missing or empty root.

### How Autopilot works here

Сборка ведётся навыком `/autopilot`. Требования, спецификация и таски — в `.autopilot/`.
Прогресс — `.autopilot/dashboard.html`. Правило: требование из `manifest.md`
может снять только пользователь.

Если работа продолжается — скажи «продолжи автопилот»: состояние поднимется
из `.autopilot/state.js`, переспрашивать ничего не нужно.
<!-- autopilot:end -->
