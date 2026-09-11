"""Unit tests for repository governance and AI agent constitution."""

from pathlib import Path


def test_agents_constitution_exists_and_line_limit() -> None:
    """AGENTS.md must exist at repo root, not exceed 120 lines, and contain core sections."""
    repo_root = Path(__file__).resolve().parents[2]
    agents_md = repo_root / "AGENTS.md"

    assert agents_md.is_file(), "AGENTS.md does not exist at repo root"
    content = agents_md.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) <= 120, f"AGENTS.md exceeds 120 lines (got {len(lines)})"
    assert len(lines) > 0, "AGENTS.md is empty"

    # Verify required Core Rails and safety protocols are codified
    required_clauses = [
        "Think Before Coding",
        "Simplicity First",
        "Surgical Changes",
        "Continuous Verification",
        "Dual-Loop Execution Protocol",
        "Outer Loop",
        "Inner Loop",
        "Cognitive Friction Protocol",
        "Level 1",
        "Level 2",
        "Level 3",
        "Mandatory Git & Worktree Discipline",
        "Worktree Isolation",
        "Language Policy",
    ]
    for clause in required_clauses:
        assert clause in content, f"Missing required clause '{clause}' in AGENTS.md"


def test_claude_symlink() -> None:
    """CLAUDE.md must be a valid relative symlink pointing to AGENTS.md."""
    repo_root = Path(__file__).resolve().parents[2]
    claude_md = repo_root / "CLAUDE.md"

    assert claude_md.is_symlink(), "CLAUDE.md is not a symlink"
    target = claude_md.readlink()
    assert target == Path("AGENTS.md"), f"CLAUDE.md target is {target}, expected AGENTS.md"
    assert claude_md.resolve() == (repo_root / "AGENTS.md").resolve()
    assert claude_md.is_file(), "CLAUDE.md does not resolve to an existing file"


def test_gemini_symlink() -> None:
    """GEMINI.md must be a valid relative symlink pointing to AGENTS.md."""
    repo_root = Path(__file__).resolve().parents[2]
    gemini_md = repo_root / "GEMINI.md"

    assert gemini_md.is_symlink(), "GEMINI.md is not a symlink"
    target = gemini_md.readlink()
    assert target == Path("AGENTS.md"), f"GEMINI.md target is {target}, expected AGENTS.md"
    assert gemini_md.resolve() == (repo_root / "AGENTS.md").resolve()
    assert gemini_md.is_file(), "GEMINI.md does not resolve to an existing file"


def test_agent_roles_documentation_exists() -> None:
    """docs/governance/agent-roles.md must exist and describe required agent roles."""
    repo_root = Path(__file__).resolve().parents[2]
    roles_md = repo_root / "docs" / "governance" / "agent-roles.md"

    assert roles_md.is_file(), "docs/governance/agent-roles.md does not exist"
    content = roles_md.read_text(encoding="utf-8").strip()
    assert len(content) > 0, "docs/governance/agent-roles.md is empty"

    # Verify required roles and contract specifications
    required_roles = ["Orchestrator", "Coder", "Validator", "Healer"]
    for role in required_roles:
        assert role in content, f"Missing required role '{role}' in agent-roles.md"
