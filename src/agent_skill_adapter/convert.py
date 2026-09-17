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

Nothing is written without ``out``. With it, every entity the target has a root for is
assembled under that folder at the paths the target description names -- every one of them
read from its ``layout``, so that what this command believes about the target environment
is only ever what the description says, and is re-checked when the description is. An
entity of a kind the target names no root for is written nowhere and said out loud instead:
a file put where nothing reads it is the silence this command exists to break.
"""

from __future__ import annotations

import json
import os.path
import re
import shutil
import sys
from collections.abc import Callable, Container, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from agent_skill_adapter.assets import (
    BLOCK,
    DROPPED,
    EMPTY,
    EVENT,
    FRONTMATTER_CLOSE,
    HOOKS_KEY,
    LINKED,
    PARTS,
    PLUGIN_MANIFEST,
    RULES_FILE,
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
from agent_skill_adapter.assets import (
    UNREADABLE as UNREADABLE_PATH,
)
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

NAMES_A_PATH = (SKILL_DIR, SKILL_TOP)
"""The entry id prefixes that name a path inside a skill bundle rather than a field of it.

What such an id was asked about is a file or a directory, which is what the one rule for an
undeclared path is about (FR-30). Every other id names a header key, an event or a decision,
and a rule about files has nothing to say about those.
"""

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
    UNREADABLE_PATH: Outcome.UNKNOWN,
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


NO_ROOM_FOR = {
    Kind.COMMAND: (
        "no entry with this id in either description, and the target names no root for one "
        "either: there is nothing for a command to become and nowhere for the file to go, "
        "so it is left where it is rather than copied where nothing would read it. Call the "
        "skill the command wraps by its own name -- a skill of the target is invoked by "
        "name and needs no wrapper -- or move what the command did into that skill's body"
    ),
}
"""Why an entity of this kind does not cross, in place of the plain silence `UNDECLARED`.

Keyed by the kind of entity and not by the entry id, because what is wrong is the kind: a
command has no counterpart in the target and no place to be put, and one row per command
has to say all three of what it is, why it stays and what to do instead (FR-21, FR-22).
A kind absent here gets `UNDECLARED`, which is the whole of what is known about it.
"""


class Scope(str, Enum):
    """Which level of the target environment the skill is assembled for.

    ``project`` by default: writing into someone's home folder because no level was named
    is changing their environment in passing.
    """

    PROJECT = "project"
    USER = "user"


ROOT_ENTRY = {
    Kind.SKILL: {Scope.PROJECT: "skills.project", Scope.USER: "skills.user"},
    Kind.SUBAGENT: {Scope.PROJECT: "agents.project", Scope.USER: "agents.user"},
    # One entry for both levels, which is the one place a level is not the caller's to
    # choose: the user-level entry of a target may be a single shared document rather than
    # a folder of files, and appending somebody else's rules to a document they wrote is
    # not a transfer. A kind absent from this table is assembled nowhere at all.
    Kind.RULES: {Scope.PROJECT: "rules.project", Scope.USER: "rules.project"},
}
"""Where an entity of each kind lives in an environment, by the level it is installed at."""

PLUGINS_ROOT = {Scope.PROJECT: "plugins.project", Scope.USER: "plugins.user"}
PLUGIN_INSIDE = {
    Kind.SKILL: "plugin.dir.skills",
    Kind.SUBAGENT: "plugin.dir.agents",
    Kind.RULES: "plugin.dir.rules",
}
PLUGIN_FILE = "plugin.file"
PLUGIN_BESIDE = "plugin.file."
"""Where the parts of a set that crosses as a plugin go, in place of the roots above.

A composition that names a manifest is a plugin, and a plugin of the target holds its own
skills, rules and subagents inside its folder: the environment finds them by that structure
and the manifest lists none of them (D02). So the roots move inside the plugin, kind for
kind, and the same `ROOT_ENTRY` table says which kinds have a place at all.

`PLUGIN_BESIDE` is the prefix of the other files a plugin folder holds -- its own hooks and
its own MCP configuration. They are read off the layout rather than named here, so a file
the target documents tomorrow is accounted for without an edit to this module, exactly as
an undocumented frontmatter key is. `PLUGIN_FILE` is not one of them: it has no trailing
dot, and it is the manifest itself.
"""

SKILLS_ROOT = ROOT_ENTRY[Kind.SKILL]
HOOKS_FILE = {Scope.PROJECT: "hooks.project", Scope.USER: "hooks.user"}
SKILL_FILE = "skill.file"
"""Entry ids the assembly asks the target description for. Ids, and never paths.

Every path this command writes to is read from the ``layout`` of the target description
under one of these ids. A path spelled out here would be a claim about the target
environment kept out of the freshness check that guards every other such claim.
"""

SKILL_NAME = "<skill-name>"
PLUGIN_NAME = "<plugin-name>"
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


ASKS_ITS_PLACE = {Kind.RULES: RULES_FILE}
"""The id an entity of this kind asks about itself, where that question is about its place.

A rule file has no format of its own for a description to document: what decides whether it
crosses is whether the target names a root for rule files, which is the `ROOT_ENTRY` the
assembly already puts it at. Asked under an id of its own instead -- one no description
carries, because there is nothing there to carry -- the very same run copies the file
exactly where the target says and calls the transfer a loss (FR-19, G02). A command is
deliberately not here: the target names no root for one, and `command.file` staying
unanswered is the honest whole of what happens to it.
"""


def _about_its_place(entry_id: str, kind: Kind, scope: Scope, plugin: str | None) -> str:
    """``entry_id``, or the id of the place the target names, where that is the question.

    A composition that names a manifest crosses as a plugin, and every root moves inside its
    folder (`_root_of`) -- a rule file among them, judged by `plugin.dir.rules` rather than
    by `rules.project`/`rules.user` once it is a plugin's, or the row would name a place the
    file was never headed for.
    """
    if ASKS_ITS_PLACE.get(kind) != entry_id:
        return entry_id
    inside = PLUGIN_INSIDE.get(kind) if plugin is not None else None
    return ROOT_ENTRY[kind][scope] if inside is None else inside


def _judge(
    findings: Sequence[Finding],
    gaps: Mapping[str, Gap],
    target: EnvSpec,
    translation: Rules,
    kind: Kind,
    scope: Scope,
    plugin: str | None,
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
            asked_by.setdefault(_about_its_place(entry_id, kind, scope, plugin), []).append(
                finding.found_as
            )
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
            source_says, target_says = None, None
            # An id that names a path gets the rules' own words for a file nobody declared,
            # exactly as `_asked_nothing` gives them to one found beside the bundle: the
            # same rule decides what happens to both, and two wordings of that rule would
            # be two rules as soon as either of them changed.
            note = (
                translation.undocumented.note
                if entry_id.startswith(NAMES_A_PATH)
                else NO_ROOM_FOR.get(kind, UNDECLARED)
            )
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

TOOL_FORM_ENTRY = f"{TOOL_NAMES_ENTRY}.form"
"""The entry whose value is the shape the tool names of a subagent are written in.

An entry of the target description like any other, and asked of it like any other: what
shapes the field may be written in is something the documentation of an environment either
names or does not, and this command reads the answer rather than holding one. The field
itself is `TOOL_NAMES_ENTRY`; this is the one thing about its value that is not one of the
names inside it.

# ponytail: one field has a form worth asking about today, so one id is spelled here. The
# way up, should a second field need it, is a suffix applied to whichever entry is being
# translated, which costs nothing here and would be a rule nobody has needed yet.
"""

AS_A_LIST = "list"
AS_A_STRING = "comma-separated string"
"""The two shapes a field of names is written in, in the words the descriptions use.

Words about a format and not about a vendor: a list and a string of names separated by
commas are shapes of YAML, and both source environments of this pair write the field either
way. Which of them a target accepts is its description's to say, and turning one into the
other is the translation rules' -- these are only the names the two sides say it in.
"""

NO_FORM_SET = (
    "the target description names no set of forms this field's value may be written in, so "
    "it crosses in the form the source wrote it -- and the form is not a matter of taste "
    "here: an environment that reads the field as a list of names and is handed one string "
    "of them has no field at all, and a file it will not read is a file it says nothing "
    "about. Name the forms in the description of the target to have this run translate them"
)
"""Why the shape of a value the target says nothing about is a row and not a silent carry.

The same rule as every other value (Decisions 1): silence about a set is not permission to
use it. The row says what the silence costs, because this is the one value whose form
decides whether the entity is read at all.
"""

NO_WAY_TO_WRITE = (
    "the rules turn the form of this value into one this command has no way of writing "
    "down, so it crosses in the form the source wrote it; what the forms are called is for "
    "the descriptions and the rules to say and writing one out is code, so the two have "
    "drifted apart and this row is the whole of what is left to say about it"
)
"""Why a form named by both documents and unknown to the writer below is a row.

Reported rather than applied: a rule recorded as applied and never written would be the
report claiming a file this run did not produce.
"""

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


def _onto(
    entry_id: str,
    was: str,
    found_as: str,
    target: EnvSpec,
    translation: Rules,
    apply: Callable[[str, str, str], None],
    *,
    no_set: str = NO_VALUE_SET,
    writable: Container[str] | None = None,
) -> Property | None:
    """``was`` put into the target's vocabulary: the rule is applied, or a row says why not.

    The one ladder every translated value goes down, and the order of its rungs is the order
    the two documents answer in. The description decides what the acceptable values are,
    because that is a fact about the environment; the rules decide what an unacceptable one
    becomes, because that is a decision of ours; and a counterpart the description's own set
    does not carry is not written, because the two disagree and neither is this run's to
    correct. ``writable`` is the last rung and belongs to neither document: a counterpart
    both of them name and this command cannot write down is a row rather than a promise.
    """
    allowed = _closed_set(target, entry_id)
    if allowed is None:
        return _unusable(entry_id, found_as, no_set)
    if was in allowed:
        return None
    became = translation.value_of(entry_id, was)
    if became is None:
        return _unusable(entry_id, found_as, NO_COUNTERPART)
    if became not in allowed:
        return _unusable(entry_id, found_as, REFUSED_BY_THE_TARGET)
    if writable is not None and became not in writable:
        return _unusable(entry_id, found_as, NO_WAY_TO_WRITE)
    apply(entry_id, was, became)
    return None


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
            # The shape the names are written in, asked apart from the names themselves and
            # of its own entry: an environment that reads this field as a list and is handed
            # a string of it reads no field at all, and a subagent whose field it cannot read
            # is one it never mentions. Which shapes it reads is the description's to name.
            form = AS_A_LIST if isinstance(value, list) else AS_A_STRING
            shaped = _onto(
                TOOL_FORM_ENTRY,
                form,
                f"frontmatter key `{key}` written as a {form}",
                target,
                translation,
                apply,
                no_set=NO_FORM_SET,
                writable=WRITTEN_AS,
            )
            rows += [] if shaped is None else [shaped]
            continue
        if _closed_set(target, entry_id) is None and entry_id not in translation.value_maps:
            continue
        was = _text(value, asset.path, key, entry_id)
        row = _onto(
            entry_id,
            was,
            f"frontmatter key `{key}` set to `{was}`",
            target,
            translation,
            apply,
        )
        rows += [] if row is None else [row]
    return rows, advice, applied


TRIGGER_ENTRY = "rules.frontmatter.trigger"
"""The entry whose value decides whether a rule file the target holds is loaded at all.

An id, like every other id here, and never the value: what the field may be set to is the
closed set the target description names, and which of those values a file that names none
gets is the translation rules' to say. Proved by running the environment (D01): a rule
file without this key sits in the rules folder and never takes effect.
"""

NOTHING_WRITTEN = ""
"""How the rules spell the value of a field a file does not carry, as the left side of a pair.

A rule file is carried whole and its header is nobody's business but its author's, so the
only value there is to translate is the one that is not there. Spelled as the empty string
rather than as a rule of its own shape, so that the pair reads as every other pair reads --
what was written, and what it becomes -- and needs nothing of the rules file format.
"""


def _trigger(
    asset: Asset, target: EnvSpec, translation: Rules
) -> tuple[list[Property], list[dict[str, str]]]:
    """The header a rule file is missing, as the rule that adds it -- or the row saying why not.

    A file that declares the key already keeps what it declares: adding what is missing is
    the whole of what this is entitled to do, and a value the author chose is not ours to
    redecide. Otherwise the two documents answer between them, exactly as they do for any
    other value: the description names the set, the rules name which of it a file with
    nothing written gets, and a run missing either says so in a row instead of guessing.
    """
    key = TRIGGER_ENTRY.rpartition(".")[2]
    if _declares(asset.path, key):
        return [], []
    found_as = f"no frontmatter key `{key}`"
    allowed = _closed_set(target, TRIGGER_ENTRY)
    became = translation.value_of(TRIGGER_ENTRY, NOTHING_WRITTEN)
    if allowed is None:
        return [_unusable(TRIGGER_ENTRY, found_as, NO_VALUE_SET)], []
    if became is None:
        return [_unusable(TRIGGER_ENTRY, found_as, NO_COUNTERPART)], []
    if became not in allowed:
        return [_unusable(TRIGGER_ENTRY, found_as, REFUSED_BY_THE_TARGET)], []
    return [], [
        {
            "path": str(asset.path),
            "id": TRIGGER_ENTRY,
            "from": NOTHING_WRITTEN,
            "to": became,
            "rule": f"{TRIGGER_ENTRY} of the translation rules {translation.version}",
        }
    ]


MANIFEST_FIELD = f"{PLUGIN_MANIFEST}."
"""The prefix under which one field of a plugin manifest is asked about.

Spelled from the id of the manifest itself, the way `skill.frontmatter.<key>` is spelled
from a skill's: a manifest is judged field by field, and every field is a question put to
the descriptions rather than a name this command keeps a list of.
"""


def _manifest_fields(path: Path) -> dict[str, Any]:
    """The manifest read as data: a mapping of fields, or a refusal naming the file.

    Somebody else's file and a trust boundary: one that will not parse is a path the caller
    can go and look at, which a traceback naming this module is not.

    # ponytail: top-level fields only, which is every field the specification names (9).
    # A nested one earns its row when a description declares a nested id to ask under.
    """
    try:
        data = json.loads(_text_of(path))
    except ValueError as error:
        raise ConvertError(
            f"{path}: could not be read as a manifest ({error})", UNREADABLE
        ) from error
    if not isinstance(data, dict):
        raise ConvertError(
            f"{path}: a manifest is a mapping of fields, and this names none", UNREADABLE
        )
    fields: dict[str, Any] = data
    return fields


def _manifest(
    asset: Asset,
    gaps: Mapping[str, Gap],
    target: EnvSpec,
    translation: Rules,
    scope: Scope,
    plugin: str | None,
) -> tuple[list[Property], list[str]]:
    """Every field of a plugin manifest as a row, and one row for the rewrite left undone.

    The fields are asked of the two descriptions exactly as a skill's header keys are, so a
    field the target's own format has no place for is a row and never a silent omission
    (FR-32), and a field nobody documented is `unknown` rather than something invented here.
    """
    findings = [
        Finding(f"manifest field `{key}`", (f"{MANIFEST_FIELD}{key}",))
        for key in _manifest_fields(asset.path)
    ]
    beside = _beside_a_manifest(asset, target)
    findings += [Finding(f"`{name}` beside the manifest", (entry_id,)) for entry_id, name in beside]
    rows, advice = _judge(findings, gaps, target, translation, asset.kind, scope, plugin)
    return rows, [*advice, *(f"`{name}` {READ_BEFORE_ENABLING}" for _, name in beside)]


READ_BEFORE_ENABLING = (
    "carries commands the target environment will run: a hooks file names what runs around "
    "an action of the agent, and an MCP configuration names servers it launches. It crossed "
    "whole and unread -- this command weighs what two documents say about file formats, and "
    "nothing anywhere tells it what a command does -- so read it before enabling the plugin "
    "in an environment of your own, on the footing of anything else executable somebody "
    "hands you. The row above says it arrived, which is not the same as saying it is safe "
    "to run"
)
"""Why a file that crossed cleanly is still worth a line of its own.

`clean` is a verdict about the transfer: the file reached the place the target documents,
whole. It says nothing about what is inside, and these are the only files of a set whose
contents become commands on somebody else's machine. Carried in silence, they would move the
gap this command exists to close -- between what is on disk and what it does -- one step
along instead of closing it (FR-3).
"""


def _beside_a_manifest(asset: Asset, target: EnvSpec) -> list[tuple[str, str]]:
    """The plugin's own files sitting beside its manifest: the entry each asks, and its name.

    Which files those are is the target's layout to say -- every entry under
    :data:`PLUGIN_BESIDE` -- so this asks about the names that description carries and keeps
    none of its own. A name the target documents and the set does not hold earns nothing:
    there is no file to account for, and a row about one would tell the owner of a plugin
    without hooks that their hooks did not cross.

    The entry and not a row, so that the two descriptions judge these exactly as they judge
    every other part: the target names a place for the file, which is what `reproduced`
    means here and what puts the file in the plan. The name comes back beside it because the
    line of advice these earn is about the file and not about the entry.
    """
    folder = Path(os.path.abspath(asset.path)).parent
    return [
        (entry.id, PurePosixPath(entry.path).name)
        for entry in sorted(target.layout, key=lambda item: item.id)
        if entry.id.startswith(PLUGIN_BESIDE)
        and (folder / PurePosixPath(entry.path).name).is_file()
    ]


def _rewritten(asset: Asset, properties: Sequence[Property]) -> str:
    """The manifest in the target's format: the fields it documents, and not one besides.

    Which those are is read off the rows the fields already earned -- a field the target
    documents came back `reproduced`, and one it has no place for came back `unknown` and
    is dropped, having said so in a row of its own. So the format of the target's manifest
    is never a list of names kept here: it is whatever its description declares, and a
    field the vendor adds tomorrow crosses as soon as the description carries it.

    Asked of the outcome and not of the verdict, though the verdict is what the rest of the
    run adds up: `out-of-scope` is `clean` too, and it means the field cost the transfer
    nothing precisely because it is not carried. Read off the verdict, such a field would be
    written into the manifest by the same run whose row for it says it was left out.
    """
    documented = {
        entry.id for entry in properties if entry.id and entry.outcome is Outcome.REPRODUCED
    }
    fields = {
        key: value
        for key, value in _manifest_fields(asset.path).items()
        if f"{MANIFEST_FIELD}{key}" in documented
    }
    return json.dumps(fields, indent=2, ensure_ascii=False) + "\n"


def _layout(spec: EnvSpec, entry_id: str) -> str | None:
    """The path the description gives ``entry_id``, or ``None`` when it names none."""
    return next((entry.path for entry in spec.layout if entry.id == entry_id), None)


def _inside_a_plugin(target: EnvSpec, scope: Scope, entry_id: str, plugin: str) -> str | None:
    """One path inside a plugin folder, measured from the root the target puts plugins in.

    Two layout entries joined and neither spelled: where the target keeps its plugins, and
    what it says one plugin folder holds. ``None`` where the target names either of them
    nowhere, which is the same answer every other missing place gets.
    """
    root = _layout(target, PLUGINS_ROOT[scope])
    inside = _layout(target, entry_id)
    if root is None or inside is None:
        return None
    return f"{root.rstrip('/')}/{inside}".replace(PLUGIN_NAME, plugin)


def _root_of(target: EnvSpec, kind: Kind, scope: Scope, plugin: str | None) -> str | None:
    """Where an entity of ``kind`` goes: the root of its own kind, or one inside a plugin."""
    if plugin is None:
        entry = ROOT_ENTRY.get(kind)
        return None if entry is None else _layout(target, entry[scope])
    inside = PLUGIN_INSIDE.get(kind)
    return None if inside is None else _inside_a_plugin(target, scope, inside, plugin)


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


def _live(template: str, skill_name: str) -> tuple[Path, Path]:
    """A layout path as a place on this machine, and the root it is measured from.

    The two roots a layout path can open with are the home folder and the workspace root,
    and a path that names neither is measured from the workspace root as well -- which is
    the folder this command was run in. Nothing else here knows any of those three: they
    come out of the description, exactly as ``_destination`` reads them for a staged run.

    The root is one of those two and never the expanded path itself. Returned as its own
    answer, a layout path that is already absolute would arrive as both the destination and
    the root it must stay under, and the check that it does would be true by construction --
    the description, or an edit a vendor makes to it, would be choosing where on this
    machine the command writes. Measured from the workspace instead, such a path is under
    neither root and `_assemble` refuses it exactly as it refuses one leading out of ``out``.
    """
    path = template.replace(SKILL_NAME, skill_name)
    if path.startswith(f"{HOME}/"):
        return Path(os.path.normpath(Path.home() / path[len(HOME) + 1 :])), Path.home()
    if path.startswith(f"{WORKSPACE_ROOT}/"):
        path = path[len(WORKSPACE_ROOT) + 1 :]
    return Path(os.path.normpath(Path.cwd() / path)), Path.cwd()


@dataclass(frozen=True)
class _Where:
    """Where this run puts what it assembles, and what a written part must stay under."""

    out: Path | None
    """The folder the caller named, or ``None`` for the live roots of the target (FR-50i).

    The two are one question asked in two places -- where a part is written, and what it is
    not allowed to leave -- so they are answered together and never by two callers apart.
    """

    def place(self, root: str, inside: str, skill_name: str) -> tuple[str, Path, Path]:
        """One layout path as three: where it belongs, where it is written, and under what.

        ``root`` is the layout entry an entity of this kind lives in and ``inside`` the path
        below it. What a part is held to is never a path the description chose: it is the
        folder the caller named, or -- for a run that installs -- the home folder or the
        workspace the layout path is measured from, which is `_live`'s second answer.
        """
        where, staged = _destination(f"{root.rstrip('/')}/{inside}", skill_name)
        if self.out is None:
            return (where, *_live(f"{root.rstrip('/')}/{inside}", skill_name))
        return where, _under(self.out, staged), self.out


@dataclass(frozen=True)
class _Part:
    """One file or directory of the assembled skill, and the two places it has."""

    label: str
    """Where it came from inside the skill folder."""
    destination: str
    """Where the target description says it belongs."""
    staged: Path
    """Where this run put it: under ``out``, or in the root of the target it belongs in."""
    root: Path
    """The folder this part may not leave -- ``out``, or the target root it is written into.

    Carried per part rather than passed once to the assembly, because a run that installs
    writes into several roots at once and each part is held to the one its destination was
    measured from.
    """
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


def _as_a_list(header: str, key: str) -> str:
    """``header`` with the one-line value of ``key`` written out as a list, item per line.

    The names are read back off the line rather than carried here from where they were
    parsed, so that a rule applied to one of them is already in what this writes: the value
    is translated where it stands and then reshaped, and the two never have to agree about
    an order. Written through `yaml` so a name that needs quoting gets it, and indented by
    hand, because a block sequence under a key is what `yaml` writes at column zero.

    # ponytail: a value spelled over several lines -- a folded scalar of names -- is left
    # alone, because only the line that opens the key is read. The way up is the same one
    # `_in_the_value_of` names: the line and column `yaml` already knows for every node.
    """
    lines = header.split("\n")
    for index, line in enumerate(lines):
        opens = _OPENS_A_KEY.match(line)
        if opens is None or opens.group(1).strip().strip("'\"") != key:
            continue
        names = [name.strip() for name in opens.group(2).split(",") if name.strip()]
        written = yaml.safe_dump(names, default_flow_style=False, allow_unicode=True)
        lines[index] = "\n".join([f"{key}:", *(f"  {item}" for item in written.splitlines())])
        break
    return "\n".join(lines)


WRITTEN_AS: dict[str, Callable[[str, str], str]] = {AS_A_LIST: _as_a_list}
"""How a value is put into a form the target names, by the name of that form.

A form the descriptions and the rules agree on and this table has no entry for is reported
and not applied (:data:`NO_WAY_TO_WRITE`): the two documents settle what a value should
look like, and whether this command can produce it is a fact about this command.
"""

TOOL_NAMES_KEY = TOOL_NAMES_ENTRY.rpartition(".")[2]
"""The header key the tool names are written under, taken back off its entry id.

The ids of a header field are built from the key as written (`assets`), so the last step of
one is the key again -- the same way `_with_translations` reads a key out of every other
rule it applies, and for the same reason: no table of pairs to keep in step with anything.
"""


def _text_of(path: Path) -> str:
    """The text of ``path``, with bytes that are not UTF-8 answered rather than raised.

    Every file this module opens belongs to somebody else, and a `UnicodeDecodeError` is
    neither of the two shapes of refusal answered for here: it is a `ValueError`, so it
    passes straight through the handler that turns a filesystem fault into a report and
    leaves the caller a traceback instead of an exit code and a path to go and look at.
    The reading of the set already refuses such a file in these words (`assets.frontmatter`);
    the files that reach this module -- a rule file carried whole -- never passed through it.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ConvertError(f"{path}: not UTF-8 text ({error})", UNREADABLE) from error


def _header_of(text: str) -> tuple[str, int] | None:
    """The text of the frontmatter and where it closes, or ``None`` when there is none.

    Both halves are needed by every caller that edits a header: the text to read the keys
    out of, and the offset to put the rest of the file back at.
    """
    if not text.startswith("---"):
        return None
    closing = FRONTMATTER_CLOSE.search(text, 3)
    return None if closing is None else (text[3 : closing.start()], closing.start())


def _declares(path: Path, key: str) -> bool:
    """Whether the file at ``path`` opens with a header that sets ``key`` at the top level.

    A line that is indented continues the value of the key above it, so only a line that
    opens a key of its own can be the one asked about -- the same rule `_in_the_value_of`
    reads a header by, and the same one that keeps a nested `trigger:` from answering here.
    """
    header = _header_of(_text_of(path))
    if header is None:
        return False
    return any(
        opens is not None and opens.group(1).strip().strip("'\"") == key
        for opens in (_OPENS_A_KEY.match(line) for line in header[0].split("\n"))
    )


def _with_trigger(path: Path, applied: Sequence[Mapping[str, str]]) -> str | None:
    """The rule file with the keys the rules add at the top of its header, or ``None``.

    Added and never merged: `_trigger` has already established that the file declares none
    of these keys, so there is nothing of the author's to overwrite. A file that carries no
    header at all gets one, which is the case the whole rule exists for -- a rule file of
    the source environment is plain Markdown, and plain Markdown is what the target leaves
    on disk unread.
    """
    if not applied:
        return None
    text = _text_of(path)
    keys = [(rule["id"].rpartition(".")[2], rule["to"]) for rule in applied]
    added = "".join(f"{key}: {value}\n" for key, value in keys)
    header = _header_of(text)
    if header is None:
        return f"---\n{added}---\n\n{text}"
    return f"---\n{added.rstrip()}{header[0]}{text[header[1] :]}"


def _with_translations(path: Path, applied: Sequence[Mapping[str, str]]) -> str | None:
    """The skill file with every applied rule in its header, or ``None`` when none were.

    The report says a value was translated, and this is what makes that true of the file the
    caller ends up with: without it the run would state a rewrite that never happened and
    call the transfer clean while the target's own set still refuses what was written.

    The body below the header is not touched at all, and neither is a key no rule applied to.
    """
    if not applied:
        return None
    text = _text_of(path)
    found = _header_of(text)
    if found is None:
        # Unreachable: a file whose header never closes was refused while it was being read,
        # and there would be no translation to apply to it. Answered rather than asserted,
        # because the answer is the file exactly as it was found.
        return None
    header, closes = found
    for rule in applied:
        if rule["id"] == TOOL_FORM_ENTRY:
            continue
        # The key is the last step of the entry id: the ids of a header field are built from
        # the key as written (`assets`), so this takes it back without a table of pairs.
        header = _in_the_value_of(header, rule["id"].rpartition(".")[2], rule["from"], rule["to"])
    # The shape of a value after the values themselves, and never before: reshaping reads the
    # names back off the line it rewrites, so a name translated afterwards would be one this
    # run reported as translated and wrote in the spelling it came in.
    for rule in applied:
        if rule["id"] == TOOL_FORM_ENTRY:
            header = WRITTEN_AS[rule["to"]](header, TOOL_NAMES_KEY)
    return f"---{header}{text[closes:]}"


CONTENT = {Kind.SUBAGENT: _with_translations, Kind.RULES: _with_trigger}
"""How the one file of an entity is rewritten on the way across, by the kind of entity.

A subagent crosses with the values of its header put into the target's vocabulary; a rule
file crosses with the header that makes the target read it at all. A kind absent here is
copied byte for byte, which is what a file nobody has a rule about deserves.
"""


def _plan(
    entity: Assessed,
    where_: _Where,
    target: EnvSpec,
    scope: Scope,
    translation: Rules,
    plugin: str | None,
) -> tuple[list[_Part], list[str]]:
    """What one entity of the set contributes to the plan, and what it asks of a person.

    Four answers, and the kind of the entity picks between them. A skill is a folder with
    parts, and has a plan of its own. A subagent and a rule file are one file each, put at
    the root the target names for their kind. A record of a named part rather than of an
    entity carries the paths nobody declared, whose fate is the translation rules' to
    decide. Everything else -- a command above all -- is assembled nowhere, and its report
    row is the whole of what this run does about it.
    """
    asset = entity.asset
    if not entity.name:
        return _undocumented(entity, where_, translation)
    if entity.assembled_name is None:
        return [], []
    if asset.kind is Kind.MANIFEST:
        return _plan_manifest(entity, where_, target, scope, entity.assembled_name)
    root = _root_of(target, asset.kind, scope, plugin)
    if root is None:
        # Unreachable: `_nowhere` asked the same question while the entity was judged, and
        # an entity with no root to go to was left without an assembled name. Answered and
        # not asserted, because the answer -- assemble nothing -- is the right one anyway.
        return [], []
    if asset.kind is Kind.SKILL:
        return _plan_skill(
            asset.path,
            where_,
            target,
            scope,
            entity.properties,
            _hooks_of(asset),
            translation,
            root=root,
            assembled_name=entity.assembled_name,
            translations=entity.translations,
        )
    rewrite = CONTENT.get(asset.kind)
    where, staged, under = where_.place(root, entity.assembled_name, entity.name)
    return [
        _Part(
            asset.path.name,
            where,
            staged,
            under,
            copied_from=asset.path,
            content=None if rewrite is None else rewrite(asset.path, entity.translations),
        )
    ], []


def _plan_manifest(
    entity: Assessed, where_: _Where, target: EnvSpec, scope: Scope, plugin: str
) -> tuple[list[_Part], list[str]]:
    """The rewritten manifest, at the place the target gives a plugin's own manifest.

    The plugin folder is what the environment reads a plugin by, and everything else of the
    set is written inside it, so this is the file that makes the folder a plugin at all.
    Its place is two layout entries like every other, and `_assess` asked for both before
    the entity was given a name to be assembled under.
    """
    root = _layout(target, PLUGINS_ROOT[scope])
    inside = _layout(target, PLUGIN_FILE)
    if root is None or inside is None:
        # Unreachable for the same reason `_plan`'s own is: `_nowhere` asked these two
        # questions while the manifest was judged and left it unnamed if either went
        # unanswered. Answered rather than asserted, the answer being the right one anyway.
        return [], []
    where, staged, under = where_.place(root, inside.replace(PLUGIN_NAME, plugin), plugin)
    parts = [
        _Part(
            entity.asset.path.name,
            where,
            staged,
            under,
            copied_from=entity.asset.path,
            content=_rewritten(entity.asset, entity.properties),
        )
    ]
    # The plugin's own hooks and MCP configuration, carried whole into the folder this run
    # is writing. Copied and not merged, unlike a skill's hook entry: that one belongs in a
    # file of the whole environment which may already hold somebody else's entries, while
    # these are files of this plugin, at a place the target documents, in a folder that did
    # not exist until this run made it. Which of them cross is read off their own rows.
    folder = Path(os.path.abspath(entity.asset.path)).parent
    for row in entity.properties:
        if row.id is None or not row.id.startswith(PLUGIN_BESIDE):
            continue
        template = _layout(target, row.id)
        if template is None or row.verdict is not Verdict.CLEAN:
            continue
        name = PurePosixPath(template).name
        where, staged, under = where_.place(root, template.replace(PLUGIN_NAME, plugin), plugin)
        parts.append(_Part(name, where, staged, under, copied_from=folder / name))
    return parts, []


STAGED_NOT_PLACED = (
    "is staged under the folder this run was told to assemble into and put in no root of "
    "the target: no description names a place for it, and every place they do name is read "
    "by the target as a folder of entities of one kind -- a path that is not one of those "
    "would be found there and read as a broken one, which is worse than the silence this "
    "command exists to break and contradicts the row telling the caller to place it by hand"
)
"""Why a file the rules say to carry is carried into the result but never into a root.

The rules decide that such a file stays with the set (FR-30); where a file belongs in the
target environment is the target description's to say, and it says nothing. So it crosses
into the result, under the name of the part it was found in, and the caller places it.
"""


NOWHERE_TO_STAGE = (
    "is left where it is: no description names a place for it, this run was told to write "
    "into the roots of the target environment, and every one of those is read as a folder "
    "of entities of one kind -- so there is nowhere to put it that would not be read as a "
    "broken entity. Assemble under `--out` instead to have it carried beside the set"
)
"""Why a run that installs carries no file that no description declares.

A staged run has a folder of its own to put such a file in (:data:`STAGED_NOT_PLACED`); a
run writing into the target's own roots has none, and the rule that they hold entities and
nothing else is the same rule in both places.
"""


def _undocumented(
    entity: Assessed, where_: _Where, translation: Rules
) -> tuple[list[_Part], list[str]]:
    """The paths of a named part that no description declares, under the rule for all of them.

    Which paths those are is the reading's answer -- a finding that asked no entry id and
    gave the undeclared path as its reason -- and what becomes of them is `_carried`'s, the
    same answer it gives the paths inside a bundle.
    """
    return _carried(
        [
            finding.found_as
            for finding in entity.asset.findings
            if not finding.ids and finding.note == UNDECLARED_PATH
        ],
        entity.asset.path,
        where_,
        translation,
    )


def _carried(
    labels: Sequence[str], folder: Path, where_: _Where, translation: Rules
) -> tuple[list[_Part], list[str]]:
    """The one rule for a path the target names no place for, carried out on every one of them.

    The only place that decision is made. It is asked from two sides -- of a path found
    beside a bundle, and of one found inside it -- and a second branch for either of them
    would be a second rule nobody chose (FR-30): that is how a `README.md` one level up came
    to be carried across while the `README.md` inside the bundle stayed where it was.

    ``folder`` is the part or the bundle the paths were found in, and ``labels`` are their
    names inside it. ``skip`` leaves them where they are and ``copy`` brings them into the
    result -- staged under the name of that folder, never in a root of the target
    (:data:`STAGED_NOT_PLACED`). Either way each keeps the report row it earned while the
    set was read: what the rule decides is where a file ends up, never whether it is named.
    """
    if translation.undocumented.action != "copy":
        return [], []
    if where_.out is None:
        return [], [f"`{label}` {NOWHERE_TO_STAGE}" for label in labels]
    parts = []
    for label in labels:
        # The name of the folder and then the path as it was found inside it: the input laid
        # out as it was given, which is the one arrangement of these files anybody has ever
        # stated. Two folders holding a `README.md` each keep one apiece by it.
        staged = f"{folder.name}/{label}"
        parts.append(
            _Part(
                label,
                staged,
                _under(where_.out, staged),
                where_.out,
                copied_from=folder / label,
            )
        )
    return parts, [f"`{part.label}` {STAGED_NOT_PLACED}" for part in parts]


def _plan_skill(
    skill_dir: Path,
    where_: _Where,
    target: EnvSpec,
    scope: Scope,
    properties: Sequence[Property],
    hooks: Mapping[str, Any],
    translation: Rules,
    *,
    root: str,
    assembled_name: str,
    translations: Sequence[Mapping[str, str]] = (),
) -> tuple[list[_Part], list[str]]:
    """What the assembly will write, and what it asks of a person once it has.

    ``root`` is where a skill of the target environment lives, read off the layout by `_plan`
    under the id `ROOT_ENTRY` gives this kind and this level. There is always one here because
    a skill the layout named nowhere for never reached a plan: `_nowhere` answered for it while
    the skill was judged, and left it without the assembled name `_plan` requires.

    A part the target description names no path for is not assembled where a skill goes:
    guessing that would be inventing the target environment's layout. What happens to it
    instead is the one rule the translation states for a path no description gives a place
    to (`_carried`) -- the same rule, and the same words, as for a path found beside the
    bundle. It keeps its row either way, and `_placeless` tells the verdict it did not land
    where the target reads it from -- from the layout alone, whether or not anybody asked
    for this plan, because that is a price the descriptions settle between them.
    """
    parts = []
    for label, inside in _places(target, properties):
        # The other half of the same list: what has a place is written where the target says,
        # what has none goes through the rule below. Neither side decides for itself which
        # half a part is in, or a part could end up in both lists, or in neither.
        if inside is None:
            continue
        where, staged, under = where_.place(root, inside, assembled_name)
        source_file = skill_dir / label
        parts.append(
            _Part(
                label,
                where,
                staged,
                under,
                copied_from=source_file,
                # Only the skill file carries a header, so it is the only part a rule can
                # have been applied to. `None` when none were, and then the bytes are copied
                # exactly as every other part's are.
                content=(
                    _with_translations(source_file, translations) if label == SKILL_MD else None
                ),
            )
        )
    staged_parts, staged_advice = _carried(
        _placeless(target, properties), skill_dir, where_, translation
    )
    parts += staged_parts
    carried, hooks_file = _hook_place(target, scope, properties, hooks)
    if not carried or hooks_file is None:
        return parts, staged_advice
    # Through `_destination` like every other part: a layout path opens with the root it is
    # measured from, and a hooks file spelled `<workspace-root>/...` or `~/...` -- as the
    # descriptions do spell it -- would otherwise reach the report with the placeholder
    # still in it, telling a person to put the entry in a folder named `<workspace-root>`.
    where, _ = _destination(hooks_file, assembled_name)
    if where_.out is None:
        # The entry is staged beside the assembled skill and never merged into the file
        # itself (FR-40), and a run writing into the target's own roots has nowhere to stage
        # it: the alternative is editing a file that belongs to the whole environment and
        # may already hold somebody else's entries, which is the one thing that rule forbids.
        return parts, [
            *staged_advice,
            f"the hook entry of `{assembled_name}` is not written anywhere: it belongs in "
            f"{where}, a file of the whole target environment that this run will not edit, "
            "so add it there yourself -- or assemble under `--out`, which stages it for you",
        ]
    hook_part = _hook_part(where_.out, where, carried)
    return [*parts, hook_part], [
        *staged_advice,
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


def _places(target: EnvSpec, properties: Sequence[Property]) -> list[tuple[str, str | None]]:
    """Every part of the skill folder and the path the target names for it, ``None`` for none.

    The one place that question is answered. It is asked from two sides -- by what is written
    and by what is said to have stayed behind -- and two spellings of it could drift apart on
    the next entry id somebody adds, leaving a part written and called left behind, or written
    and never mentioned. That is the silent disappearance this whole module is written against.
    """
    return [(label, _layout(target, entry_id)) for entry_id, label in _wanted(properties)]


def _placeless(target: EnvSpec, properties: Sequence[Property]) -> list[str]:
    """Every part of the skill folder the target names no path for, by its name inside it.

    Two callers and one answer: what the rule for an undeclared path is carried out on, and
    what tells the verdict the skill did not cross whole. Spelled once, because a part
    written by one and called left behind by the other is the silent disappearance this
    whole module is written against.
    """
    return [label for label, inside in _places(target, properties) if inside is None]


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


def _unregistered_hook(
    target: EnvSpec, scope: Scope, properties: Sequence[Property], hooks: Mapping[str, Any]
) -> list[str]:
    """The line a hook the target fires but registers nowhere earns, or nothing.

    Read off the layout of the target and nothing else: no ``out``, no filesystem. What the
    transfer costs is settled by the two descriptions and the skill folder, so asking for the
    bytes cannot change it -- ``--out`` decides what is written, not what is lost.

    The one thing that can be reproduced in full and still have nowhere to go: the event a
    hook fires on is a capability, and the file the environment registers a hook in is a
    layout entry it owes nothing about for having declared the event. The header itself
    crosses -- `SKILL.md` is copied whole, `hooks:` and all -- so what is lost is not the
    text of the declaration but the only place the environment would have read it from.

    A part of the folder with nowhere to go is not here and was never a thing apart: it goes
    through the one rule for a path no description gives a place to (`_carried`), like every
    other such path, and `_placeless` is what tells the verdict about it.
    """
    carried, hooks_file = _hook_place(target, scope, properties, hooks)
    if not carried or hooks_file is not None:
        return []
    return [
        f"the `{HOOKS_KEY}` key crosses inside {SKILL_MD} and is registered nowhere: "
        f"{target.vendor}/{target.environment} names no file for hook entries, and that "
        "file is where a declaration becomes a hook -- what arrives in the target is the "
        "text of the rule, in a header nothing reads it from"
    ]


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
        out,
        # No rescue argument here, and none needed: every value came through `_portable`,
        # which is where a header meets JSON. A date is already the text ISO 8601 spells,
        # and a shape with no stable text never got this far -- the file was refused as it
        # was read. A rescue here would have turned an unwritable value into whatever
        # `str()` makes of it, unannounced and differently on every run.
        content=json.dumps({HOOKS_KEY: carried}, indent=2, ensure_ascii=False) + "\n",
    )


_HOOK_ENTRY_LABEL = f"frontmatter key `{HOOKS_KEY}`"
"""The label `_hook_part` gives every staged hook entry, and the one `_merged_hooks` looks for.

Spelled once because it names the one shape `_merged_hooks` treats specially -- a second
spelling drifting from `_hook_part`'s own would leave that function matching nothing and two
skills' hook entries silently back to colliding on the one file they share.
"""


def _as_hook_entries(value: Any) -> list[Any]:
    """``value`` as a list of hook entries for one event: itself, or itself alone in one.

    The source documents a list of matcher entries, but this reading carries a header's
    `hooks:` through whatever it was written as (`_portable` only asks that it have a
    stable text, not that it have this shape), so a value that arrived as one mapping or
    one bare string is as real an input as a list already is, and merging two skills' entries
    must answer for both without losing which skill each one came from.
    """
    return value if isinstance(value, list) else [value]


def _merged_hooks(parts: Sequence[_Part]) -> list[_Part]:
    """Every hook entry staged at the one file the target registers hooks in, collapsed to one.

    Two skills of one set that both declare ``hooks:`` are staged at the same destination --
    the target names one file for the whole workspace, not one per skill -- and that is not a
    collision `_assemble` should refuse: FR-40 is about a file this run does not edit because
    it may already hold someone else's entries, not about two parts of its own plan landing on
    the file it is about to create. Left as two parts, the second write would replace the
    first and `_assemble` would refuse the whole run over a path it staged itself. Merged here
    instead, by event, the same way two events inside one skill's own header already merge in
    `_hooks_the_target_fires` -- an event both skills declare keeps both skills' entries.
    """
    merged: dict[Path, _Part] = {}
    order: list[Path] = []
    rest: list[_Part] = []
    for part in parts:
        if part.label != _HOOK_ENTRY_LABEL or part.content is None:
            rest.append(part)
            continue
        carried = json.loads(part.content)[HOOKS_KEY]
        earlier = merged.get(part.staged)
        if earlier is None:
            merged[part.staged] = part
            order.append(part.staged)
            continue
        before = json.loads(earlier.content)[HOOKS_KEY]  # type: ignore[arg-type]
        combined = {**before}
        for event, entries in carried.items():
            # Each side is a list of matcher entries in the shape the source documents, but
            # nothing upstream of here enforces that shape on a header the reading only
            # carries through `_portable` -- and `+` on two of anything else is either a
            # crash (two mappings) or a string built out of two commands nobody wrote (two
            # scalars), neither of which this run may hand to the target as one entry. Each
            # side is wrapped in a list of its own first, so two events combine into a list
            # of the two original values however each was shaped, and never into their sum.
            combined[event] = _as_hook_entries(combined.get(event, [])) + _as_hook_entries(entries)
        merged[part.staged] = replace(
            earlier, content=json.dumps({HOOKS_KEY: combined}, indent=2, ensure_ascii=False) + "\n"
        )
    return rest + [merged[staged] for staged in order]


def _links_on_the_way(root: Path, staged: Path) -> None:
    """Refuse a symbolic link at any level of ``staged`` below ``root``, the last one included.

    Every level, because every one of them is a door out: `mkdir(parents=True,
    exist_ok=True)` walks through a link in the middle of a path without a word, and a copy
    at the end follows one, so a link anywhere below `root` puts the bytes where it points.
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
        level for level in reversed(staged.parents) if level != root and level.is_relative_to(root)
    ]
    for level in [*below, staged]:
        if level.is_symlink():
            raise ConvertError(
                f"{level} is a symbolic link, and no level of a destination is written "
                f"through one: the bytes would go where the link points rather than under "
                f"{root}, which is the one promise this command makes about the caller's "
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


_ADDRESSED = re.compile(r"\]\((?P<link>[^)\s]+)[^)\n]*\)|`(?P<code>[^`\n]+)`")
"""The two ways one file of a set addresses another where it stands: a link, and inline code.

Both, because both are how the sets these rules were written against are actually written --
a subagent says ``Follow `../policy/tone.md` `` as readily as it says ``[tone](...)``, and an
address that only one of the two spellings reaches is an address left pointing at nothing.

# ponytail: an address inside a fenced code block is rewritten when it happens to sit on one
# line with a backtick each side, because nothing here tracks fences. That is the right
# answer more often than not -- the file really did move, and the substitution is reported
# either way -- and the way up is a Markdown parser, which is a dependency no set this has
# met needs.
"""

_DEFINED = re.compile(r"^ {0,3}\[[^\]\n]+\]:[ \t]*(?P<target>\S+)", re.MULTILINE)
"""A Markdown link definition: a label at the start of a line, then the address it stands for.

Recognised and never rewritten. A definition is written in one place and used from another,
while the substitution here only ever edits an address where it stands, so repointing one is
work of a different shape. Recognising it costs one expression and is not the same promise:
a file this run moved away from under a definition is a file left broken, and a broken file
the caller is told about is a different thing from a broken file nobody mentions.
"""


def _addresses_a_file(token: str, *, moved: bool) -> bool:
    """The one rule for what counts as an address of a file beside the one it was written in.

    One rule in one place, because it is one question and both halves of the work read the
    same answer: what may be rewritten is what may be reported. Split in two -- a syntactic
    test before the rewrite and a second, looser test before the report -- it would call a
    token an address for one purpose and not for the other, which is how a run comes to
    repoint something it never says a word about, or to say a word about something it would
    never have repointed.

    A token is an address when it is written as a relative path -- not a URL, not an anchor
    within the same file, not an absolute path, not a home-relative one, not an autolink --
    and then either has a step in it or names a file this run actually moved. The second
    half is what lets a sibling addressed by its bare name be repointed when the two move
    apart; without it, the first half alone would have to treat every backticked word as an
    address, and `pro`, `model_decision` and `uv run pytest` would each earn a report row
    saying they lead out of the set. The price is the other way round: a bare name that
    leads out of the set stays silent, because nothing distinguishes it from a word.
    """
    if token.startswith(("/", "#", "<", "~")) or "://" in token or token.startswith("mailto:"):
        return False
    return moved or "/" in token.partition("#")[0]


def _placed(parts: Sequence[_Part]) -> dict[Path, Path]:
    """Where every path of the plan ends up, by the path it was read from.

    The whole plan and not one entity of it: a subagent addresses a rule file, and which of
    the two is asked about first is an order of the composition rather than a fact about
    either. An entity with no part here was moved nowhere, and an address of it is left alone.
    """
    return {
        Path(os.path.normpath(part.copied_from)): part.staged
        for part in parts
        if part.copied_from is not None
    }


def _repointed(candidate: Path, placed: Mapping[Path, Path]) -> Path | None:
    """Where ``candidate`` lands, whether it moves itself or inside a directory that moves.

    A bundled directory crosses as one part, so a file inside it has no entry of its own and
    is found by the nearest ancestor that has one; the steps below that ancestor are the same
    on both sides, because the directory is copied whole.
    """
    for level in [candidate, *candidate.parents]:
        moved = placed.get(level)
        if moved is not None:
            return moved / candidate.relative_to(level)
    return None


def _named_paths(inputs: Inputs) -> list[Path]:
    """Every path the composition names, in the order :data:`assets.PARTS` lists the parts.

    A part may be absent -- ``plugin`` as ``None``, a folder tuple as an empty one -- and an
    absent part names no path. Every part that is there is a path or a tuple of them, which
    is the whole of what a composition can hold.
    """
    named: list[Path] = []
    for part in PARTS:
        value = getattr(inputs, part)
        if value is None:
            continue
        named += [value] if isinstance(value, Path) else list(value)
    return named


OUT_OF_THE_SET = (
    "leads out of the set: the composition names no part holding what it points at, so this "
    "run moved no such file and has no new place to point it at. It crosses exactly as it "
    "was written -- follow it by hand once you know where the file it means ended up"
)
"""Why an address this run did not rewrite is named rather than left in silence.

An address inside the set that stayed where it was is a different case and says nothing: the
file is still at the path it was at, and the rule is to rewrite what moved and nothing else.
An address of something the set never held cannot be checked by anyone but the caller.
"""

STILL_POINTS_AT_THE_OLD_PLACE = (
    "in a Markdown link definition, and this run moved what it points at without repointing "
    "it: a definition stands in one place and is used from another, and the substitution "
    "here only ever edits an address where it stands. The file is broken as it crosses, "
    "which is why it is named here rather than left to be found -- point it at "
)
"""Why an address this run broke is named. The place to point it at is appended to this.

The one row of this whole module about damage rather than about a price: every other line
says a file crossed unchanged, and this one says a file crossed changed underneath. Silence
here would be the exact failure the command exists against, with the command as its author.
"""


def _settled(
    token: str,
    source_dir: Path,
    staged_dir: Path,
    placed: Mapping[Path, Path],
    named: Sequence[Path],
) -> tuple[str | None, str | None]:
    """What becomes of one address: the new one, a reason to report, or neither of the two.

    Three answers, and one question asked of each address by resolving it against the folder
    the file was read from. It names something the plan moves: the new address is the way
    from where this file lands to where that one lands, and one that comes out the same --
    two parts that move together -- is neither a rewrite nor a row. It names something inside
    the set that the plan does not move: neither, because the file is still where the address
    says it is. It names nothing the composition holds: a row, because nobody here can work
    out what it should have become.

    Both spellings of an address are settled here and not each in its own way, so that what
    is decided about ``../policy/tone.md`` does not depend on whether it was written inline
    or as a definition. What differs between them is only what the caller does with the first
    answer: an inline address is rewritten with it, a definition is named with it.
    """
    # An anchor names a place inside the file and travels with it untouched; what moves is
    # the path in front of it.
    target, _, anchor = token.partition("#")
    candidate = Path(os.path.normpath(source_dir / target))
    landed = _repointed(candidate, placed)
    if not _addresses_a_file(token, moved=landed is not None):
        return None, None
    if landed is None:
        inside = any(candidate == root or candidate.is_relative_to(root) for root in named)
        return None, None if inside else f"addresses `{token}`, which {OUT_OF_THE_SET}"
    became = Path(os.path.relpath(landed, staged_dir)).as_posix() + (f"#{anchor}" if anchor else "")
    return (None if became == token else became), None


def _relink(
    text: str,
    source_dir: Path,
    staged_dir: Path,
    placed: Mapping[Path, Path],
    named: Sequence[Path],
) -> tuple[str, list[tuple[str, str]], list[str]]:
    """``text`` with every address of a moved file pointed at where this run put it.

    Two passes over the same text and one decision behind both (`_settled`). An address
    written where it stands is rewritten; a link definition is named instead, with the place
    it should point at, because this run moves the file out from under it either way and only
    one of the two can be fixed here.
    """
    rewrites: list[tuple[str, str]] = []
    said: list[str] = []

    def pointed(match: re.Match[str]) -> str:
        group = "link" if match.group("link") is not None else "code"
        token = match.group(group)
        became, reason = _settled(token, source_dir, staged_dir, placed, named)
        if reason is not None:
            said.append(reason)
        if became is None:
            return match.group()
        rewrites.append((token, became))
        whole, start = match.group(), match.start()
        return whole[: match.start(group) - start] + became + whole[match.end(group) - start :]

    changed = _ADDRESSED.sub(pointed, text)
    for found in _DEFINED.finditer(text):
        token = found.group("target")
        became, reason = _settled(token, source_dir, staged_dir, placed, named)
        if became is not None:
            said.append(f"addresses `{token}` {STILL_POINTS_AT_THE_OLD_PLACE}`{became}`")
        elif reason is not None:
            said.append(reason)
    return changed, rewrites, said


def _relinked(
    parts: Sequence[_Part], inputs: Inputs
) -> tuple[list[_Part], list[dict[str, str]], list[str]]:
    """The plan with every address in it pointed at where this run put the file it names.

    Only the files the translation rules name (:meth:`rules.Rules.rewritable`) are opened at
    all: a change history is a record of what was written, and a run that edited one would
    make it a record of what we wish had been written. Which files those are is data in the
    rules file, so no name of any particular set is spelled here.

    The text edited is what the plan was already going to write -- a header this run
    translated, or the file as it was found -- never the caller's own file, which is not this
    command's to touch under any circumstance.
    """
    placed = _placed(parts)
    named = _named_paths(inputs)
    settled: list[_Part] = []
    pointed: list[dict[str, str]] = []
    said: list[str] = []
    for part in parts:
        source = part.copied_from
        # A bundled directory crosses whole (`_assemble` copies it with `shutil.copytree`),
        # so it holds no text of its own to rewrite -- but a Markdown file inside it does,
        # and nothing else here ever opens one. Overlaid beside the directory's own copy
        # rather than skipped with it, so a link inside a bundled directory is repointed
        # exactly as one beside the skill file already is.
        if source is not None and source.is_dir() and not source.is_symlink():
            overlays, over_pointed, over_said = _bundled_overlays(
                part, source, placed, named, inputs.translation
            )
            settled.append(part)
            settled += overlays
            pointed += over_pointed
            said += over_said
            continue
        # A link crosses as a link: not a file this run holds the text of, and reading
        # through it is the one thing `_assemble` is careful not to do.
        if source is None or source.is_symlink() or not inputs.translation.rewritable(part.label):
            settled.append(part)
            continue
        text = part.content if part.content is not None else _text_of(source)
        changed, rewrites, reasons = _relink(text, source.parent, part.staged.parent, placed, named)
        settled.append(part if not rewrites else replace(part, content=changed))
        pointed += [
            {"path": str(part.staged), "from": was, "to": became} for was, became in rewrites
        ]
        # The part names itself and the reason says the rest: which file a row is about is the
        # one thing `_relink` cannot know, and the one thing a reader needs first.
        said += [f"`{part.label}` {reason}" for reason in reasons]
    return settled, pointed, said


def _bundled_overlays(
    part: _Part,
    source: Path,
    placed: Mapping[Path, Path],
    named: Sequence[Path],
    translation: Rules,
) -> tuple[list[_Part], list[dict[str, str]], list[str]]:
    """Every rewritable file inside a bundled directory, relinked and staged beside its copy.

    A bundled directory is one part of the plan and `_assemble` copies it whole, so nothing
    else in this module ever opens a file living inside it. `_repointed` already resolves an
    address that points into or out of such a directory, by the nearest ancestor it finds in
    ``placed``; the piece missing is opening the file itself, which this does exactly as the
    loop above opens one found beside the skill file. Left unopened, a broken link inside a
    bundled directory would cross the same way a broken link anywhere else in the set is the
    one thing this module exists against -- only unreported, because nothing here had read it.

    Staged at ``part.staged / <relative path>`` -- inside the directory `_assemble` is about
    to copy whole -- so the write that follows overwrites the one copytree already made,
    rather than landing beside it as a second, unrelated file.
    """
    overlays: list[_Part] = []
    pointed: list[dict[str, str]] = []
    said: list[str] = []
    for found in sorted(source.rglob("*")):
        if not found.is_file() or found.is_symlink():
            continue
        relative = found.relative_to(source).as_posix()
        if translation.ignored(relative) or not translation.rewritable(relative):
            continue
        staged = part.staged / relative
        changed, rewrites, reasons = _relink(
            _text_of(found), found.parent, staged.parent, placed, named
        )
        label = f"{part.label}{relative}"
        said += [f"`{label}` {reason}" for reason in reasons]
        if not rewrites:
            continue
        destination = f"{part.destination}{relative}"
        overlays.append(_Part(label, destination, staged, part.root, content=changed))
        pointed += [{"path": str(staged), "from": was, "to": became} for was, became in rewrites]
    return overlays, pointed, said


def _overlays(part: _Part, earlier: _Part) -> bool:
    """Whether ``part`` is `_bundled_overlays`'s own relinked copy of a file ``earlier`` stages.

    Read off the two parts alone, never off which function produced them: a part with
    written content of its own and no source of its own (`_bundled_overlays` writes such a
    part; nothing else in this module does) that lands inside a directory `earlier` is about
    to copy whole is the one shape this module ever stages on purpose two deep -- an
    unrelated pair sharing a path by accident never has both halves of it.
    """
    return (
        part.content is not None
        and part.copied_from is None
        and earlier.copied_from is not None
        and earlier.copied_from.is_dir()
        and part.staged.is_relative_to(earlier.staged)
    )


def _lands_at(part: _Part, *, installing: bool) -> Path:
    """Where a part would be created, measured the way the root it is held to is measured.

    Under ``out`` the parent is resolved and the last name left as written: what that asks is
    where the file would be created, and every way a destination can lead out of the folder
    the caller named -- an absolute layout path, a ``..`` along the way or as the last step,
    a symbolic link partway down -- is one question answered once. A link at the destination
    itself is not a way out but an occupied place, and resolving it here would have the run
    report a broken promise where the promise was never reached.

    A run that installs is measured as written, ``normpath`` and nothing else. The tree it
    writes into is the caller's own, and a link they made in it says where their
    configuration lives rather than leading a write out of a folder this command created:
    resolved through it, a destination inside their home folder comes back outside it and the
    check below calls a path theirs by their own arrangement a path leading away. What still
    has teeth is what the layout itself spells -- `_live` has already collapsed the path, so
    an absolute one or a ``..`` above the root lands outside it here exactly as under ``out``.
    """
    if installing:
        return Path(os.path.normpath(part.staged))
    return Path(os.path.normpath(_resolved(part.staged.parent) / part.staged.name))


def _kept_out(ignored: Callable[[str], bool]) -> Callable[[Any, list[str]], set[str]]:
    """The names a directory copy leaves behind, in the shape :func:`shutil.copytree` asks for.

    The same question the reading of the set already asked of every path under the folder,
    asked again at the one place the bytes are actually moved. Both have to ask it: the
    reading is what puts the row in the report, and a directory is copied whole, so a row
    saying a build cache stayed behind would otherwise sit above five files of it on disk.
    Matched on the name alone, which is how the rules match every part of a path anyway --
    and a directory kept out is never descended into, so nothing below it is asked at all.
    """
    return lambda _, names: {name for name in names if ignored(name)}


def _assemble(
    parts: Sequence[_Part], *, installing: bool, ignored: Callable[[str], bool]
) -> tuple[list[dict[str, str]], list[str]]:
    """Copy or write every planned part, once the whole plan is known to be safe to write.

    Two questions are asked of every destination before the first byte of the first one is
    written: is the place free, and is it under the root the part belongs to -- the folder
    the caller named, or the root of the target environment its destination was measured
    from. Both run over the whole plan, because
    a run that wrote two files and then refused the third would have done the damage it
    refused to do.

    ``installing`` says which of the two roots that is, and with it how far a destination is
    followed before it is measured: through the symbolic links of a tree this command made,
    and never through those of a tree that was the caller's before it ran. `_lands_at` holds
    the whole of that reasoning, and `_links_on_the_way` below is the same question asked
    again of a staged run, level by level, as late as it can be asked.

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
    # Over the whole plan, and answered again level by level in `_links_on_the_way` before
    # each part of a staged run is written: this one rules out a destination that leads out
    # of `out` at all, that one rules out the path having changed since.
    # The root is measured exactly as the destination is -- `_lands_at` says which way and
    # why -- because a root read one way and a destination the other are two spellings of one
    # folder, and a path under the root matches it in neither.
    roots = {
        part.root: Path(os.path.normpath(part.root)) if installing else _resolved(part.root)
        for part in parts
    }
    places = [(part, _lands_at(part, installing=installing)) for part in parts]
    outside = [
        f"{part.staged} is not under {part.root}"
        for part, place in places
        if not place.is_relative_to(roots[part.root])
    ]
    if outside:
        raise ConvertError(
            ", ".join(outside) + "; nothing was written, because the one "
            "promise this command makes about the caller's filesystem is that it writes "
            "under the roots it was told to write under and nowhere else",
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
    onto = [str(part.staged) for part, place in places if place == roots[part.root]]
    if onto:
        raise ConvertError(
            ", ".join(onto) + " is the root this run was told to write into, not a place "
            "inside it; nothing was written, because a part of a skill put there would "
            "replace that root with one piece of what was supposed to go inside it",
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
    planned: dict[Path, _Part] = {}
    for part in parts:
        for place, earlier in planned.items():
            if _overlays(part, earlier):
                # `_bundled_overlays` stages a relinked file exactly where the directory
                # part it belongs to is about to be copied whole -- on purpose, so the
                # write below replaces the copytree's own unrewritten copy of it. The one
                # shape this loop is not the collision it exists to catch.
                continue
            if place.is_relative_to(part.staged) or part.staged.is_relative_to(place):
                raise ConvertError(
                    f"`{earlier.label}` is to be written at {place} and `{part.label}` at "
                    f"{part.staged}, which is the same place or one inside the other; "
                    "nothing was written, because whichever of the two went second would "
                    "replace the other while the report called both of them carried over",
                    COLLISION,
                )
        planned[part.staged] = part
    # A link is named as one, at the level it stands: it is the one occupied place that does
    # not look occupied to whoever reads the folder, and a refusal that called it a file
    # would send them looking for something that is not there.
    taken = [
        f"{part.staged}, which is a symbolic link" if part.staged.is_symlink() else str(part.staged)
        for part in parts
        if part.staged.exists() or part.staged.is_symlink()
    ]
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
            # Not asked of a run that installs: every level of that destination is the
            # caller's own, and a link they put there is where they keep their configuration
            # -- the same reason `_lands_at` measures such a destination as written.
            if not installing:
                _links_on_the_way(part.root, part.staged)
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
                shutil.copytree(
                    part.copied_from, part.staged, symlinks=True, ignore=_kept_out(ignored)
                )
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
            f"nothing was assembled, and what this run had already written is taken back: {error}",
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
    links: Sequence[dict[str, str]],
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
        # Beside the translated values and for the same reason: a substitution the run made
        # inside somebody's file is work done to it, and work a report does not show is work
        # the caller cannot check. Empty without `out`, which is where addresses are settled.
        "links": list(links),
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
        f"  pointed `{entry['from']}` at `{entry['to']}` in {entry['path']}"
        for entry in report["links"]
    ]
    lines += [
        f"  wrote {entry['path']} (it belongs at {entry['to']})" for entry in report["written"]
    ]
    lines += [f"  advice: {line}" for line in report["advice"]]
    return "\n".join(_plain(line) for line in lines) + "\n"


INSTALL_WITH = (
    "nothing was put where the target environment reads it: this run only assembled the "
    "set. Repeat the command with `--install` in place of `--out` to write every part to "
    "the destination named beside it above, in the roots the target description gives"
)
"""The ready way to install, printed by every run that assembled instead of installing.

A copy of the assembled tree is not it: the destinations of one run can be measured from
two different roots -- the workspace and the home folder -- so there is no one folder to
copy it into, and a command that told a person to copy it anyway would be telling them to
put half of it in the wrong place.
"""


def _announced(parts: Sequence[_Part]) -> str:
    """The whole plan in words: every place about to be written, and which are already taken.

    Taken places are named here as well as refused below, and the two are not the same
    thing said twice: the refusal is about the run, this is about the caller's folders, and
    a person reading a list of paths wants to know which of them hold something of theirs
    before a single one is touched.
    """
    lines = ["about to write into the roots the target description names:"]
    lines += [
        f"  {part.staged} <- `{part.label}`"
        + (
            " -- ALREADY THERE, and nothing here is replaced: this run stops instead"
            if part.staged.exists() or part.staged.is_symlink()
            else ""
        )
        for part in parts
    ]
    return "\n".join(_plain(line) for line in lines) + "\n"


def refusal(source: str | None, target: str | None, exit_code: int, message: str) -> Conversion:
    """A run that never started, in the shape every run of this command ends in.

    Something a run needs before it can read anything -- the translation rules above all --
    can be missing or unreadable, and the caller of this module has no other way to say so
    in the report and the words a run always answers with. The version of the rules is empty
    because there are none: a number invented here would name rules nobody read.
    """
    report = _report(source, target, "", Verdict.UNDECIDABLE, exit_code, (), (), (), (), message)
    return Conversion(Verdict.UNDECIDABLE, exit_code, report, _summary(report))


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
    absent = []
    for path in _named_paths(inputs):
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


def _nowhere(target: EnvSpec, kind: Kind, scope: Scope, plugin: str | None) -> list[str]:
    """The line an entity whose kind the target names no root for earns, in the report's words.

    The same price `_placeless` names for one part of a skill, for a whole entity of
    another kind: the target documents no place, and a place picked here would be a guess
    about a layout only that environment's documentation can settle. A line and not a
    refusal, because the rest of the set is unaffected and stopping the run over it would
    lose every entity that did have somewhere to go.
    """
    if kind is Kind.MANIFEST:
        # The one kind whose place is not a root of entities: a manifest is the marker that
        # makes a folder a plugin, so it is asked for the plugins root and for its own name
        # inside it -- the same two answers a skill needs, about a different pair of entries.
        wanted = [_layout(target, PLUGINS_ROOT[scope]), _layout(target, PLUGIN_FILE)]
    elif kind not in (PLUGIN_INSIDE if plugin is not None else ROOT_ENTRY):
        return []
    elif kind is Kind.SKILL:
        # A skill is a folder and needs two answers: the root its folder sits in, and what
        # the file inside it is called. Every other kind crosses as one file and needs one.
        wanted = [_root_of(target, kind, scope, plugin), _layout(target, SKILL_FILE)]
    else:
        wanted = [_root_of(target, kind, scope, plugin)]
    if all(item is not None for item in wanted):
        return []
    return [
        f"the {kind.value} stayed where it is: {target.vendor}/{target.environment} names no "
        f"place for one at the {scope.value} level, and a place picked for it here would be "
        "a guess about a layout only that environment's documentation can settle"
    ]


def _assess(
    asset: Asset,
    gaps: Mapping[str, Gap],
    target: EnvSpec,
    translation: Rules,
    scope: Scope,
    plugin: str | None,
    named_directly: frozenset[Path],
) -> tuple[Assessed, list[str]]:
    """One entity of the set: its rows, its own verdict, and the lines it owes the reader.

    Where an entity goes is read off the layout of the target alone, before and whether or
    not any bytes are asked for, because what the transfer costs is settled by the two
    descriptions and never by `--out`. A skill is a folder and is asked part by part
    (`_placeless`); a kind that crosses as one file is asked once (`_nowhere`); a kind
    the target has no root for at all -- a command -- is never assembled and says so in its
    row instead.

    An asset with no name is the named part itself rather than an entity of it -- an empty
    folder, a path the rules keep out, a file nobody declared. It is judged like any other,
    and carries no name of its own to be assembled under; what it holds is placed by the
    rule the translation states for an undeclared file.
    """
    properties, advice = _judge(
        asset.findings, gaps, target, translation, asset.kind, scope, plugin
    )
    valued, said, applied = _translated(asset, target, translation)
    properties += valued
    advice += said
    if asset.kind is Kind.RULES and asset.name:
        # The one header this command writes rather than translates, and the one kind whose
        # own header the reading never opened: a rule file is carried whole, so what it
        # declares is asked here, where the file is about to be put somewhere that reads it.
        headed, added = _trigger(asset, target, translation)
        properties += headed
        applied += added
    if asset.kind is Kind.MANIFEST and asset.name:
        # The other file the reading carried whole: a manifest is data rather than a header,
        # and what it holds is asked here, where the two descriptions are at hand.
        fields, said = _manifest(asset, gaps, target, translation, scope, plugin)
        properties += fields
        advice += said
    stayed: list[str] = []
    unplaced = False
    name, assembled = asset.name, None
    if not asset.name:
        pass
    elif asset.kind is Kind.SKILL:
        try:
            name = _skill_name(asset.path, asset.frontmatter)
            # The whole skill having nowhere to go, and one part of it left behind, are
            # asked in that order and never both: a target that names no root has nothing
            # to say about where the parts inside it would have gone either.
            stayed = _nowhere(target, asset.kind, scope, plugin)
            if not stayed:
                assembled = _assembled_name(name, target.environment)
        except ConvertError as error:
            if Path(os.path.abspath(asset.path)) in named_directly:
                # ADR-0012: a refusal is about the path the caller named, and this is it --
                # a `--skill` folder the command line pointed at directly, not one this run
                # found on its own. Re-raised whole, and caught by `convert`'s own refusal.
                raise
            # Found inside a folder the caller named rather than named itself, so an invalid
            # name -- the frontmatter's own, or that same name once suffixed with the
            # target's environment -- is a fault of this one skill and not of the folder it
            # was found in: refusing the whole `--skills` read over it would lose every
            # skill beside it that named itself correctly. A row instead, the same price a
            # target with no root for skills at all already pays below.
            stayed = [str(error)]
        else:
            if not stayed:
                stayed = _unregistered_hook(target, scope, properties, _hooks_of(asset))
                unplaced = bool(_placeless(target, properties))
    elif asset.kind is Kind.MANIFEST:
        stayed = _nowhere(target, asset.kind, scope, plugin)
        # The folder the manifest sits in, which is what the target reads a plugin by: its
        # own `config.json` keys a plugin on the directory name, and the `name` field of the
        # manifest is a display name that defaults to it. Unsuffixed, unlike a skill: a
        # plugin is a namespace of its own and two of them never share a folder.
        assembled = None if stayed else plugin
    elif asset.kind in ROOT_ENTRY:
        stayed = _nowhere(target, asset.kind, scope, plugin)
        # The name on disk, and not one suffixed with the target environment: a skill is a
        # folder of its own and two targets would collide on it, while one file among many
        # in a shared folder is found by the name its own header and its callers use.
        assembled = None if stayed else asset.path.name
    verdict = worst(entry.verdict for entry in properties)
    # A part with nowhere to go did not cross, whatever its row says about being reproduced:
    # exit code 0 on a run that left one behind would be this command telling a caller there
    # is nothing here to look at. Carried beside the result by the rule for an undeclared
    # path, it still did not land where the target reads it from, so the price is the same.
    if stayed or unplaced:
        verdict = worst([verdict, Verdict.LOSSY])
    return (
        Assessed(asset, name, assembled, verdict, tuple(properties), tuple(applied)),
        [*advice, *stayed],
    )


def convert(
    inputs: Inputs,
    source: str | None,
    target: str | None,
    *,
    root: str | Path = "specs",
    out: str | Path | None = None,
    install: bool = False,
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
    whole answer. With it, every entity of the set the target names a root for is assembled
    under ``out`` at the paths the target description names, at the level ``scope`` chooses.

    ``install`` writes those same destinations into the roots of the target environment on
    this machine instead, and then the whole plan goes to the error stream before the first
    byte of it is written: what a person is asked to trust with their own folders is what
    they were shown first. It rules out ``out``, because a run has one destination and not
    two, and it changes nothing about what the transfer costs -- the verdict is computed
    before either of them is looked at.
    """
    if install and out is not None:
        # Before anything is read: the arguments contradict each other, and every answer
        # this run could give about the set would be an answer to a question nobody asked.
        report = _report(
            source,
            target,
            inputs.translation.version,
            Verdict.UNDECIDABLE,
            UNWRITABLE,
            (),
            (),
            (),
            (),
            "`--install` and `--out` name two destinations and a run has one: drop `--out` "
            "to write into the roots of the target environment, or drop `--install` to "
            "assemble under the folder you named",
        )
        return Conversion(Verdict.UNDECIDABLE, UNWRITABLE, report, _summary(report))
    assessed: list[Assessed] = []
    advice: list[str] = []
    written: list[dict[str, str]] = []
    links: list[dict[str, str]] = []
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
        # A composition that names a manifest crosses as a plugin, and every root moves
        # inside its folder. Asked once, of the whole set, because it is a fact about the
        # set and not about any one entity of it -- the skills of a plugin go inside it
        # whether or not the manifest is the entity being judged at the time.
        # Made absolute before the folder is named: `Path("plugin.json").parent` is `.`,
        # whose name is the empty string, and a plugin folder called that is every part of
        # the set written one level above where it belongs. The command line expands its
        # arguments, the seam takes whatever a caller passes, and this is the seam.
        plugin = next(
            (
                Path(os.path.abspath(asset.path)).parent.name
                for asset in found
                if asset.kind is Kind.MANIFEST
            ),
            None,
        )
        named_directly = frozenset(Path(os.path.abspath(path)) for path in inputs.skill)
        for asset in found:
            entity, said = _assess(
                asset, gaps, target_spec, inputs.translation, scope, plugin, named_directly
            )
            assessed.append(entity)
            advice += said
        verdict = worst(entity.verdict for entity in assessed)
        # An undecidable run assembles nothing: the transferable half of a set whose other
        # half nobody documented is a folder that looks converted and is not.
        if (out is not None or install) and verdict is not Verdict.UNDECIDABLE:
            # One spelling of `out` from here down. Every check below counts the levels of a
            # destination by text -- `_under` against a collapsed path, `_links_on_the_way`
            # against the root itself -- so a `..` the caller typed and a `..` collapsed away
            # are two paths that name one folder, and levels compared across the two match
            # nowhere: a link partway down goes unasked and is written through, on a run the
            # report then calls clean.
            where = _Where(None if out is None else Path(os.path.normpath(out)))
            parts: list[_Part] = []
            for entity in assessed:
                planned, asked = _plan(
                    entity, where, target_spec, scope, inputs.translation, plugin
                )
                parts += planned
                advice += asked
            # Two skills that both declare `hooks:` are staged at the one file the target
            # names for the whole workspace, and merging them is not the collision the plan
            # is checked whole for below -- it is the one shape `_merged_hooks` is allowed to
            # resolve rather than refuse.
            parts = _merged_hooks(parts)
            # One plan for the whole set, checked whole before the first byte: two skills of
            # one set aimed at one destination -- apart from that one merged shape -- is the
            # same collision as two parts of one skill, and a check made per entity would not
            # see it.
            # After the whole plan and before the first byte of it: an address is rewritten
            # against where the file it names lands, and that is not known until every entity
            # has contributed its parts.
            parts, links, addressed = _relinked(parts, inputs)
            advice += addressed
            if where.out is None:
                # Before the first byte and not behind a flag of its own: what a run is
                # about to do to somebody's own folders is the one thing they have to be
                # able to read before it happens, and an option to ask for it is an option
                # to forget. To the error stream, where everything for a person goes.
                sys.stderr.write(_announced(parts))
            written, linked = _assemble(
                parts, installing=where.out is None, ignored=inputs.translation.ignored
            )
            advice += linked
            if where.out is not None and written:
                advice.append(INSTALL_WITH)
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
            links,
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
        links,
        None,
    )
    return Conversion(verdict, EXIT_CODE[verdict], report, _summary(report))
