"""Smoke tests for package initialization and CLI entrypoint."""

from typer.testing import CliRunner

import agent_skill_adapter
from agent_skill_adapter.cli.main import app

runner = CliRunner()


def test_package_version() -> None:
    """Verify package version is defined."""
    assert agent_skill_adapter.__version__ == "0.1.0"


def test_cli_help() -> None:
    """Verify CLI --help runs cleanly."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Universal adapter and compiler between agent skill standards." in result.output
