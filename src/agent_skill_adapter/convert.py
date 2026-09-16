"""Converting one asset set: read what it holds, judge it, report, and say so in a code.

Three steps, one function. :mod:`assets` reads the set into entities and each entity into
*findings* -- a frontmatter key, a bundled directory, a declared hook event, a path the
rules keep out -- each of which names the entry ids of the environment descriptions it
turns on. :func:`envspec.gaps.compare` has already judged every entry of the source
environment against the target, so nothing here compares anything: it looks up what the
comparison concluded and applies the assembly table of PRD 5.2.

One report over the whole set and one verdict, the worst of them: a run that answered per
entity would leave the caller adding up exit codes themselves. The rows are grouped by the
entity they were found in, so that a set of hundreds of files is still read by a person.

Nothing is written without ``out``. With it, each skill is assembled under that folder at
the paths the target description names -- every one of them read from its ``layout``, so
that what this command believes about the target environment is only ever what the
description says, and is re-checked when the description is.
"""

from __future__ import annotations

import json
import os.path
import re
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agent_skill_adapter.assets import (
    BLOCK,
    DROPPED,
    EMPTY,
    EVENT,
    FRONTMATTER_CLOSE,
    HOOKS_KEY,
    LINKED,
    PARTS,
    SKILL_DIR,
    SKILL_FRONTMATTER,
    SKILL_MD,
    SKILL_TOP,
    SUBAGENT_FRONTMATTER,
    Asset,
    Finding,
    Inputs,
    Kind,
    ReadError,
    read,
)
from agent_skill_adapter.assets import UNDECLARED as UNDECLARED_PATH
from agent_skill_adapter.envspec.gaps import Gap, Origin, Outcome, compare
from agent_skill_adapter.envspec.loader import base_specs, select
from agent_skill_adapter.envspec.model import EnvSpec, Support
from agent_skill_adapter.rules import TOOL_NAMES_ENTRY, Rules

REPORT_SCHEMA = 2
"""Version of the report format below. A field that changes meaning changes this number.

2: the report is of a set. The rows a run computes are grouped under the entity they were
found in (``assets``), where version 1 carried one ``skill`` and one flat ``properties``.
"""

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
"""The set could not be read at all, so there was nothing to judge."""

UNWRITABLE = 7
"""The result could not be written under ``out``, and no file of it was left there.

Either the plan failed the check made before the first byte (FR-37), so the writing never
began, or the writing itself was refused part way and every file it had put there was taken
back. What may remain is the empty skeleton of folders made on the way to a destination:
`mkdir` does not say whether a folder was already there, and removing one this run did not
create would be the damage this code exists to prevent. Nothing readable is left, so half a
skill cannot be mistaken for a whole one, which is what the taking back is for.
"""

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

TARGET_ONLY = (
    "no entry with this id in the source description or what it extends; the target "
    "names one anyway, and what it says about it is what this run relies on"
)
"""Why a property's words come from the target alone, though `compare` never carried it.

`compare` matches only what the *source* declares, by id, within its own list -- so an id
only the *target*'s capabilities or layout carry never earns a `Gap` at all, and reads as
`UNDECLARED` unless this is asked of the target directly. It is not the same silence: the
target has a documented place or word for the entry. That word need not be a clean one --
a target-only capability the target documents as unsupported is still `MISSING`, exactly as
a `Gap` would call it."""

ASKS_NOTHING = {
    DROPPED: Outcome.OUT_OF_SCOPE,
    EMPTY: Outcome.OUT_OF_SCOPE,
    UNDECLARED_PATH: Outcome.UNKNOWN,
    LINKED: Outcome.UNKNOWN,
}
"""What a path that asks no entry amounts to, keyed by the reason the reading gives for it.

A path the rules keep out and a named part of the set that is empty cost the transfer
nothing: both are the set being smaller than it looks, said out loud so that no path is
dropped in silence (FR-29.1, FR-25.2). A path nobody declared and a folder the walk did not
follow are `unknown` from an `extension` -- the report row the specification asks for by
name (story 5), because what happens to them is decided by a rule of ours and not by
anything either environment documents.

Keyed by the reason and not by the shape of the finding. A reason not in this table is not
taken for one of them and not passed over either: `UNWEIGHED` says so in a row of its own,
because a reading that grew a fifth reason must not reach a caller as a clean verdict.
"""

UNWEIGHED = (
    "the reading gave a reason this run has no rule for, so nothing here could be weighed "
    "against the descriptions; the row is `unknown` because a reason nobody could read is "
    "not a reason to call the transfer clean"
)
"""Why a path with a reason :data:`ASKS_NOTHING` does not know is `unknown` and not `clean`.

The two modules version together and this cannot happen today. It is written down rather
than assumed because the cost of being wrong is one-sided: a reason silently taken for
nothing turns a lost file into an exit code 0, which is the one answer this command must
never give.
"""

REWRITTEN_VALUE = "frontmatter of "
"""How the reading spells a finding about a value it had to rewrite rather than about a path.

Such a finding is the one that leaves a line of advice instead of a row: there is no path to
account for, and the value did cross -- as the text the line names. Asked after the reason
has been looked up in :data:`ASKS_NOTHING`, so that a file whose own name begins with these
words keeps the row its reason earned it.

# ponytail: matched on the words the reading uses, because a `Finding` carries no kind to
# ask for. The way up is a kind on `Finding`, which is the reading's own to add.
"""

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
"""Entry ids the assembly asks the target description for. Ids, and never paths.

Every path this command writes to is read from the ``layout`` of the target description
under one of these ids. A path spelled out here would be a claim about the target
environment kept out of the freshness check that guards every other such claim.
"""

SKILL_NAME = "<skill-name>"
WORKSPACE_ROOT = "<workspace-root>"
HOME = "~"
"""What a layout path may carry in place of a name or a root, expanded by the assembly."""


class ConvertError(Exception):
    """A refusal that still produces a report: the message says what is wrong and where."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class Property:
    """One row of the report: what was found, and what the two descriptions make of it.

    ``id`` is the entry id of the descriptions the finding asked about, and ``None`` where
    it asked about none: a path the rules keep out, a folder nobody declared, a part of the
    set that is empty. Those have no entry to look up and still have a row, which is the
    whole of FR-3 -- a file that left no row would be a file nobody can account for.
    """

    id: str | None
    found_as: str
    outcome: Outcome
    origin: Origin
    verdict: Verdict
    source_says: str | None
    target_says: str | None
    note: str | None = None


@dataclass(frozen=True)
class Assessed:
    """One entity of the set, judged: its rows and the verdict they add up to.

    ``name`` is what the entity is called -- for a skill, the name its own header or folder
    gives it -- and is empty for a record of a named part rather than of an entity in it.
    ``assembled_name`` is that name suffixed with the target environment, and ``None`` for
    everything this run assembles nothing for.

    ``translations`` are the rules that were applied to its header, one per value rewritten.
    A rule that was applied cost the transfer nothing, so it leaves no row among the
    ``properties``; it leaves this instead, which is how the report shows the work (FR-14).
    """

    asset: Asset
    name: str
    assembled_name: str | None
    verdict: Verdict
    properties: tuple[Property, ...]
    translations: tuple[dict[str, str], ...] = ()


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


_TARGET_ONLY_OUTCOME = {
    Support.SUPPORTED: Outcome.REPRODUCED,
    Support.UNSUPPORTED: Outcome.MISSING,
    Support.UNKNOWN: Outcome.UNKNOWN,
}
"""What a target-only capability's own ``support`` means, mirrored from `compare`'s table.

`compare` never carries this entry -- it is asked here, of the target alone -- but once
asked, the answer follows the same rule `compare` uses for every entry it does carry: the
target's declared ``support``, not whether it left a ``note``.
"""


def _target_alone(target: EnvSpec, entry_id: str) -> tuple[str | None, Outcome] | None:
    """What the target says about ``entry_id`` on its own, or ``None`` when it names nothing.

    `compare` never asks about an id neither the source nor what it extends declares, so an
    id only the *target*'s capabilities or layout carry -- a directory both a real skill and
    the target's own layout happen to name, say -- reaches `_judge` with no `Gap` at all.
    Asked here, directly of the target, rather than folded into the source-only silence
    `UNDECLARED` speaks for.

    A layout entry carries no `support` of its own -- the target either names a place or does
    not, which is `compare`'s own rule for layout too -- so finding one is `REPRODUCED`. A
    capability does carry `support`, and a target that documents the entry as unsupported or
    unknown said so on its own initiative; that is not weaker for being unasked.
    """
    layout_path = _layout(target, entry_id)
    if layout_path is not None:
        return layout_path, Outcome.REPRODUCED
    capability = next((entry for entry in target.capabilities if entry.id == entry_id), None)
    if capability is None:
        return None
    return capability.note, _TARGET_ONLY_OUTCOME[capability.support]


def _judge(
    findings: Sequence[Finding],
    gaps: Mapping[str, Gap],
    target: EnvSpec,
    translation: Rules,
) -> tuple[list[Property], list[str]]:
    """Every finding against the comparison, once per entry id, plus the advice it earns.

    An id the comparison does not carry is ``unknown`` from an ``extension`` -- unless the
    *target* documents it on its own, which `compare` has no way to say: it matches only
    what the source declares. An entry only the target names is not the silence `UNDECLARED`
    describes, and reporting it that way while the very same run copies it to the place the
    target names would tell the caller both that nobody knows where it goes and where it went.

    One id, one row, however many findings asked about it: ``hook.decision.block`` is asked
    once by every declared hook, and the row names all of them. Naming the first and dropping
    the rest would read as though only that hook lost its veto.

    A finding that asks no id at all is a row too, ahead of the rest: it is about a path, and
    a path that produced no row is a file this run cannot account for. The one exception is a
    value the header had to rewrite to cross, which is about no path and leaves a line of
    advice -- first of those, because it happened first, while the header was being read.
    """
    asked_by: dict[str, list[str]] = {}
    asked_nothing: list[Property] = []
    rewritten: list[str] = []
    for finding in findings:
        for entry_id in finding.ids:
            asked_by.setdefault(entry_id, []).append(finding.found_as)
        if finding.ids:
            continue
        # The reason first and the shape of the finding second: a reason the table knows is
        # about a path however the path is spelled, and only a finding left over by that is
        # about a value. Reversed, a file called `frontmatter of ours.md` would lose its row.
        if finding.note in ASKS_NOTHING or not finding.found_as.startswith(REWRITTEN_VALUE):
            asked_nothing.append(_asked_nothing(finding, translation))
        else:
            rewritten.append(finding.note or finding.found_as)
    properties: list[Property] = []
    advice: list[str] = []
    for entry_id, found_as in asked_by.items():
        gap = gaps.get(entry_id)
        target_only = None if gap is not None else _target_alone(target, entry_id)
        if gap is not None:
            outcome, origin = gap.outcome, gap.origin
            source_says, target_says, note = gap.source_note, gap.target_note, None
        elif target_only is not None:
            target_says, outcome = target_only
            origin = Origin.EXTENSION
            source_says, note = None, TARGET_ONLY
        else:
            outcome, origin = Outcome.UNKNOWN, Origin.EXTENSION
            source_says, target_says, note = None, None, UNDECLARED
        verdict = verdict_of(outcome, origin)
        properties.append(
            Property(
                id=entry_id,
                found_as=", ".join(found_as),
                outcome=outcome,
                origin=origin,
                verdict=verdict,
                source_says=source_says,
                target_says=target_says,
                note=note,
            )
        )
        if verdict is not Verdict.CLEAN:
            ways_out = WORKAROUNDS.get(_kind(entry_id, gap), ())
            advice += [line for line in ways_out if line not in advice]
    return [*asked_nothing, *properties], [*rewritten, *advice]


def _asked_nothing(finding: Finding, translation: Rules) -> Property:
    """The row a finding that names no entry id earns. There is always one.

    The reason the reading gave decides the outcome (:data:`ASKS_NOTHING`) and a path nobody
    declared carries the one rule the translation states for such a file, in its own words:
    FR-30 asks for one rule and one row per undeclared file, and two wordings of it -- the
    reading's and the rules' -- would be two rules as soon as either changed.

    A reason the table does not know is `unknown` and says why (:data:`UNWEIGHED`), and its
    verdict is counted with every other: a row whose weight is not added is a row that makes
    an entity look clean for the one reason nobody could read.
    """
    known = ASKS_NOTHING.get(finding.note or "")
    outcome = known if known is not None else Outcome.UNKNOWN
    if known is None:
        note = f"{finding.note}; {UNWEIGHED}" if finding.note else UNWEIGHED
    elif finding.note == UNDECLARED_PATH:
        note = translation.undocumented.note
    else:
        note = finding.note or UNWEIGHED
    return Property(
        id=None,
        found_as=finding.found_as,
        outcome=outcome,
        origin=Origin.EXTENSION,
        verdict=verdict_of(outcome, Origin.EXTENSION),
        source_says=None,
        target_says=None,
        note=note,
    )


FRONTMATTER = {Kind.SKILL: SKILL_FRONTMATTER, Kind.SUBAGENT: SUBAGENT_FRONTMATTER}
"""Which entry ids an entity's header keys are spelled under, by the kind of entity.

The other kinds carry no header this command reads (`assets._plain`), so a kind absent here
has no field whose value could be translated.
"""

NO_VALUE_SET = (
    "the target description names no closed set of values for this field, so there is "
    "nothing here to tell an acceptable value from one that has to be translated; the value "
    "crosses as it was written, and a translation applied without a documented set would be "
    "a rule of ours dressed as a fact about the environment"
)
"""Why a field the rules can translate is left alone when the target documents no value set.

Silence about the set is not permission to use it (Decisions 1): the row is `unknown` and
says which of the two documents is missing, so that the fix is to the description and not
to a guess here.
"""

NO_COUNTERPART = (
    "the value is outside the closed set the target documents, and the translation rules "
    "name no counterpart for it: it is neither invented here nor dropped, so the file "
    "crosses carrying a value the target does not accept"
)
"""Why a value outside the set and outside the table is a row rather than a silence (FR-12)."""

NO_TOOL_COUNTERPART = (
    "the translation rules name no counterpart for this tool name, so it stays as it is; "
    "the target warns that a tool name it does not know may leave the subagent hanging on "
    "the call, and a pair guessed by how the two names sound would be that same hang with "
    "nobody left to blame it on"
)
"""Why an unpaired tool name is carried and named rather than translated or removed (FR-18)."""

REFUSED_BY_THE_TARGET = (
    "the translation rules turn this value into one the closed set of the target does not "
    "contain, so applying them would write a value the target rejects; the rules and the "
    "description disagree, and which of them is out of date is not a thing this run can tell"
)
"""Why a counterpart the target's own set does not carry is not applied (Decisions 1)."""

_HOW_TO_KEEP_A_TOOL_NAME = (
    "Remove the unpaired tool name from the header, or replace it by hand with a tool the "
    "target documents: the two are a decision about what the subagent may do, which is not "
    "this command's to make.",
)
"""The ways out of an unpaired tool name, named and not chosen between, as hooks are."""


def _closed_set(target: EnvSpec, entry_id: str) -> tuple[str, ...] | None:
    """The values the target documents for ``entry_id``, or ``None`` when it documents none."""
    entry = next((item for item in target.capabilities if item.id == entry_id), None)
    if entry is None or entry.values is None:
        return None
    return tuple(entry.values)


def _text(value: Any, path: Path, key: str, entry_id: str) -> str:
    """``value`` as the text a closed set is read against, or a refusal naming where it is.

    A value that is not text cannot be looked up in a set of words nor found in a table of
    them, and passing it through unexamined would be this command deciding in silence that
    it needs no translation. The refusal names the file and the key, because that is the
    line somebody has to open and edit (FR-11.1).
    """
    if isinstance(value, str):
        return value
    raise ConvertError(
        f"{path}: frontmatter key `{key}` reads as {type(value).__name__}, and `{entry_id}` "
        "is a field whose values are translated as text; quote the value if it is meant as "
        "text, or remove the key",
        UNREADABLE,
    )


def _tool_names(value: Any, path: Path, key: str) -> list[str]:
    """The tool names a header value holds, written either way the source environment allows.

    One string of names separated by commas, or a list of them; anything else is refused at
    the address it is written, like any other value this command cannot read as text.
    """
    if isinstance(value, list) and all(isinstance(name, str) for name in value):
        spelled: list[str] = value
    else:
        spelled = _text(value, path, key, TOOL_NAMES_ENTRY).split(",")
    return [name.strip() for name in spelled if name.strip()]


def _unusable(entry_id: str, found_as: str, note: str) -> Property:
    """The row a value that did not cross in the target's own vocabulary earns.

    ``unknown`` from an ``extension``, whatever the entry's own row said about the field:
    the field crossing and its value crossing are two questions, and the vocabulary of
    values is each product's own -- the open specification declares fields, never the words
    one environment happens to spell a model tier or a tool with. So this is the ordinary
    price of moving between two products (`lossy`), and never the refusal an entry of the
    specification earns.
    """
    return Property(
        id=entry_id,
        found_as=found_as,
        outcome=Outcome.UNKNOWN,
        origin=Origin.EXTENSION,
        verdict=verdict_of(Outcome.UNKNOWN, Origin.EXTENSION),
        source_says=None,
        target_says=None,
        note=note,
    )


def _translated(
    asset: Asset, target: EnvSpec, translation: Rules
) -> tuple[list[Property], list[str], list[dict[str, str]]]:
    """Every header value of one entity put into the target's vocabulary: rows, advice, rules.

    Two documents decide this between them and neither decides it alone. The description of
    the target names the closed set a field's values come from, which is what makes a value
    wrong rather than merely different; the rules name what a value outside that set becomes,
    which is a decision of ours and so is versioned apart from either description (FR-6).
    A field neither of them says anything about is not touched: a header key is not a thing
    to translate just because it is there.

    Tool names are the one field asked without a closed set, because the target documents
    its tools under its own supported tool set rather than as the values of that field. The
    rules carry only pairs whose right-hand side the target documents, so a name absent from
    them has no documented counterpart and crosses as it was written, with a row saying so.
    """
    prefix = FRONTMATTER.get(asset.kind)
    if prefix is None:
        return [], [], []
    rows: list[Property] = []
    advice: list[str] = []
    applied: list[dict[str, str]] = []

    def apply(entry_id: str, was: str, became: str) -> None:
        applied.append(
            {
                "path": str(asset.path),
                "id": entry_id,
                "from": was,
                "to": became,
                "rule": f"{entry_id} of the translation rules {translation.version}",
            }
        )

    for key, value in asset.frontmatter.items():
        entry_id = f"{prefix}{key}"
        if entry_id == TOOL_NAMES_ENTRY:
            for name in _tool_names(value, asset.path, key):
                became = translation.tool_name(name)
                if became is None:
                    rows.append(_unusable(entry_id, f"tool name `{name}`", NO_TOOL_COUNTERPART))
                    advice += [line for line in _HOW_TO_KEEP_A_TOOL_NAME if line not in advice]
                else:
                    apply(entry_id, name, became)
            continue
        allowed = _closed_set(target, entry_id)
        if allowed is None and entry_id not in translation.value_maps:
            continue
        was = _text(value, asset.path, key, entry_id)
        found_as = f"frontmatter key `{key}` set to `{was}`"
        if allowed is None:
            rows.append(_unusable(entry_id, found_as, NO_VALUE_SET))
        elif was in allowed:
            continue
        elif (became := translation.value_of(entry_id, was)) is None:
            rows.append(_unusable(entry_id, found_as, NO_COUNTERPART))
        elif became not in allowed:
            rows.append(_unusable(entry_id, found_as, REFUSED_BY_THE_TARGET))
        else:
            apply(entry_id, was, became)
    return rows, advice, applied


def _layout(spec: EnvSpec, entry_id: str) -> str | None:
    """The path the description gives ``entry_id``, or ``None`` when it names none."""
    return next((entry.path for entry in spec.layout if entry.id == entry_id), None)


# A skill's own name, not documented by either environment description -- both merely say a
# missing `name` defaults to the directory name (specs/anthropic/claude-code-2.1.yaml:113,
# specs/google/antigravity-2.0.yaml:166) and neither states the rule a name itself must
# follow. This is that rule, a repository-level one sourced from the Claude Code
# documentation (https://code.claude.com/docs/en/skills), kept here rather than as a
# `limits` entry a description's own freshness check would have to keep current.
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX_LENGTH = 64
NAME_RULE = (
    f"lowercase letters, digits and single hyphens between them, at most {NAME_MAX_LENGTH} "
    "characters"
)


def _valid_name(value: str) -> bool:
    """Whether ``value`` matches the skill-name rule above."""
    return len(value) <= NAME_MAX_LENGTH and NAME_PATTERN.fullmatch(value) is not None


def _skill_name(skill_dir: Path, front: Mapping[str, Any]) -> str:
    """The skill's own name: the frontmatter's ``name``, or the folder's own last component.

    Both descriptions agree that a missing ``name`` "defaults to the directory name", so the
    frontmatter is asked first, and never overridden by what the folder happens to be called
    once it has answered.

    The directory name is read with ``os.path.abspath``, never ``Path.resolve()``: `abspath`
    collapses ``.`` and ``..`` lexically, without touching the filesystem, so ``.``, ``..``,
    a trailing slash and a symbolic link all get a correct answer from the one expression,
    and a loop of links -- which raises out of `resolve()` -- never reaches this function at
    all. A skill installed as a link keeps the name it is invoked by, not the link target's.

    A name that fails the rule is a refusal, not a fallback: an invalid frontmatter ``name``
    is never quietly replaced by the directory name it happens to sit in.
    """
    declared = front.get("name")
    if declared is not None:
        candidate, found_as = declared, "the frontmatter `name`"
    else:
        candidate, found_as = Path(os.path.abspath(skill_dir)).name, "the directory name"
    if isinstance(candidate, str) and _valid_name(candidate):
        return candidate
    raise ConvertError(
        f"{skill_dir}: {found_as} is {candidate!r}, which is not a skill name -- {NAME_RULE}",
        UNREADABLE,
    )


def _assembled_name(name: str, environment: str) -> str:
    """``name``, suffixed with the target's own ``environment`` -- what a layout path expands.

    One folder per target, so that converting the same skill to two targets never collides
    on one destination. Validated by the same rule as `_skill_name`, because the result
    becomes a path segment the same way: an oversize name or an ``environment`` that is not
    itself lowercase-and-hyphens is refused rather than truncated, which would silently
    rename a skill someone chose the name of.

    Whose fault it is decides the code, and the two faults are told apart before the two
    names are joined. An ``environment`` that is not a path segment is the description's:
    the skill folder is exactly as it should be, and code 6 would send a person to read a
    skill file with nothing wrong in it. Past that, what is too long is the pair, and the
    name the caller can do something about is the skill's -- code 6, as for any other name
    the skill folder gave this run.
    """
    if not _valid_name(environment):
        raise ConvertError(
            f"the target description names its environment {environment!r}, which cannot be "
            f"part of a folder name -- {NAME_RULE}; the skill is readable, the description "
            "is what settles nothing",
            EXIT_CODE[Verdict.UNDECIDABLE],
        )
    assembled = f"{name}-{environment}"
    if _valid_name(assembled):
        return assembled
    raise ConvertError(
        f"{name!r} suffixed with the target environment {environment!r} is {assembled!r}, "
        f"which is not a skill name -- {NAME_RULE}",
        UNREADABLE,
    )


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
    """The bytes to write, where the part is written rather than copied from where it came.

    Set beside ``copied_from`` and not instead of it for a part that came from a file and
    leaves changed -- the skill file with a translated header. The content is what is
    written; ``copied_from`` still says where it came from, which is what the report reads
    to say whether that path was a symbolic link.
    """


_OPENS_A_KEY = re.compile(r"([^\s:#][^:]*):(.*)$")
"""A header line that opens a top-level key: a name at column one, then a colon.

A line that begins with a space continues the value of the key above it, whatever it holds
-- a nested mapping, an item of a list, the next line of a folded scalar -- and a line that
begins with `#` is a comment. Neither opens a key, and neither ends the value being read.
"""


def _in_the_value_of(header: str, key: str, was: str, became: str) -> str:
    """``header`` with ``was`` replaced by ``became`` inside the value of ``key``, and nowhere else.

    The file is somebody's, and the one thing this run is entitled to change in it is the
    value a rule was applied to. So the header is edited where it stands rather than parsed
    and dumped again: a round trip through YAML would return a file with its comments gone,
    its quoting redecided and its keys reordered, all of it unannounced and none of it
    translation. Whole words only -- a tier named `pro` must not turn the `sonnet` inside
    `sonnet-2.0` into one.

    # ponytail: a comment written on the same line as a translated value is inside that
    # value as far as this is concerned, and a word in it that matches is replaced too. The
    # way up is the line and column `yaml` already knows for every node, which means holding
    # on to the parsed header rather than only to what it loaded.
    """
    spelled = re.compile(rf"(?<![\w.-]){re.escape(was)}(?![\w.-])")
    lines = header.split("\n")
    inside = False
    for index, line in enumerate(lines):
        opens = _OPENS_A_KEY.match(line)
        if opens is None:
            # A continuation line: it belongs to whichever key was opened last, so it is
            # rewritten exactly when that key is the one being translated.
            lines[index] = spelled.sub(became, line) if inside else line
            continue
        inside = opens.group(1).strip().strip("'\"") == key
        if inside:
            lines[index] = line[: opens.start(2)] + spelled.sub(became, opens.group(2))
    return "\n".join(lines)


def _with_translations(path: Path, applied: Sequence[Mapping[str, str]]) -> str | None:
    """The skill file with every applied rule in its header, or ``None`` when none were.

    The report says a value was translated, and this is what makes that true of the file the
    caller ends up with: without it the run would state a rewrite that never happened and
    call the transfer clean while the target's own set still refuses what was written.

    The body below the header is not touched at all, and neither is a key no rule applied to.
    """
    if not applied:
        return None
    text = path.read_text(encoding="utf-8")
    closing = FRONTMATTER_CLOSE.search(text, 3)
    if closing is None:
        # Unreachable: a file whose header never closes was refused while it was being read,
        # and there would be no translation to apply to it. Answered rather than asserted,
        # because the answer is the file exactly as it was found.
        return None
    header = text[3 : closing.start()]
    for rule in applied:
        # The key is the last step of the entry id: the ids of a header field are built from
        # the key as written (`assets`), so this takes it back without a table of pairs.
        header = _in_the_value_of(header, rule["id"].rpartition(".")[2], rule["from"], rule["to"])
    return f"---{header}{text[closing.start() :]}"


def _plan(
    skill_dir: Path,
    out: Path,
    target: EnvSpec,
    scope: Scope,
    properties: Sequence[Property],
    hooks: Mapping[str, Any],
    *,
    root: str,
    assembled_name: str,
    translations: Sequence[Mapping[str, str]] = (),
) -> tuple[list[_Part], list[str]]:
    """What the assembly will write, and what it asks of a person once it has.

    ``root`` is where a skill of the target environment lives, as `_skills_root` read it off
    the layout -- and refused the run when the layout named nowhere, which is why there is
    always one here.

    A part the target description names no path for is not assembled: guessing where it goes
    would be inventing the target environment's layout. It keeps its row in the report, and
    `_left_behind` says it was left behind -- from the layout alone, whether or not anybody
    asked for this plan, because that is a price the descriptions settle between them.
    """
    parts = []
    for label, inside in _places(target, properties):
        # The other half of the same list: what has a place is written, what has none is
        # named by `_left_behind`. Neither side decides for itself which half a part is in,
        # or a part could end up written and called left behind, or in neither list.
        if inside is None:
            continue
        where, staged = _destination(f"{root.rstrip('/')}/{inside}", assembled_name)
        source_file = skill_dir / label
        parts.append(
            _Part(
                label,
                where,
                _under(out, staged),
                copied_from=source_file,
                # Only the skill file carries a header, so it is the only part a rule can
                # have been applied to. `None` when none were, and then the bytes are copied
                # exactly as every other part's are.
                content=(
                    _with_translations(source_file, translations) if label == SKILL_MD else None
                ),
            )
        )
    carried, hooks_file = _hook_place(target, scope, properties, hooks)
    if not carried or hooks_file is None:
        return parts, []
    # Through `_destination` like every other part: a layout path opens with the root it is
    # measured from, and a hooks file spelled `<workspace-root>/...` or `~/...` -- as the
    # descriptions do spell it -- would otherwise reach the report with the placeholder
    # still in it, telling a person to put the entry in a folder named `<workspace-root>`.
    where, _ = _destination(hooks_file, assembled_name)
    hook_part = _hook_part(out, where, carried)
    return [*parts, hook_part], [
        f"the hook entry is staged at {hook_part.staged} and not merged into "
        f"{hook_part.destination}: that file belongs to the whole target environment and "
        "may already hold entries of its own, so add this one to it yourself",
    ]


def _under(out: Path, staged: str) -> Path:
    """One staged path, with every ``..`` in it collapsed before anything is done with it.

    Lexically, by text, and deliberately: what is worked out here is what the checks are made
    about, what the bytes are written to and what the report calls the place they are in. Left
    for the operating system to work out at the last moment, those three could differ -- the
    report would name a path that leads to the file only once somebody else has read the
    ``..``, and the checks would have been made about a place nothing was written to.
    """
    return Path(os.path.normpath(out / staged))


def _skills_root(target: EnvSpec, scope: Scope) -> str:
    """Where a skill of the target environment lives, or the refusal that there is nowhere.

    Asked whether or not the caller wants the bytes written: that a target names no place for
    a skill file is read off its layout like everything else here, so the answer -- and the
    exit code -- cannot depend on `--out`. It is not a part left behind either, and the code
    says which: nothing is known about where any of this skill goes, which is `undecidable`.
    """
    root = _layout(target, SKILLS_ROOT[scope])
    if root is None or _layout(target, SKILL_FILE) is None:
        raise ConvertError(
            f"{target.vendor}/{target.environment} names no place for a skill file at the "
            f"{scope.value} level, so there is nowhere to assemble into",
            EXIT_CODE[Verdict.UNDECIDABLE],
        )
    return root


def _places(target: EnvSpec, properties: Sequence[Property]) -> list[tuple[str, str | None]]:
    """Every part of the skill folder and the path the target names for it, ``None`` for none.

    The one place that question is answered. It is asked from two sides -- by what is written
    and by what is said to have stayed behind -- and two spellings of it could drift apart on
    the next entry id somebody adds, leaving a part written and called left behind, or written
    and never mentioned. That is the silent disappearance this whole module is written against.
    """
    return [(label, _layout(target, entry_id)) for entry_id, label in _wanted(properties)]


def _hook_place(
    target: EnvSpec, scope: Scope, properties: Sequence[Property], hooks: Mapping[str, Any]
) -> tuple[dict[str, Any], str | None]:
    """The hooks to carry over, and the file the target registers hooks in -- both or neither.

    One answer for the same two sides, for the same reason as `_places`: a hook with nowhere
    to go is named, one with a place is written, and nothing decides that twice.
    """
    return _hooks_the_target_fires(properties, hooks), _layout(target, HOOKS_FILE[scope])


def _wanted(properties: Sequence[Property]) -> list[tuple[str, str]]:
    """Every part of the skill folder to place: the id that names its path in the layout of
    an environment, and the name it goes by inside the folder.

    A file beside the skill file is asked about exactly as a bundled directory is. Left out
    of this list it would be left out of what is said about parts with nowhere to go as
    well, and a `README.md` nobody has a place for would go unmentioned while a directory in
    the same position is named.
    """
    held = [entry.id for entry in properties if entry.id is not None]
    wanted = [(SKILL_FILE, SKILL_MD)]
    wanted += [
        (entry_id, f"{entry_id[len(SKILL_DIR) :]}/")
        for entry_id in held
        if entry_id.startswith(SKILL_DIR)
    ]
    return wanted + [
        (entry_id, entry_id[len(SKILL_TOP) :])
        for entry_id in held
        if entry_id.startswith(SKILL_TOP)
    ]


def _left_behind(
    target: EnvSpec, scope: Scope, properties: Sequence[Property], hooks: Mapping[str, Any]
) -> list[str]:
    """What the target description names no place for, in the words the report says it in.

    Read off the layout of the target and nothing else: no ``out``, no filesystem. What the
    transfer costs is settled by the two descriptions and the skill folder, so asking for the
    bytes cannot change it -- ``--out`` decides what is written, not what is lost. Said out
    loud, too, because the list of what was written cannot say it: a part missing from that
    list looks the same whether the run had nowhere to put it or never got that far.

    The skill file cannot turn up here: a target that names no place for one has nowhere to
    assemble into at all, and `_skills_root` has refused the run before this is asked -- that
    is the whole skill with nowhere to go, not one part of it left behind while the rest
    crosses, and it carries the other code.
    """
    lines = [
        f"`{label}` stayed in the skill folder: {target.vendor}/{target.environment} names "
        "no place for it, and a place picked for it here would be a guess about a layout "
        "only that environment's documentation can settle"
        for label, inside in _places(target, properties)
        if inside is None
    ]
    # The one thing that can be reproduced in full and still have nowhere to go: the event a
    # hook fires on is a capability, and the file the environment registers a hook in is a
    # layout entry it owes nothing about for having declared the event. The header itself
    # crosses -- `SKILL.md` is copied whole, `hooks:` and all -- so what is lost is not the
    # text of the declaration but the only place the environment would have read it from.
    carried, hooks_file = _hook_place(target, scope, properties, hooks)
    if carried and hooks_file is None:
        lines.append(
            f"the `{HOOKS_KEY}` key crosses inside {SKILL_MD} and is registered nowhere: "
            f"{target.vendor}/{target.environment} names no file for hook entries, and that "
            "file is where a declaration becomes a hook -- what arrives in the target is the "
            "text of the rule, in a header nothing reads it from"
        )
    return lines


def _hooks_the_target_fires(
    properties: Sequence[Property], hooks: Mapping[str, Any]
) -> dict[str, Any]:
    """The declared hooks whose event the target reproduces, and nothing else.

    An event the target does not reproduce is left out of the file -- written there it would
    read as a guarantee the target never gave. It keeps its row in the report either way.
    """
    fires = {entry.id for entry in properties if entry.verdict is Verdict.CLEAN}
    return {name: value for name, value in hooks.items() if f"{EVENT}{name}" in fires}


def _hook_part(out: Path, destination: str, carried: Mapping[str, Any]) -> _Part:
    """The hook entry to carry over, ready to be staged beside the assembled skill.

    Whether there is anything to carry and whether the target names a file to carry it into
    are asked before this, by the plan: a hook with nowhere to go is not a part to write but
    a part left behind, and the two answers must not both arrive here as one ``None``.
    """
    return _Part(
        f"frontmatter key `{HOOKS_KEY}`",
        destination,
        # The entry is staged beside the assembled skill under the name the target gives the
        # file it belongs in, never at the destination itself: merging into a file that may
        # already hold someone else's entries is FR-40.
        _under(out, Path(destination).name),
        # No rescue argument here, and none needed: every value came through `_portable`,
        # which is where a header meets JSON. A date is already the text ISO 8601 spells,
        # and a shape with no stable text never got this far -- the file was refused as it
        # was read. A rescue here would have turned an unwritable value into whatever
        # `str()` makes of it, unannounced and differently on every run.
        content=json.dumps({HOOKS_KEY: carried}, indent=2, ensure_ascii=False) + "\n",
    )


def _links_on_the_way(out: Path, staged: Path) -> None:
    """Refuse a symbolic link at any level of ``staged`` below ``out``, the last one included.

    Every level, because every one of them is a door out: `mkdir(parents=True,
    exist_ok=True)` walks through a link in the middle of a path without a word, and a copy
    at the end follows one, so a link anywhere below `out` puts the bytes where it points.
    Asked here rather than with the checks over the whole plan, so that the answer is as
    fresh as it can be: what is asked of a path and what is then done to it are two moments,
    and the shorter the gap the less of it another process can use.
    """
    # ponytail: the window is narrowed, not closed. Between this question and the operation
    # it clears, a concurrent writer can still replace a level with a link, and no amount of
    # asking beforehand changes that. Closing it means the operations themselves refusing to
    # follow links -- `O_NOFOLLOW` and `dir_fd` down every level of the path -- which is the
    # path sandbox of FR-14, deferred twice by the user and a block of work of its own.
    below = [
        level for level in reversed(staged.parents) if level != out and level.is_relative_to(out)
    ]
    for level in [*below, staged]:
        if level.is_symlink():
            raise ConvertError(
                f"{level} is a symbolic link, and no level of a destination is written "
                f"through one: the bytes would go where the link points rather than under "
                f"{out}, which is the one promise this command makes about the caller's "
                "filesystem",
                UNWRITABLE,
            )


def _resolved(path: Path) -> Path:
    """``path.resolve()``, with a loop of symbolic links answered rather than raised.

    Up to Python 3.12 a cycle of links leaves `resolve` as a `RuntimeError`, which is neither
    of the two shapes of refusal this module answers for: it would leave `convert` as a
    traceback, and the process with the code a caller reads as "moved, and here is what it
    cost". A cycle is a path nothing can be written through, which is what `UNWRITABLE` says.

    Caught around the call and nowhere wider: a `RuntimeError` from anything else in here is
    a fault of ours, and dressed up as a filesystem we could not write to it would be
    reported as the caller's to fix.
    """
    try:
        return path.resolve()
    except RuntimeError as error:
        raise ConvertError(
            f"{path} is a loop of symbolic links, so it names no place to write to and "
            f"nothing was written: {error}",
            UNWRITABLE,
        ) from error


def _links_within(copied_from: Path, label: str) -> list[str]:
    """Every symbolic link under ``copied_from``, named the way the report names a part.

    A ``SKILL.md`` that is a link is read and its content copied; every other link is carried
    over as a link and never read -- neither its own bytes, when it is the part itself, nor its
    target's, when it sits somewhere inside a bundled directory copied whole. Named here so that
    a caller sees which paths of the assembled skill are links and not the files or directories
    they appear to be: the skill folder is a stranger's, and a link inside it may point anywhere
    on the machine this command runs on.
    """
    if copied_from.is_symlink():
        if label == SKILL_MD:
            # The one link this command does read through, and so the one whose wording must
            # not say it was not read: `assets.frontmatter` graded the run on its content and the
            # copy staged that content, not the pointer. Named all the same, because the run
            # reached into a folder nobody named on the command line to do it.
            # `os.readlink`, not `resolve()`: it shows what the link itself says, and it does
            # not raise on a loop -- a loop at `SKILL.md` never reaches here, refused as
            # unreadable while the header was being read.
            return [
                f"`{SKILL_MD}` is a symbolic link to {os.readlink(copied_from)}; its content "
                "was read and copied, not the link"
            ]
        return [f"`{label}` is a symbolic link, carried over as one and not read"]
    if not copied_from.is_dir():
        return []
    return [
        f"`{label}{entry.relative_to(copied_from).as_posix()}` is a symbolic link, carried "
        "over as one and not read"
        for entry in sorted(copied_from.rglob("*"))
        if entry.is_symlink()
    ]


def _assemble(out: Path, parts: Sequence[_Part]) -> tuple[list[dict[str, str]], list[str]]:
    """Copy or write every planned part, once the whole plan is known to be safe to write.

    Two questions are asked of every destination before the first byte of the first one is
    written: is the place free, and is it under ``out``. Both run over the whole plan, because
    a run that wrote two files and then refused the third would have done the damage it
    refused to do.

    A symbolic link counts as an occupied place even when it points at nothing: ``exists``
    answers ``False`` for a broken one, and writing to it would create its target somewhere
    the caller never named.

    A symbolic link inside the skill folder is carried over as a link and never read, on
    either side of the copy: ``shutil.copytree`` is asked for the same, ``shutil.copy2``
    told not to follow one, and a part that is itself a link is checked for that before it is
    asked whether it is a directory -- ``is_dir`` follows a link, and asking it first would
    read straight through the one thing this command must not read through. The second
    return value names every link a caller must know is a link, so a run that carries one
    over does not also read as an ordinary, clean copy.

    ``SKILL.md`` is the one exception, because it is not this function's own rule to keep:
    its bytes are what the whole run was graded on, read straight through a link already by
    `assets.frontmatter`. Carrying it over as a link here -- almost always unresolvable, since it
    would point relative to a folder under ``out`` rather than the one it came from -- would
    stage a broken pointer behind a verdict computed from real content. It is copied through
    the link instead, exactly as reading it already was. It is still named among the links
    the second return value reports, in words of its own: the run reached into a folder
    nobody named on the command line, and a caller who is not told cannot know it did.

    The order of the three is the order of what they answer for. Leading out of ``out``
    first: that is the one promise this command makes about the caller's filesystem, and a
    plan that breaks it must not be answered with the code for a lesser fault it also has.
    Then the plan against itself, then the plan against what is already on disk.
    """
    # The four ways a destination can lead out of `out` -- a layout path that is absolute, a
    # `..` anywhere along the way, a `..` as the last step, a link on the way -- are one
    # question asked once: `resolve` answers for everything above the last name and
    # `normpath` for the last name itself.
    # Over the whole plan, and answered again level by level in `_links_on_the_way` before
    # each part is written: this one rules out a destination that leads out of `out` at all,
    # that one rules out the path having changed since.
    root = _resolved(out)
    # The parent resolved and the last name left as written: what this asks is where the file
    # would be created. A link at the destination itself is not a way out of `out` but an
    # occupied place, and the check below answers for it with the code for that; resolving it
    # here would have the run report a broken promise where the promise was never reached.
    # `normpath` then settles what that last name means without going near the filesystem: a
    # `..` written there is a step back out, not a name to create, and left as text it would
    # read as a path under `out`.
    places = [
        (part, Path(os.path.normpath(_resolved(part.staged.parent) / part.staged.name)))
        for part in parts
    ]
    outside = [str(part.staged) for part, place in places if not place.is_relative_to(root)]
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
    # `out` is the folder the result is assembled in, so it is never a place for one part of
    # that result: a destination that collapses onto it would replace what the caller named
    # -- a folder turned into a file or a bundle -- while the list of what was written called
    # that a part carried over. The same code as a destination outside `out`, and the same
    # reason: the fault is in the plan, and what the skill costs to transfer is untouched by
    # it. Not the code for an occupied place, which would make the answer depend on whether
    # `out` happens to exist yet -- met as an empty name it would be written straight through.
    onto = [str(part.staged) for part, place in places if place == root]
    if onto:
        raise ConvertError(
            ", ".join(onto) + f" is {out} itself, the folder this run was told to assemble "
            "into; nothing was written, because a part of a skill put there would replace "
            "the folder the caller named with one piece of what was supposed to go inside it",
            UNWRITABLE,
        )
    # The plan against itself, and apart from the plan against what is already there: a
    # description keeps its `id` unique and promises nothing about its `path`, so a target
    # may give two entries one destination. Two parts of one plan meeting there is ours to
    # notice -- the second write lands on the first, and `written` reports both as carried
    # over, which is a run saying it moved a file to where another file is.
    # ponytail: every part against every other, which is a handful against a handful. The way
    # up, if a plan ever grows, is to sort the destinations and compare each with the one
    # before it, where containment can only be with the neighbour.
    planned: dict[Path, str] = {}
    for part in parts:
        for place, label in planned.items():
            if place.is_relative_to(part.staged) or part.staged.is_relative_to(place):
                raise ConvertError(
                    f"`{label}` is to be written at {place} and `{part.label}` at "
                    f"{part.staged}, which is the same place or one inside the other; "
                    "nothing was written, because whichever of the two went second would "
                    "replace the other while the report called both of them carried over",
                    COLLISION,
                )
        planned[part.staged] = part.label
    taken = [str(part.staged) for part in parts if part.staged.exists() or part.staged.is_symlink()]
    if taken:
        raise ConvertError(
            "there is already something at " + ", ".join(taken) + "; nothing was written, "
            "because a converted skill that silently replaced a result of an earlier run "
            "is indistinguishable from one that was never converted",
            COLLISION,
        )
    started: list[_Part] = []
    try:
        for part in parts:
            # Immediately before this part is written, and once per part: the checks above
            # answered for the plan as a whole, and a path is only as checked as it is fresh.
            # Before `started` grows, so that a refusal here takes back what this run wrote
            # and never the link it refused to write through.
            _links_on_the_way(out, part.staged)
            part.staged.parent.mkdir(parents=True, exist_ok=True)
            started.append(part)
            if part.content is not None:
                part.staged.write_text(part.content, encoding="utf-8")
            elif (
                part.copied_from is not None
                and part.copied_from.is_symlink()
                and part.label != SKILL_MD
            ):
                # Checked before `is_dir`, which follows a link to ask about what it points
                # at rather than the link itself, and would send a link to a directory into
                # the branch below -- reading through the one thing that must not be read.
                # `SKILL.md` itself is excepted: its bytes are what the whole run was graded
                # on, read straight through a link by `assets.frontmatter` already, so carrying it
                # as a link here -- almost never resolvable relative to a different folder
                # under ``out`` -- would stage a broken pointer behind a verdict computed
                # from real content. It falls through to the plain copy below, which follows
                # a link exactly as reading it already did.
                shutil.copy2(part.copied_from, part.staged, follow_symlinks=False)
            elif part.copied_from is not None and part.copied_from.is_dir():
                shutil.copytree(part.copied_from, part.staged, symlinks=True)
            elif part.copied_from is not None:
                shutil.copy2(part.copied_from, part.staged)
    except (OSError, ConvertError) as error:
        # Whatever stopped the writing -- a link on the way to a destination, a link pointing
        # nowhere inside a bundle, a full disk -- this run takes back what it had put there,
        # because half an assembled skill is indistinguishable from a whole one. Only what it
        # wrote: every one of these places was free, which is what the check above established.
        for part in started:
            if part.staged.is_dir() and not part.staged.is_symlink():
                shutil.rmtree(part.staged, ignore_errors=True)
            else:
                part.staged.unlink(missing_ok=True)
        raise ConvertError(
            f"nothing was assembled under {out}, and what this run had written there is "
            f"taken back: {error}",
            # The same code as a destination outside `out`, and for the same reason: we could
            # not write. FR-27 has one row for that side of the run, and what the skill costs
            # to transfer was decided before any of it was written.
            UNWRITABLE,
        ) from error
    written = [
        {"from": part.label, "to": part.destination, "path": str(part.staged)} for part in parts
    ]
    links = [
        line
        for part in parts
        if part.copied_from is not None
        for line in _links_within(part.copied_from, part.label)
    ]
    return written, links


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
    source: str | None,
    target: str | None,
    rules_version: str,
    verdict: Verdict,
    exit_code: int,
    assessed: Sequence[Assessed],
    advice: Sequence[str],
    written: Sequence[dict[str, str]],
    error: str | None,
) -> dict[str, Any]:
    """The machine-readable report. ``report_schema`` first, and ``error`` says why it is thin.

    One report for the whole set, and the rows grouped under the entity they were found in:
    a set of hundreds of files makes hundreds of rows, and a flat list of them is a thing a
    person scrolls rather than reads (FR-26.1). ``name`` is the entity's own name -- for a
    skill the frontmatter's or the folder's -- and ``assembled_name`` is that name suffixed
    with the target environment, the one every destination in ``written`` is built from;
    ``None`` for anything this run assembles nothing for. Carried apart and not merged into
    one field, because the second is a property of *this* conversion and the first is not.

    ``rules_version`` stands beside the two environment versions and not inside them: what a
    value outside a closed set becomes is our decision and moves when we change our mind,
    while a description moves when a vendor changes their documentation. Repeating a past
    transfer needs all three numbers, and a report naming two of them would let a person
    reproduce the run they think they ran (FR-13.1).
    """
    return {
        "report_schema": REPORT_SCHEMA,
        "outcome": verdict.value,
        "exit_code": exit_code,
        "source": _environment(source),
        "target": _environment(target),
        "rules_version": rules_version,
        "translations": [row for entry in assessed for row in entry.translations],
        "assets": [
            {
                "kind": entry.asset.kind.value,
                "path": str(entry.asset.path),
                "name": entry.name,
                "assembled_name": entry.assembled_name,
                "verdict": entry.verdict.value,
                "properties": [
                    {
                        "id": row.id,
                        "found_as": row.found_as,
                        "outcome": row.outcome.value,
                        "origin": row.origin.value,
                        "verdict": row.verdict.value,
                        "source_says": row.source_says,
                        "target_says": row.target_says,
                        "note": row.note,
                    }
                    for row in entry.properties
                ],
            }
            for entry in assessed
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


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
"""Every character that does something to a terminal rather than appearing in it."""


def _plain(line: str) -> str:
    """One line of the summary with its control characters spelled out instead of acted on."""
    return _CONTROL.sub(lambda match: f"\\x{ord(match.group()):02x}", line)


def _summary(report: dict[str, Any]) -> str:
    r"""The same run in words: the verdict first, then one line per property, then the advice.

    Every line is escaped before it is joined, and the joining newlines are put in after: a
    frontmatter key, a file name and the text of a YAML parser's complaint are all a
    stranger's writing, and they reach a terminal here. A newline inside one of them writes a
    row of its own -- a property claiming it transferred cleanly, in the same columns as the
    rows this run computed -- and an escape sequence repaints or wipes the screen of whoever
    ran the command. Escaped at the one sink rather than at each of the many places a value
    enters, because a value that enters somewhere new is then safe without anyone noticing it
    had to be. The machine-readable report is untouched: `json.dumps` already escapes both,
    and a reader of it is not a terminal.

    A multi-line YAML error becomes one line with a literal ``\x0a`` in it, which is the
    price. U+2028 and U+2029, and the bidirectional overrides, are deliberately not covered:
    no terminal acts on them the way it acts on these.
    """
    lines = [f"the set: {report['outcome']} (exit {report['exit_code']})"]
    if report["error"]:
        lines.append(f"  {report['error']}")
    for asset in report["assets"]:
        # The entity first and its rows indented under it: the grouping the report carries is
        # the grouping a person reads, or a set of hundreds of rows is a wall of them.
        lines.append(
            f"  {asset['verdict']:<12} {asset['kind']} `{asset['name']}` at {asset['path']}"
        )
        lines += [
            f"    {entry['verdict']:<12} {entry['id'] or '-'} -- {entry['found_as']} "
            f"({entry['outcome']}, {entry['origin']})"
            + (f"; {entry['note']}" if entry["note"] else "")
            for entry in asset["properties"]
        ]
    lines += [
        f"  translated `{entry['from']}` to `{entry['to']}` in {entry['path']} (by {entry['rule']})"
        for entry in report["translations"]
    ]
    lines += [
        f"  wrote {entry['path']} (it belongs at {entry['to']})" for entry in report["written"]
    ]
    lines += [f"  advice: {line}" for line in report["advice"]]
    return "\n".join(_plain(line) for line in lines) + "\n"


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


def _nothing_there(inputs: Inputs) -> list[str]:
    """Every path the composition names that nothing can be read from, and why, one each.

    Asked before the set is read, and here rather than in the reading, because the reading
    opens a named skill folder by asking for its skill file and so answers a path nothing is
    at with the words for a folder that holds no skill file. That sends a person with a typo
    in the path looking for a `SKILL.md` inside a folder nobody has. Which paths were named
    is `PARTS`, the reading's own list of them, so a part added there is asked about here
    without a line added.

    A link pointing at nothing is named as the link it is, and so is a loop of them: the
    reading has no word for either -- it asks whether there is a skill file at the path, and
    a link leading nowhere answers no -- so it too would be reported as a folder without a
    skill file, which is the same false blame in a narrower door. What is wrong is the link,
    and what a person has to go and look at is what it points at, so the refusal says both.
    """
    named: list[Path] = []
    for part in PARTS:
        # A part may be absent -- `plugin` as `None`, a folder tuple as an empty one -- and an
        # absent part is not a path that is missing. Every part that is there is a path or a
        # tuple of them, which is the whole of what the composition can hold.
        value = getattr(inputs, part)
        if value is None:
            continue
        named += [value] if isinstance(value, Path) else list(value)
    absent = []
    for path in named:
        # The link first, because `exists()` follows one and answers `False` for both cases:
        # asked the other way round, a link leading nowhere reads as a path with nothing at
        # it, and the report would name a folder the person can see is there.
        # `os.readlink` and not `resolve()`: it says what the link itself says, and a loop of
        # links raises out of `resolve()` -- which is one of the two cases this is about.
        if path.is_symlink() and not path.exists():
            absent.append(
                f"{path} is a symbolic link to {os.readlink(path)}, and there is nothing "
                "this run can read at the other end of it"
            )
        elif not path.exists():
            absent.append(f"there is nothing at {path}")
    return absent


def _hooks_of(asset: Asset) -> Mapping[str, Any]:
    """The hooks an entity declares in its header, or none: only a mapping is a set of them."""
    declared = asset.frontmatter.get(HOOKS_KEY)
    return declared if isinstance(declared, Mapping) else {}


def _assess(
    asset: Asset,
    gaps: Mapping[str, Gap],
    target: EnvSpec,
    translation: Rules,
    scope: Scope,
) -> tuple[Assessed, list[str]]:
    """One entity of the set: its rows, its own verdict, and the lines it owes the reader.

    A skill is the one kind this command assembles, so it is the one kind asked where its
    parts go: `_left_behind` is read off the layout of the target alone, before and whether
    or not any bytes are asked for, because what the transfer costs is settled by the two
    descriptions and never by `--out`.

    An asset with no name is the named part itself rather than an entity of it -- an empty
    folder, a path the rules keep out, a file nobody declared. It is judged like any other,
    and assembled nowhere: there is no name to assemble it under.
    """
    properties, advice = _judge(asset.findings, gaps, target, translation)
    valued, said, applied = _translated(asset, target, translation)
    properties += valued
    advice += said
    verdict = worst(entry.verdict for entry in properties)
    if asset.kind is not Kind.SKILL or not asset.name:
        return (
            Assessed(asset, asset.name, None, verdict, tuple(properties), tuple(applied)),
            advice,
        )
    name = _skill_name(asset.path, asset.frontmatter)
    stayed = _left_behind(target, scope, properties, _hooks_of(asset))
    # A part with nowhere to go did not cross, whatever its row says about being reproduced:
    # exit code 0 on a run that left one behind would be this command telling a caller there
    # is nothing here to look at.
    if stayed:
        verdict = worst([verdict, Verdict.LOSSY])
    assembled = Assessed(
        asset,
        name,
        _assembled_name(name, target.environment),
        verdict,
        tuple(properties),
        tuple(applied),
    )
    return assembled, [*advice, *stayed]


def convert(
    inputs: Inputs,
    source: str | None,
    target: str | None,
    *,
    root: str | Path = "specs",
    out: str | Path | None = None,
    scope: Scope = Scope.PROJECT,
    allow_stale: bool = False,
) -> Conversion:
    """Read the set, judge every property of every entity in it, and report what it costs.

    ``inputs`` is the composition of the set -- folders of skills, of subagents, of commands,
    the rule files, the manifest -- and any part of it may be absent. ``source`` and
    ``target`` name the two environments as ``vendor/environment@version``; neither version
    is inferred, and a missing or unreadable one ends the run at ``undecidable`` rather than
    at a guess. A set that cannot be read ends it at exit code 6. Both still produce a
    report: a run that refuses and says nothing machine-readable about the refusal cannot be
    acted on by whatever called it.

    The verdict of the run is the worst of the whole set, exactly as the verdict of one
    entity is the worst of its rows. Without ``out`` nothing is written and the report is the
    whole answer. With it, every skill of the set is assembled under ``out`` at the paths the
    target description names, at the level ``scope`` chooses.
    """
    assessed: list[Assessed] = []
    advice: list[str] = []
    written: list[dict[str, str]] = []
    # Until the assembly table has judged something there is no verdict to keep, and
    # "we could not read enough to say" is what `undecidable` means. Once it has, that
    # verdict stands even if the run then fails to write: being unable to put the files
    # somewhere is not a judgement about what the set loses in the transfer.
    verdict = Verdict.UNDECIDABLE
    # Which side of the run an operating system error came from, and so which code answers
    # for it: while the descriptions are being read it is code 3, like every other way of not
    # knowing what the two environments say; from there on it is the set, code 6.
    # The writing side names its own code where it writes, so it never arrives here as one.
    side = EXIT_CODE[Verdict.UNDECIDABLE]
    ground = ""
    try:
        gaps, target_spec = _gaps(root, source, target, allow_stale)
        side = UNREADABLE
        absent = _nothing_there(inputs)
        if absent:
            raise ConvertError(
                "; ".join(absent) + ". No part of a set could be read from it: the "
                "composition names what this run reads, and a path in it that leads nowhere "
                "is a path to correct rather than a set to judge",
                UNREADABLE,
            )
        found = read(inputs)
        # Asked once, and before the branch below rather than inside it: whether the target
        # names a place for a skill file at all is read off its layout, so the answer -- and
        # the exit code -- is the same whether or not the caller asked for the bytes. Asked
        # only of a set that holds a skill: a set of rule files loses nothing by a target
        # that names nowhere to put a skill.
        if any(asset.kind is Kind.SKILL and asset.name for asset in found):
            ground = _skills_root(target_spec, scope)
        for asset in found:
            entity, said = _assess(asset, gaps, target_spec, inputs.translation, scope)
            assessed.append(entity)
            advice += said
        verdict = worst(entity.verdict for entity in assessed)
        # An undecidable run assembles nothing: the transferable half of a set whose other
        # half nobody documented is a folder that looks converted and is not.
        if out is not None and verdict is not Verdict.UNDECIDABLE:
            # One spelling of `out` from here down. Every check below counts the levels of a
            # destination by text -- `_under` against a collapsed path, `_links_on_the_way`
            # against `out` itself -- so a `..` the caller typed and a `..` collapsed away
            # are two paths that name one folder, and levels compared across the two match
            # nowhere: a link partway down goes unasked and is written through, on a run the
            # report then calls clean.
            out_dir = Path(os.path.normpath(out))
            parts: list[_Part] = []
            for entity in assessed:
                if entity.assembled_name is None:
                    continue
                planned, asked = _plan(
                    entity.asset.path,
                    out_dir,
                    target_spec,
                    scope,
                    entity.properties,
                    _hooks_of(entity.asset),
                    root=ground,
                    assembled_name=entity.assembled_name,
                    translations=entity.translations,
                )
                parts += planned
                advice += asked
            # One plan for the whole set, checked whole before the first byte: two skills of
            # one set aimed at one destination is the same collision as two parts of one
            # skill, and a check made per entity would not see it.
            written, linked = _assemble(out_dir, parts)
            advice += linked
    except (ConvertError, ReadError, OSError) as error:
        # Three shapes of refusal and one answer: what this module raised, what the reading of
        # the set raised and what the filesystem raised all leave as a report and a code, so
        # that reading the answer never costs a caller knowing which exceptions live in here.
        if isinstance(error, ConvertError):
            stopped = error
        elif isinstance(error, ReadError):
            # The reading carries no code of its own: every one of its refusals is about a
            # path the caller named, which is the set this run could not read.
            stopped = ConvertError(str(error), UNREADABLE)
        else:
            # Named by the error and not by the argument: a description of this repository
            # that would not open is not the caller's set, and saying it was sends a person
            # to read the wrong file for a fault that is not in it.
            stopped = ConvertError(
                f"{error.filename}: could not be read ({error})"
                if error.filename
                else f"the set could not be read ({error})",
                side,
            )
        # A refusal that exits with one of the table's own codes is that verdict: not
        # knowing where the set goes is not knowing what the transfer amounts to. Which
        # codes those are is `REFUSAL_VERDICT`, and the rest leave the computed one alone.
        verdict = REFUSAL_VERDICT.get(stopped.exit_code, verdict)
        report = _report(
            source,
            target,
            inputs.translation.version,
            verdict,
            stopped.exit_code,
            assessed,
            advice,
            written,
            str(stopped),
        )
        return Conversion(verdict, stopped.exit_code, report, _summary(report))
    report = _report(
        source,
        target,
        inputs.translation.version,
        verdict,
        EXIT_CODE[verdict],
        assessed,
        advice,
        written,
        None,
    )
    return Conversion(verdict, EXIT_CODE[verdict], report, _summary(report))
