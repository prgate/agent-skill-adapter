"""Converting one skill folder: read what it holds, judge it, report, and say so in a code.

Three steps, one function. The folder is read into *findings* -- a frontmatter key, a
bundled directory, a declared hook event -- each of which names one or more entry ids of
the environment descriptions. :func:`envspec.gaps.compare` has already judged every entry
of the source environment against the target, so nothing here compares anything: it looks
up what the comparison concluded and applies the assembly table of PRD 5.2.

Nothing is written without ``out``. With it, the skill is assembled under that folder at
the paths the target description names -- every one of them read from its ``layout``, so
that what this command believes about the target environment is only ever what the
description says, and is re-checked when the description is.
"""

from __future__ import annotations

import codecs
import json
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from agent_skill_adapter.envspec.gaps import Gap, Origin, Outcome, compare
from agent_skill_adapter.envspec.loader import base_specs, select
from agent_skill_adapter.envspec.model import EnvSpec

REPORT_SCHEMA = 1
"""Version of the report format below. A field that changes meaning changes this number."""

REFERENCE = "vendor/environment@version, such as anthropic/claude-code@2.1.0"


class Verdict(str, Enum):
    """What one property, one file or one run amounts to. Three values, and no fourth.

    "The transfer is forbidden" is not here: no row of the assembly table produces it, and
    a value nobody ever returns is a branch nobody ever exercises. It arrives with FR-36,
    which is where a prohibition is defined in the first place.
    """

    CLEAN = "clean"
    LOSSY = "lossy"
    UNDECIDABLE = "undecidable"


SEVERITY = (Verdict.CLEAN, Verdict.LOSSY, Verdict.UNDECIDABLE)
"""Least to worst. The verdict of a file is the worst of its properties, and so for a run."""

EXIT_CODE = {Verdict.CLEAN: 0, Verdict.LOSSY: 1, Verdict.UNDECIDABLE: 3}
UNREADABLE = 6
"""The skill folder could not be read at all, so there was nothing to judge."""

UNWRITABLE = 7
"""The result did not pass the check made before writing, so nothing was written (FR-37)."""

COLLISION = 8
"""Something is already at a destination this run would have written."""

REPORT_UNWRITABLE = 11
"""The report was produced and the place named for it would not take it: row 11 of FR-27.

It stands over `UNSTOPPED` and over nothing else. Code 7 would have said the assembled skill
failed the check made before writing, which is a different thing and did not happen.
"""

UNSTOPPED = (EXIT_CODE[Verdict.CLEAN], EXIT_CODE[Verdict.LOSSY])
"""The codes of a run nothing stopped: the skill was judged and the code is its verdict.

Only these give way to something that goes wrong after the judgement. FR-27 gives the run
the code of whatever stopped it earliest, and a report that will not go where it was asked
for is the latest thing that can go wrong: 11 over a 3 or a 6 would answer about the report
to a caller asking what happened to the skill. Nothing is hidden by that -- the report
reaches standard output either way (FR-26), and its `error` names both reasons.
"""

REFUSAL_VERDICT = {EXIT_CODE[Verdict.UNDECIDABLE]: Verdict.UNDECIDABLE}
"""Which refusal codes are a verdict as well, written out rather than searched for.

A code answers "what stopped the run", a verdict answers "what does the transfer cost",
and the two happen to share the number 3: a run that cannot tell which environments it is
asked about has nothing to say about the skill either. Codes 6, 7 and 8 say the run could
not read or could not write, which is not a judgement about the skill, and leave the
verdict the assembly table computed exactly as it is. Reading this backwards out of
``EXIT_CODE`` would work only for as long as no two verdicts ever share a code, which is
a property of that table nobody promised.
"""

UNDECLARED = "no entry with this id in either description"
"""Why a property carries no words from either side: nobody documented it under that id."""

_HOW_TO_KEEP_A_HOOK = (
    "Move the rule into the body of the skill: prose the model may disregard is weaker "
    "than a hook by an order of magnitude, and it is not the same guarantee.",
    "Move the check into a pre-commit hook or a CI step: that works for checks over files "
    "only -- a hook that stops an action of the agent is nothing git ever sees.",
    "Fold the event onto the nearest one the target does document: it will fire more often "
    "than the original, which makes it a translation rule (FR-6), not a copy.",
)
"""The three ways to keep a hook the target does not reproduce, named and not chosen between.

FR-22 forbids this converter to read the command a hook runs, so it cannot tell which of
the three fits; the person reading the report can. Keyed by the kind of entry rather than
branched on, so the assembly rule stays the same rule for every kind of property.
"""

WORKAROUNDS: dict[str, tuple[str, ...]] = {
    "hook-event": _HOW_TO_KEEP_A_HOOK,
    "hook-decision": _HOW_TO_KEEP_A_HOOK,
}

BLOCK = "hook.decision.block"
"""Firing an event and stopping what it precedes are two entries, so a hook asks about both.

A target that documents the event says nothing by that about whether a hook of it can
refuse the tool call, so the two are graded apart. Why the descriptions carry the pair
split rather than the converter treating hooks specially is ADR-0007.
"""


class Scope(str, Enum):
    """Which level of the target environment the skill is assembled for.

    ``project`` by default: writing into someone's home folder because no level was named
    is changing their environment in passing.
    """

    PROJECT = "project"
    USER = "user"


SKILLS_ROOT = {Scope.PROJECT: "skills.project", Scope.USER: "skills.user"}
HOOKS_FILE = {Scope.PROJECT: "hooks.project", Scope.USER: "hooks.user"}
SKILL_FILE = "skill.file"
DIRECTORY = "skill.dir."
TOP = "skill.top."
"""Ids of what the skill folder holds. `skill.file.*` is taken: those are the skill file's
own fields, and a file called `README.md` is not one of them."""
EVENT = "hook.event."
"""Entry ids the assembly asks the target description for. Ids, and never paths.

Every path this command writes to is read from the ``layout`` of the target description
under one of these ids. A path spelled out here would be a claim about the target
environment kept out of the freshness check that guards every other such claim.
"""

SKILL_NAME = "<skill-name>"
WORKSPACE_ROOT = "<workspace-root>"
HOME = "~"
"""What a layout path may carry in place of a name or a root, expanded by the assembly."""

SKILL_MD = "SKILL.md"
HOOKS_KEY = "hooks"
"""The file and the frontmatter key of the source environment this command opens by name."""

SKILL_FILE_BYTES = 1024 * 1024
"""How much of a skill file this command reads before refusing to read any of it.

Not the size limit of an environment, which is the other limit a skill file has: that one
is a documented property of the target (FR-32 keeps it in the `limits` of a description),
a file past it is split rather than refused (FR-33), and exceeding it is its own outcome
with its own exit code 9 (NFR-2). This one is a guard on reading a stranger's repository,
so overrunning it is code 6 -- nothing was read, so there is nothing to judge. It guards
the reading and not the parsing: a file is measured before it is opened, or the folder
decides how many bytes this command pulls into memory before any limit is consulted.

# ponytail: one number for any skill file, whatever the target environment allows. The way
# up is to read the target's own limit out of the `limits` of its description (FR-32) and
# split what exceeds it (FR-33), after which this number goes back to guarding only how
# much of a stranger's file is pulled into memory.
"""

FRONTMATTER_BYTES = 64 * 1024
FRONTMATTER_DEPTH = 16
"""What a header may weigh and how deep it may nest before the file is refused (FR-15).

Both are far above anything a person writes and far below what would cost this command its
memory or its stack.
"""

# ponytail: named here because the format of the descriptions has no field for "this entry
# is required" -- the word lives in the prose of a `note`. The way up is a flag on
# `Capability`, after which this list is read off the descriptions rather than written here.
REQUIRED_FIELDS = ("description",)
"""The frontmatter keys a skill file must carry, taken from what the descriptions do mark.

Where the descriptions disagree, the environment that loads the file decides, because its
word is the refusal a person actually meets. The open specification decides where an entry
came from -- whether the target was obliged to document it -- and not what a runtime accepts.

`description` is here: the target description marks it required, the open specification
marks it required, and the source environment lets it fall back to the first non-empty line
of the body -- filling it in from there would be a translation rule (FR-6) this command does
not have. `name` is not, and the two sides do disagree about it: the open specification
marks it required and has it match the parent directory name, while both environments say it
defaults to the directory name when omitted. Both runtimes load such a file, so demanding it
here would refuse a skill file that works in either one.
"""


class ConvertError(Exception):
    """A refusal that still produces a report: the message says what is wrong and where."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class Finding:
    """One thing found in the skill folder, and the entry ids it asks the descriptions about."""

    found_as: str
    ids: tuple[str, ...]


@dataclass(frozen=True)
class Property:
    """One entry id the skill folder depends on, and what the two descriptions make of it."""

    id: str
    found_as: str
    outcome: Outcome
    origin: Origin
    verdict: Verdict
    source_says: str | None
    target_says: str | None
    note: str | None = None


@dataclass(frozen=True)
class Conversion:
    """The answer of one run: the verdict, the code it exits with, and both reports."""

    verdict: Verdict
    exit_code: int
    report: dict[str, Any]
    """The machine-readable report, issued on every outcome including a refusal."""
    summary: str
    """The same run in words, for a person reading the error stream."""


def verdict_of(outcome: Outcome, origin: Origin) -> Verdict:
    """The assembly table of PRD 5.2, one branch per row.

    ``missing`` is a loss and not a refusal because the target said so in words: a known
    loss can be weighed. ``unknown`` on an entry the open specification declares is a
    refusal because the target claims to implement that format, so its silence is a hole in
    its documentation rather than in ours -- and a permissive verdict on it would be a
    guess. ``unknown`` on an extension is the ordinary price of moving between two products.
    """
    if outcome in (Outcome.REPRODUCED, Outcome.OUT_OF_SCOPE):
        return Verdict.CLEAN
    if outcome is Outcome.MISSING:
        return Verdict.LOSSY
    return Verdict.LOSSY if origin is Origin.EXTENSION else Verdict.UNDECIDABLE


def worst(verdicts: Iterable[Verdict]) -> Verdict:
    """The heaviest verdict of the lot; nothing to judge is ``clean``, not undecidable.

    A skill that declares no property the descriptions know about loses nothing in the
    transfer, and there is nothing about it left to decide.
    """
    return max(verdicts, key=SEVERITY.index, default=Verdict.CLEAN)


class _Anchored(Exception):
    """The header declares a YAML anchor, at the line this carries.

    Its own exception rather than a ``yaml`` one: the header parses, and calling a refusal
    by rule a syntax error would send a person looking for a typo that is not there.
    """

    def __init__(self, line: int) -> None:
        super().__init__(f"line {line}")
        self.line = line


class _StrictLoader(yaml.SafeLoader):
    """A loader that refuses what a skill header may not contain: a repeated key, an anchor.

    PyYAML keeps the last of two equal keys and says nothing, which is how a frontmatter
    that sets ``model`` twice reaches a converter as one value nobody chose. An anchor and
    the alias repeating it are the same defect spelled differently: the text a person reads
    in the file and the value the parser builds stop being the same thing, and a converter
    that copied the file over would hand the target environment neither of them (FR-15).
    """

    def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
        node = super().compose_node(parent, index)
        # An alias can only repeat an anchor declared before it, so refusing every anchor as
        # it is registered refuses both -- and refuses them at the place the anchor is written,
        # which is the place a person has to edit.
        if self.anchors:
            raise _Anchored(0 if node is None else node.start_mark.line + 1)
        return node

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while reading the frontmatter",
                    node.start_mark,
                    f"key {key!r} is declared twice",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _depth(value: Any) -> int:
    """How deeply the loaded frontmatter nests, walked with a stack rather than by recursion.

    The depth is a limit on a file somebody else wrote, and a limit that overflows the
    interpreter's stack on the very input it guards against is not a limit.
    """
    deepest = 0
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        item, level = pending.pop()
        deepest = max(deepest, level)
        if isinstance(item, Mapping):
            pending += [(nested, level + 1) for nested in item.values()]
        elif isinstance(item, list):
            pending += [(nested, level + 1) for nested in item]
    return deepest


def _frontmatter(path: Path) -> dict[str, Any]:
    """The frontmatter of ``path``, or a refusal naming what is wrong and where.

    Every refusal here is structural: the file is not the shape a skill file has, so no
    part of it can be trusted to mean what it appears to mean.
    """
    if not path.is_file():
        raise ConvertError(f"{path}: no SKILL.md here, so this is not a skill folder", UNREADABLE)
    size = path.stat().st_size
    if size > SKILL_FILE_BYTES:
        raise ConvertError(
            f"{path}: the file is {size} bytes, past the {SKILL_FILE_BYTES} this command "
            "will read; a skill file that size is not one, and reading it to find out would "
            "be letting the folder decide how much memory the run takes",
            UNREADABLE,
        )
    raw = path.read_bytes()
    if raw.startswith(codecs.BOM_UTF8):
        raise ConvertError(
            f"{path}: the file opens with a UTF-8 byte order mark, so the `---` that opens "
            "the frontmatter is not the first byte; save the file without a BOM",
            UNREADABLE,
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConvertError(f"{path}: not UTF-8 text ({error})", UNREADABLE) from error
    if not text.startswith("---"):
        raise ConvertError(
            f"{path}: no frontmatter; a skill file opens with a `---` line", UNREADABLE
        )
    end = text.find("\n---", 3)
    if end < 0:
        raise ConvertError(
            f"{path}: the frontmatter opened on line 1 is never closed by a `---` line",
            UNREADABLE,
        )
    header = text[3:end]
    if len(header.encode("utf-8")) > FRONTMATTER_BYTES:
        raise ConvertError(
            f"{path}: the frontmatter is longer than {FRONTMATTER_BYTES} bytes, which is "
            "not a header any more; what belongs in the body of the skill goes below the "
            "closing `---` line",
            UNREADABLE,
        )
    try:
        # A header nested past what the parser itself can carry arrives as a `RecursionError`,
        # which is the depth limit being hit before this function gets to apply its own.
        loaded = yaml.load(header, _StrictLoader)
    except _Anchored as error:
        raise ConvertError(
            f"{path}: the frontmatter declares a YAML anchor on line {error.line}. Anchors "
            "and the aliases repeating them are valid YAML and are refused here all the "
            "same (FR-15): the text a person reads in the file and the value the parser "
            "builds stop being the same thing, and this command cannot carry both across",
            UNREADABLE,
        ) from error
    except (yaml.YAMLError, RecursionError) as error:
        raise ConvertError(
            f"{path}: the frontmatter is not valid YAML ({error})", UNREADABLE
        ) from error
    if not isinstance(loaded, dict):
        raise ConvertError(
            f"{path}: the frontmatter is not a mapping of keys "
            f"(it reads as {type(loaded).__name__})",
            UNREADABLE,
        )
    if _depth(loaded) > FRONTMATTER_DEPTH:
        raise ConvertError(
            f"{path}: the frontmatter nests deeper than {FRONTMATTER_DEPTH} levels; a skill "
            "header that deep is a data file, and reading one is not what this command does",
            UNREADABLE,
        )
    missing = [key for key in REQUIRED_FIELDS if key not in loaded]
    if missing:
        raise ConvertError(
            f"{path}: the frontmatter declares no "
            + " and no ".join(f"`{key}`" for key in missing)
            + "; the description of the target environment marks the field required, so "
            "there is nothing here that could be assembled for it, and a value invented "
            "for the field would be this command writing the skill rather than moving it",
            UNREADABLE,
        )
    return loaded


def _findings(skill_dir: Path) -> tuple[list[Finding], dict[str, Any]]:
    """Everything the folder holds that an environment has to reproduce, in the order found.

    Ids are built from the names as written -- ``skill.frontmatter.<key>``,
    ``skill.dir.<name>``, ``skill.top.<name>``, ``hook.event.<name>`` -- and no table of
    known names is kept.
    A name no description declares then reaches the report as a property nobody documented,
    which is the point: it must not vanish because we had not heard of it.
    """
    if not skill_dir.is_dir():
        raise ConvertError(f"{skill_dir}: no such folder", UNREADABLE)
    front = _frontmatter(skill_dir / SKILL_MD)
    findings = [Finding(f"frontmatter key `{key}`", (f"skill.frontmatter.{key}",)) for key in front]
    held = sorted(skill_dir.iterdir())
    findings += [
        Finding(f"bundled directory `{entry.name}/`", (f"{DIRECTORY}{entry.name}",))
        for entry in held
        if entry.is_dir()
    ]
    # Everything else at the top of the folder, the skill file aside: a README, a licence, a
    # diagram. Nothing says where they go in the target environment, and a file that fell out
    # of the report would be content lost under an exit code that called the transfer clean.
    findings += [
        Finding(f"top-level file `{entry.name}`", (f"{TOP}{entry.name}",))
        for entry in held
        if not entry.is_dir() and entry.name != SKILL_MD
    ]
    # ponytail: hooks are read from the frontmatter alone, which is where a skill declares
    # its own. Workspace-level hook files belong to the workspace, not to one skill folder,
    # and this command takes one skill folder (R07); reading them arrives with the workspace.
    declared = front.get(HOOKS_KEY)
    events = declared if isinstance(declared, Mapping) else {}
    findings += [
        Finding(
            f"hook event `{event}` declared in frontmatter key `hooks`",
            (f"hook.event.{event}", BLOCK),
        )
        for event in events
    ]
    return findings, front


def _kind(entry_id: str, gap: Gap | None) -> str:
    """What kind of entry an id names: the comparison's word for it, or the id's own shape.

    A hook event nobody wrote down carries no ``Gap`` to read a kind off, and it is exactly
    then that the ways of keeping the rule are worth printing. The ways out are earned by
    what the skill folder holds, not by whether a description happens to mention it.
    """
    if gap is not None:
        return gap.kind
    if entry_id == BLOCK:
        return "hook-decision"
    return "hook-event" if entry_id.startswith(EVENT) else ""


def _judge(
    findings: Sequence[Finding], gaps: Mapping[str, Gap]
) -> tuple[list[Property], list[str]]:
    """Every finding against the comparison, once per entry id, plus the advice it earns.

    An id the comparison does not carry is ``unknown`` from an ``extension``: the source
    description never declared it, so no open format ever promised it either, and nothing
    is known about what the target does with it. It still gets a row -- a property that
    fell out of the report silently is the one failure this command cannot be trusted after.

    One id, one row, however many findings asked about it: ``hook.decision.block`` is asked
    once by every declared hook, and the row names all of them. Naming the first and dropping
    the rest would read as though only that hook lost its veto.
    """
    asked_by: dict[str, list[str]] = {}
    for finding in findings:
        for entry_id in finding.ids:
            asked_by.setdefault(entry_id, []).append(finding.found_as)
    properties: list[Property] = []
    advice: list[str] = []
    for entry_id, found_as in asked_by.items():
        gap = gaps.get(entry_id)
        outcome = gap.outcome if gap is not None else Outcome.UNKNOWN
        origin = gap.origin if gap is not None else Origin.EXTENSION
        verdict = verdict_of(outcome, origin)
        properties.append(
            Property(
                id=entry_id,
                found_as=", ".join(found_as),
                outcome=outcome,
                origin=origin,
                verdict=verdict,
                source_says=gap.source_note if gap is not None else None,
                target_says=gap.target_note if gap is not None else None,
                note=None if gap is not None else UNDECLARED,
            )
        )
        if verdict is not Verdict.CLEAN:
            ways_out = WORKAROUNDS.get(_kind(entry_id, gap), ())
            advice += [line for line in ways_out if line not in advice]
    return properties, advice


def _layout(spec: EnvSpec, entry_id: str) -> str | None:
    """The path the description gives ``entry_id``, or ``None`` when it names none."""
    return next((entry.path for entry in spec.layout if entry.id == entry_id), None)


def _destination(template: str, skill_name: str) -> tuple[str, str]:
    """A layout path expanded twice: where it belongs, and where under ``out`` it is staged.

    A layout path opens with the root it is measured from: the workspace root, or the home
    folder for a user-level entry. The destination expands that root; the staged path drops
    it, because nothing is ever written outside ``out`` -- a command asked what a transfer
    costs must not reach into the caller's home folder on the way to answering.
    """
    path = template.replace(SKILL_NAME, skill_name)
    if path.startswith(f"{WORKSPACE_ROOT}/"):
        relative = path[len(WORKSPACE_ROOT) + 1 :]
        return relative, relative
    if path.startswith(f"{HOME}/"):
        relative = path[len(HOME) + 1 :]
        # Joined as text, not through Path: a destination is printed, not walked, and
        # Path would drop the trailing slash that says the entry is a directory.
        return f"{Path.home()}/{relative}", relative
    return path, path


@dataclass(frozen=True)
class _Part:
    """One file or directory of the assembled skill, and the two places it has."""

    label: str
    """Where it came from inside the skill folder."""
    destination: str
    """Where the target description says it belongs."""
    staged: Path
    """Where this run put it, always under ``out``."""
    copied_from: Path | None = None
    content: str | None = None
    """Set instead of ``copied_from`` when the part is written rather than copied."""


def _plan(
    skill_dir: Path,
    out: Path,
    target: EnvSpec,
    scope: Scope,
    properties: Sequence[Property],
    hooks: Mapping[str, Any],
) -> tuple[list[_Part], list[str]]:
    """What the assembly will write, before it writes anything, and what it asks of a person.

    A part the target description names no path for is not assembled: guessing where it
    goes would be inventing the target environment's layout. It keeps its row in the
    report, which is where its fate is read.
    """
    root = _layout(target, SKILLS_ROOT[scope])
    if root is None or _layout(target, SKILL_FILE) is None:
        raise ConvertError(
            f"{target.vendor}/{target.environment} names no place for a skill file at the "
            f"{scope.value} level, so there is nowhere to assemble into",
            EXIT_CODE[Verdict.UNDECIDABLE],
        )
    wanted = [(SKILL_FILE, SKILL_MD)]
    wanted += [
        (entry.id, f"{entry.id[len(DIRECTORY) :]}/")
        for entry in properties
        if entry.id.startswith(DIRECTORY)
    ]
    parts = []
    homeless = []
    for entry_id, label in wanted:
        inside = _layout(target, entry_id)
        if inside is None:
            homeless.append(label)
            continue
        destination, staged = _destination(f"{root.rstrip('/')}/{inside}", skill_dir.name)
        parts.append(_Part(label, destination, out / staged, copied_from=skill_dir / label))
    # Said out loud, because the list of what was written cannot say it: a part missing from
    # it looks the same whether the run had nowhere to put it or never got that far.
    asked = [
        f"`{label}` stayed in the skill folder: {target.vendor}/{target.environment} names "
        "no place for it, and a place picked for it here would be a guess about a layout "
        "only that environment's documentation can settle"
        for label in homeless
    ]
    hook_part = _hook_part(out, target, scope, properties, hooks)
    if hook_part is None:
        return parts, asked
    return parts + [hook_part], [
        *asked,
        f"the hook entry is staged at {hook_part.staged} and not merged into "
        f"{hook_part.destination}: that file belongs to the whole target environment and may "
        "already hold entries of its own, so add this one to it yourself",
    ]


def _hook_part(
    out: Path,
    target: EnvSpec,
    scope: Scope,
    properties: Sequence[Property],
    hooks: Mapping[str, Any],
) -> _Part | None:
    """The hook entry to carry over: the declared events the target fires, and nothing else.

    An event the target does not reproduce is left out of the file -- written there it would
    read as a guarantee the target never gave. It keeps its row in the report either way.
    """
    fires = {entry.id for entry in properties if entry.verdict is Verdict.CLEAN}
    carried = {name: value for name, value in hooks.items() if f"{EVENT}{name}" in fires}
    destination = _layout(target, HOOKS_FILE[scope])
    if not carried or destination is None:
        return None
    return _Part(
        f"frontmatter key `{HOOKS_KEY}`",
        destination,
        # The entry is staged beside the assembled skill under the name the target gives the
        # file it belongs in, never at the destination itself: merging into a file that may
        # already hold someone else's entries is FR-40.
        out / Path(destination).name,
        content=json.dumps({HOOKS_KEY: carried}, indent=2, ensure_ascii=False) + "\n",
    )


def _assemble(out: Path, parts: Sequence[_Part]) -> list[dict[str, str]]:
    """Copy or write every planned part, once the whole plan is known to be safe to write.

    Two questions are asked of every destination before the first byte of the first one is
    written: is the place free, and is it under ``out``. Both run over the whole plan, because
    a run that wrote two files and then refused the third would have done the damage it
    refused to do.

    A symbolic link counts as an occupied place even when it points at nothing: ``exists``
    answers ``False`` for a broken one, and writing to it would create its target somewhere
    the caller never named.
    """
    taken = [str(part.staged) for part in parts if part.staged.exists() or part.staged.is_symlink()]
    if taken:
        raise ConvertError(
            "there is already something at " + ", ".join(taken) + "; nothing was written, "
            "because a converted skill that silently replaced a result of an earlier run "
            "is indistinguishable from one that was never converted",
            COLLISION,
        )
    # `resolve` normalises `..` and follows links, so the three ways a destination can lead
    # out of `out` -- a layout path that is absolute, a skill folder named `..`, a link on
    # the way -- are one question asked once.
    # ponytail: checked and then written as two steps, so a link planted in between is not
    # caught; closing that needs writes that refuse to follow links (FR-14, path sandboxing).
    root = out.resolve()
    outside = [str(part.staged) for part in parts if not part.staged.resolve().is_relative_to(root)]
    if outside:
        raise ConvertError(
            ", ".join(outside) + f" is not under {out}; nothing was written, because the one "
            "promise this command makes about the caller's filesystem is that it writes "
            "under the folder the caller named and nowhere else",
            # The plan failed the check made before writing, which is its own outcome
            # (FR-37) and not a verdict: like an occupied destination, being unable to write
            # says nothing about what the skill costs to transfer. Exit code 3 here would
            # overwrite the answer the assembly table had already computed.
            UNWRITABLE,
        )
    for part in parts:
        part.staged.parent.mkdir(parents=True, exist_ok=True)
        if part.content is not None:
            part.staged.write_text(part.content, encoding="utf-8")
        elif part.copied_from is not None and part.copied_from.is_dir():
            shutil.copytree(part.copied_from, part.staged)
        elif part.copied_from is not None:
            shutil.copy2(part.copied_from, part.staged)
    return [
        {"from": part.label, "to": part.destination, "path": str(part.staged)} for part in parts
    ]


def _environment(text: str | None) -> dict[str, str] | None:
    """``vendor/environment@version`` split in three, or ``None`` when it is not that."""
    if text is None:
        return None
    head, _, version = text.partition("@")
    vendor, _, environment = head.partition("/")
    if not (vendor and environment and version):
        return None
    return {"vendor": vendor, "environment": environment, "version": version}


def _requested(text: str | None, flag: str) -> dict[str, str]:
    """The environment ``flag`` names, or a refusal. A version is never guessed (FR-4)."""
    named = _environment(text)
    if named is None:
        raise ConvertError(
            f"{flag} must name an environment as {REFERENCE}; got {text!r}",
            EXIT_CODE[Verdict.UNDECIDABLE],
        )
    return named


def _gaps(
    root: str | Path, source: str | None, target: str | None, allow_stale: bool
) -> tuple[dict[str, Gap], EnvSpec]:
    """What the comparison of the two named descriptions concluded, by entry id.

    Selection is :func:`loader.select`, so its refusals stand and all of them mean the same
    thing here: we do not know what these environments say, so we cannot decide anything
    about the skill. Every one of them is a ``ValueError`` by design of that module.
    """
    wanted = (_requested(source, "--source"), _requested(target, "--target"))
    try:
        source_spec, target_spec = [
            select(
                root,
                named["vendor"],
                named["environment"],
                named["version"],
                allow_stale=allow_stale,
            )
            for named in wanted
        ]
        bases = base_specs(source_spec, root, allow_stale=allow_stale)
    except ValueError as error:
        raise ConvertError(
            f"cannot read the environment descriptions under {root}: {error}",
            EXIT_CODE[Verdict.UNDECIDABLE],
        ) from error
    return {gap.id: gap for gap in compare(source_spec, target_spec, bases).gaps}, target_spec


def _report(
    skill_dir: Path,
    source: str | None,
    target: str | None,
    verdict: Verdict,
    exit_code: int,
    properties: Sequence[Property],
    advice: Sequence[str],
    written: Sequence[dict[str, str]],
    error: str | None,
) -> dict[str, Any]:
    """The machine-readable report. ``report_schema`` first, and ``error`` says why it is thin."""
    return {
        "report_schema": REPORT_SCHEMA,
        "outcome": verdict.value,
        "exit_code": exit_code,
        "source": _environment(source),
        "target": _environment(target),
        "skill": {"path": str(skill_dir), "name": skill_dir.name},
        "properties": [
            {
                "id": entry.id,
                "found_as": entry.found_as,
                "outcome": entry.outcome.value,
                "origin": entry.origin.value,
                "verdict": entry.verdict.value,
                "source_says": entry.source_says,
                "target_says": entry.target_says,
                "note": entry.note,
            }
            for entry in properties
        ],
        # Empty without `out`. It is a field and not an omission because a reader has to be
        # able to tell "wrote nothing" from "this report is of an older shape".
        "written": list(written),
        "advice": list(advice),
        # Not in the report sketch of the specification, and needed by the rule that a report
        # is issued on every outcome: a refusal whose reason reached only the error stream
        # would be a report that says "undecidable" and never says why.
        "error": error,
    }


def _summary(report: dict[str, Any]) -> str:
    """The same run in words: the verdict first, then one line per property, then the advice."""
    skill = report["skill"]["path"]
    lines = [f"{skill}: {report['outcome']} (exit {report['exit_code']})"]
    if report["error"]:
        lines.append(f"  {report['error']}")
    lines += [
        f"  {entry['verdict']:<12} {entry['id']} -- {entry['found_as']} "
        f"({entry['outcome']}, {entry['origin']})" + (f"; {entry['note']}" if entry["note"] else "")
        for entry in report["properties"]
    ]
    lines += [
        f"  wrote {entry['path']} (it belongs at {entry['to']})" for entry in report["written"]
    ]
    lines += [f"  advice: {line}" for line in report["advice"]]
    return "\n".join(lines) + "\n"


def refused(result: Conversion, exit_code: int, message: str) -> Conversion:
    """The same run, ending in something that went wrong after it: the report says what.

    Whatever happens to a conversion once it is computed -- a report that could not be put
    where it was asked for, and in time whatever else -- the answer a caller reads has to
    agree with itself. The code in the report, the code in the words for a person and the
    code the process exits with are one number, or the two streams describe different runs.
    The verdict is untouched: it is what the transfer costs, and that did not change.
    """
    report = dict(result.report)
    report["exit_code"] = exit_code
    report["error"] = f"{report['error']}; {message}" if report["error"] else message
    return Conversion(result.verdict, exit_code, report, _summary(report))


def convert(
    skill_dir: str | Path,
    source: str | None,
    target: str | None,
    *,
    root: str | Path = "specs",
    out: str | Path | None = None,
    scope: Scope = Scope.PROJECT,
    allow_stale: bool = False,
) -> Conversion:
    """Read the skill folder, judge every property it holds, and report what a transfer costs.

    ``source`` and ``target`` name the two environments as ``vendor/environment@version``;
    neither version is inferred, and a missing or unreadable one ends the run at
    ``undecidable`` rather than at a guess. A folder that is not shaped like a skill ends it
    at exit code 6. Both still produce a report: a run that refuses and says nothing
    machine-readable about the refusal cannot be acted on by whatever called it.

    Without ``out`` nothing is written and the report is the whole answer. With it, the skill
    is assembled under ``out`` at the paths the target description names, at the level
    ``scope`` chooses.
    """
    skill_dir = Path(skill_dir)
    properties: list[Property] = []
    advice: list[str] = []
    written: list[dict[str, str]] = []
    # Until the assembly table has judged something there is no verdict to keep, and
    # "we could not read enough to say" is what `undecidable` means. Once it has, that
    # verdict stands even if the run then fails to write: being unable to put the files
    # somewhere is not a judgement about what the skill loses in the transfer.
    verdict = Verdict.UNDECIDABLE
    try:
        gaps, target_spec = _gaps(root, source, target, allow_stale)
        findings, front = _findings(skill_dir)
        properties, advice = _judge(findings, gaps)
        verdict = worst(entry.verdict for entry in properties)
        # An undecidable run assembles nothing: the transferable half of a skill whose other
        # half nobody documented is a folder that looks converted and is not.
        if out is not None and verdict is not Verdict.UNDECIDABLE:
            declared = front.get(HOOKS_KEY)
            parts, asked = _plan(
                skill_dir,
                Path(out),
                target_spec,
                scope,
                properties,
                declared if isinstance(declared, Mapping) else {},
            )
            written = _assemble(Path(out), parts)
            advice += asked
    except ConvertError as error:
        # A refusal that exits with one of the table's own codes is that verdict: not
        # knowing where the skill goes is not knowing what the transfer amounts to. Which
        # codes those are is `REFUSAL_VERDICT`, and the rest leave the computed one alone.
        verdict = REFUSAL_VERDICT.get(error.exit_code, verdict)
        report = _report(
            skill_dir,
            source,
            target,
            verdict,
            error.exit_code,
            properties,
            advice,
            written,
            str(error),
        )
        return Conversion(verdict, error.exit_code, report, _summary(report))
    report = _report(
        skill_dir, source, target, verdict, EXIT_CODE[verdict], properties, advice, written, None
    )
    return Conversion(verdict, EXIT_CODE[verdict], report, _summary(report))
