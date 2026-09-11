"""Unit tests for repository governance and AI agent constitution."""

from pathlib import Path


def test_agents_constitution_exists_and_line_limit() -> None:
    """AGENTS.md must exist at repo root and not exceed 120 lines."""
    repo_root = Path(__file__).resolve().parents[2]
    agents_md = repo_root / "AGENTS.md"

    assert agents_md.is_file(), "AGENTS.md does not exist at repo root"
    lines = agents_md.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 120, f"AGENTS.md exceeds 120 lines (got {len(lines)})"
    assert len(lines) > 0, "AGENTS.md is empty"


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
    """docs/governance/agent-roles.md must exist and be non-empty."""
    repo_root = Path(__file__).resolve().parents[2]
    roles_md = repo_root / "docs" / "governance" / "agent-roles.md"

    assert roles_md.is_file(), "docs/governance/agent-roles.md does not exist"
    content = roles_md.read_text(encoding="utf-8").strip()
    assert len(content) > 0, "docs/governance/agent-roles.md is empty"
