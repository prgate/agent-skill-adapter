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
## Agent Skill Adapter — Autopilot Notes

Adapter that moves Claude Code agent configuration into Google Antigravity and reports what
is lost in transit. Offline, deterministic. For skill authors and CI.

### Commands

| Command | Purpose |
|---------|---------|
| `make install` | Install dependencies and dev tools |
| `make check` | Lint, typecheck, tests |
| `make test` | Run the test suite |

### How Autopilot works here

Сборка ведётся навыком `/autopilot`. Требования, спецификация и таски — в `.autopilot/`.
Прогресс — `.autopilot/dashboard.html`. Правило: требование из `manifest.md`
может снять только пользователь.

Если работа продолжается — скажи «продолжи автопилот»: состояние поднимется
из `.autopilot/state.js`, переспрашивать ничего не нужно.
<!-- autopilot:end -->
