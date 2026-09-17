"""CLI entrypoint for agent-skill-adapter."""

import json
import os.path
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agent_skill_adapter import __version__, assets, rules
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

RULES = Path(__file__).resolve().parents[3] / "rules" / "claude-code-to-antigravity-1.0.yaml"
"""The translation rules this repository ships, found the same way and for the same reason.

Only the default: ``--translation`` names another file, which is what a caller outside a
checkout of this repository has to do -- the path above is worked out from the source tree
and is a path to nowhere once the package is installed on its own.
"""


def _absolute(paths: list[Path] | None) -> tuple[Path, ...]:
    """Every path the caller named, spelled in full.

    A folder given as ``.`` has no last component to be named by, and the report names every
    entity of a set by the part it was read from -- so the spelling is settled here, once,
    before any of it reaches the reading.
    """
    return tuple(Path(os.path.abspath(path)) for path in paths or ())


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
    skill_dir: Annotated[Path | None, typer.Argument(help="One skill folder to read.")] = None,
    skills: Annotated[
        list[Path] | None, typer.Option("--skills", help="A folder of skill folders. Repeatable.")
    ] = None,
    agents: Annotated[
        list[Path] | None, typer.Option("--agents", help="A folder of subagents. Repeatable.")
    ] = None,
    commands: Annotated[
        list[Path] | None, typer.Option("--commands", help="A folder of commands. Repeatable.")
    ] = None,
    rule_files: Annotated[
        list[Path] | None, typer.Option("--rules", help="A rule file of the set. Repeatable.")
    ] = None,
    plugin: Annotated[
        Path | None, typer.Option("--plugin", help="The plugin manifest of the set.")
    ] = None,
    translation: Annotated[
        Path, typer.Option("--translation", help="The translation rules to read the set by.")
    ] = RULES,
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
        typer.Option(help="Assemble the set under this folder. Without it, nothing is written."),
    ] = None,
    install: Annotated[
        bool,
        typer.Option(
            "--install",
            help="Write into the live roots of the target environment instead of --out.",
        ),
    ] = False,
    scope: Annotated[
        convert_module.Scope,
        typer.Option(help="Which level of the target environment the layout is taken from."),
    ] = convert_module.Scope.PROJECT,
    allow_stale: Annotated[
        bool, typer.Option(help="Read a description that is due for a re-check.")
    ] = False,
) -> None:
    """Report what transferring a set of assets to another environment costs, and do it.

    The composition of the set is what the options name -- a folder of skills, of subagents,
    of commands, the rule files, the manifest -- and any part of it may be absent. The
    positional argument is one skill folder, which is a composition of one part and means
    what it has always meant.

    Standard output carries the JSON report and nothing else, so a caller can pipe it; the
    same run in words goes to the error stream. Nothing is written to the set or anywhere
    else unless `--out` names a folder to assemble into, and then only under that folder --
    or `--install` says to write into the roots the target environment reads, and then the
    plan reaches the error stream before the first byte of it is written.
    """
    try:
        translation_rules = rules.load(translation)
    except (rules.InvalidRules, OSError) as error:
        # A rules file that will not open or does not hold rules is an argument to correct,
        # and left to itself it is a traceback -- which exits 1, the code for a transfer that
        # lost something, and says nothing machine-readable at all. Every outcome of this
        # command is a report (FR-26), this one included.
        result = convert_module.refusal(
            source,
            target,
            convert_module.UNREADABLE,
            f"{translation}: the translation rules could not be read ({error})",
        )
    else:
        inputs = assets.Inputs(
            translation=translation_rules,
            skills=_absolute(skills),
            skill=_absolute([skill_dir] if skill_dir is not None else None),
            agents=_absolute(agents),
            commands=_absolute(commands),
            rules=_absolute(rule_files),
            plugin=None if plugin is None else Path(os.path.abspath(plugin)),
        )
        result = convert_module.convert(
            inputs,
            source,
            target,
            root=specs,
            out=out,
            install=install,
            scope=scope,
            allow_stale=allow_stale,
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
