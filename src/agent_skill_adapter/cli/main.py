"""CLI entrypoint for agent-skill-adapter."""

import typer
from rich.console import Console

from agent_skill_adapter import __version__

app = typer.Typer(
    name="agent-skill-adapter",
    help="Universal adapter and compiler between agent skill standards.",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"agent-skill-adapter version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Universal adapter and compiler between agent skill standards."""


if __name__ == "__main__":
    app()
