"""Smoke tests for package initialization."""

import agent_skill_adapter


def test_package_version() -> None:
    """Verify package version is set."""
    assert agent_skill_adapter.__version__ == "0.1.0"
