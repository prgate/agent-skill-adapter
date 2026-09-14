"""CLI entrypoint for agent-skill-adapter."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agent_skill_adapter import __version__
from agent_skill_adapter import convert as convert_module

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


@app.command("convert")
def convert_command(
    skill_dir: Annotated[Path, typer.Argument(help="The skill folder to read.")],
    source: Annotated[
        str | None,
        typer.Option(help=f"Environment the skill comes from, as {convert_module.REFERENCE}."),
    ] = None,
    target: Annotated[
        str | None,
        typer.Option(help=f"Environment it is going to, as {convert_module.REFERENCE}."),
    ] = None,
    specs: Annotated[Path, typer.Option(help="Tree of environment descriptions.")] = Path("specs"),
    report: Annotated[
        Path | None,
        typer.Option(help="Write the JSON report here instead of to standard output."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(help="Assemble the skill under this folder. Without it, nothing is written."),
    ] = None,
    scope: Annotated[
        convert_module.Scope,
        typer.Option(help="Which level of the target environment the layout is taken from."),
    ] = convert_module.Scope.PROJECT,
    allow_stale: Annotated[
        bool, typer.Option(help="Read a description that is due for a re-check.")
    ] = False,
) -> None:
    """Report what transferring one skill folder to another environment costs, and do it.

    Standard output carries the JSON report and nothing else, so a caller can pipe it; the
    same run in words goes to the error stream. Nothing is written to the skill or anywhere
    else unless `--out` names a folder to assemble into, and then only under that folder.
    """
    result = convert_module.convert(
        skill_dir, source, target, root=specs, out=out, scope=scope, allow_stale=allow_stale
    )
    payload = json.dumps(result.report, indent=2, ensure_ascii=False) + "\n"
    if report is None:
        sys.stdout.write(payload)
    else:
        report.write_text(payload, encoding="utf-8")
    sys.stderr.write(result.summary)
    raise typer.Exit(result.exit_code)


if __name__ == "__main__":
    app()
