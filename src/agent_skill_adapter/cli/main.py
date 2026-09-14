"""CLI entrypoint for agent-skill-adapter."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agent_skill_adapter import __version__
from agent_skill_adapter import convert as convert_module

# ponytail: found beside the source tree, which holds for a checkout and for the editable
# install this project uses. A wheel that shipped the descriptions as package data would
# read them through `importlib.resources` instead.
SPECS = Path(__file__).resolve().parents[3] / "specs"
"""The descriptions this repository ships, so that the working directory does not decide.

A relative default means a different tree in every folder the command is run from, and the
one it usually finds is none: the run then ends at exit code 3 saying the descriptions
could not be read -- the same code as a skill the descriptions leave undecided. Two very
different answers under one number, and the one that is about the caller's folder rather
than about their skill is the one that reads as a verdict it is not.
"""

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
    specs: Annotated[Path, typer.Option(help="Tree of environment descriptions.")] = SPECS,
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
    saved = False
    if report is not None:
        try:
            report.write_text(
                json.dumps(result.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            saved = True
        except OSError as error:
            # Left to itself this is a traceback, and a traceback exits 1 -- the code for a
            # transfer that lost something, which is an answer about the skill given for a
            # mistake in the arguments. The report itself is still issued (FR-26), on the
            # stream it would have taken had `--report` not been given. A run that was
            # already stopped keeps the code of what stopped it: FR-27 gives the run the
            # earliest stop, and this is the latest thing that can go wrong.
            unstopped = result.exit_code in convert_module.UNSTOPPED
            result = convert_module.refused(
                result,
                convert_module.REPORT_UNWRITABLE if unstopped else result.exit_code,
                f"{report}: the report could not be written here ({error}), "
                "so it went to standard output instead",
            )
    sys.stderr.write(result.summary)
    if not saved:
        sys.stdout.write(json.dumps(result.report, indent=2, ensure_ascii=False) + "\n")
    raise typer.Exit(result.exit_code)


if __name__ == "__main__":
    app()
