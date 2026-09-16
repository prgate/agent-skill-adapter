"""Reading one asset set off the disk: what it holds, and the entry ids it asks about.

The set is given by its composition -- folders of skills, of subagents, of commands, the
rule files, the plugin manifest -- and never by one root laid out the way one repository
happens to lay it out. Which part a path belongs to is decided by the option that named it,
so no folder name is ever read as a meaning: a set that spells its subagents ``roles/`` and
its skills ``bundles/`` is read exactly as one that spells them anything else.

Nothing here compares anything or decides what travels. Each entity is read into *findings*
-- a frontmatter key, a bundled directory, a hook event, a path the rules keep out -- and
each finding names the entry ids of the environment descriptions that it turns on. Ids are
built from the names as written, and no list of known names is kept anywhere in this module:
a name nobody documented has to reach the report as a row rather than fall out of it.
"""

from __future__ import annotations

import codecs
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any

import yaml

from agent_skill_adapter.rules import Rules

SKILL_MD = "SKILL.md"
HOOKS_KEY = "hooks"
"""The file and the frontmatter key of the source environment this module opens by name."""

MARKDOWN = ".md"
"""What marks a file in a named folder as one of its entities rather than a file beside them.

The suffix is the format of the file, which is a thing the file itself says; the name of the
folder it sits in is not, and reading a meaning out of that name is what this module exists
to avoid. A folder of subagents may hold a diagram or a data file next to them, and those
are files nobody declared -- a row in the report -- rather than subagents that fail to parse.
"""

SKILL_FRONTMATTER = "skill.frontmatter."
SKILL_DIR = "skill.dir."
SKILL_TOP = "skill.top."
SUBAGENT_FRONTMATTER = "subagent.frontmatter."
SUBAGENT_BODY = "subagent.system-prompt-body"
COMMAND_FILE = "command.file"
RULES_FILE = "rules.file"
PLUGIN_MANIFEST = "settings.file.plugin-manifest"
EVENT = "hook.event."
BLOCK = "hook.decision.block"
"""The entry ids the entities of a set ask the descriptions about.

Firing an event and stopping what it precedes are two entries, so a hook asks about both
(ADR-0007). `skill.file.*` is not among these: those are the skill file's own fields, and a
file called `README.md` is not one of them.
"""


class Kind(str, Enum):
    """What kind of thing an entity of the set is.

    The value comes from the option that named the path, never from the path itself.
    """

    SKILL = "skill"
    SUBAGENT = "subagent"
    COMMAND = "command"
    RULES = "rules-file"
    MANIFEST = "manifest"


PARTS = {
    "skills": "folders of skills",
    "skill": "a skill folder",
    "agents": "folders of subagents",
    "commands": "folders of commands",
    "rules": "rule files",
    "plugin": "a plugin manifest",
}
"""Every part a composition may name, and the words the refusal for an empty one uses."""

DROPPED = (
    "kept out by the ignore list of the translation rules, so nothing of it is carried "
    "across -- named here because a path that is dropped in silence is a path nobody can "
    "audit"
)
UNDECLARED = (
    "no environment description declares anything here, so nothing states what it is; what "
    "happens to it is the rule the translation states for an undeclared file"
)
LINKED = (
    "a folder reached through a symbolic link, which this walk does not follow: a link "
    "pointing at a folder above itself is a loop, and the walk is over a folder somebody "
    "else wrote. Name what it points at in the composition to have what is inside it read"
)
EMPTY = (
    "the folder was named in the composition and is empty of anything this run reads: a "
    "part of the set that is empty is not an error, and saying so is not the same as "
    "saying nothing"
)
"""The four things a reading has to say about a path that produced no entity."""


class ReadError(ValueError):
    """The set could not be read, and the message says what is wrong and where.

    A refusal and not a traceback: every one of these is about the folder the run was
    pointed at, which is something a person can go and look at.
    """


@dataclass(frozen=True)
class Finding:
    """One thing found in the set, and the entry ids it asks the descriptions about.

    ``ids`` is empty where there is nothing to ask -- a path the rules keep out, a file no
    description declares, a header value that had to be rewritten to cross. Those carry a
    ``note`` instead: they are rows of the report all the same, because the whole point of
    reading them is that they do not disappear.
    """

    found_as: str
    ids: tuple[str, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class Asset:
    """One entity of the set: what it is, where it is, and what it depends on.

    An asset whose ``name`` is empty is not an entity but the named part itself -- a folder
    that produced none, or one that had something to say about what it holds. It is never
    carried anywhere: there is no name to assemble it under, because there is nothing there.
    """

    kind: Kind
    path: Path
    name: str
    frontmatter: dict[str, Any]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class Inputs:
    """The composition of one set, part by part. Every part is optional but not all of them.

    ``skills``, ``agents`` and ``commands`` name folders holding those entities; ``skill``
    names skill folders one at a time, which is what the positional argument of the command
    has always meant; ``rules`` names rule files; ``plugin`` names the manifest.
    """

    translation: Rules
    """The translation rules, read for what they keep out of the transfer."""
    skills: tuple[Path, ...] = ()
    skill: tuple[Path, ...] = ()
    agents: tuple[Path, ...] = ()
    commands: tuple[Path, ...] = ()
    rules: tuple[Path, ...] = ()
    plugin: Path | None = None

    def named(self) -> tuple[str, ...]:
        """The parts this composition names, in the order :data:`PARTS` lists them."""
        return tuple(part for part in PARTS if getattr(self, part))


def read(inputs: Inputs) -> tuple[Asset, ...]:
    """Every entity the composition names, in the order the parts are read.

    Raises :class:`ReadError` when the composition names nothing, or when a path it names
    is not there.
    """
    if not inputs.named():
        raise ReadError(
            "the composition names no part of a set, so there is nothing to read: name at "
            "least one of " + ", ".join(PARTS.values())
        )
    found: list[Asset] = []
    for folder in inputs.skills:
        found += _skills_in(folder, inputs.translation)
    found += [_skill(folder, inputs.translation) for folder in inputs.skill]
    for folder in inputs.agents:
        found += _files_in(folder, Kind.SUBAGENT, inputs.translation)
    for folder in inputs.commands:
        found += _files_in(folder, Kind.COMMAND, inputs.translation)
    found += [_plain(file, Kind.RULES, RULES_FILE, "rule file") for file in inputs.rules]
    if inputs.plugin is not None:
        found.append(_plain(inputs.plugin, Kind.MANIFEST, PLUGIN_MANIFEST, "plugin manifest"))
    return tuple(found)


def _listed(folder: Path) -> list[Path]:
    """What ``folder`` holds, sorted, or a refusal naming the folder."""
    if not folder.is_dir():
        raise ReadError(f"{folder}: no such folder")
    try:
        return sorted(folder.iterdir())
    except OSError as error:
        raise ReadError(f"{folder}: could not be read ({error})") from error


def _named(entry: Path, root: Path) -> str:
    """How a path under ``root`` is written in a finding: relative, and a folder marked as one."""
    rel = entry.relative_to(root).as_posix()
    return f"{rel}/" if entry.is_dir() else rel


def _part(kind: Kind, folder: Path, notes: list[Finding], found: list[Asset]) -> list[Asset]:
    """``found``, with the record of the part itself appended when the part has anything to say."""
    if not found:
        notes.append(Finding(_named(folder, folder.parent), (), EMPTY))
    if notes:
        found.append(Asset(kind, folder, "", {}, tuple(sorted(notes, key=lambda n: n.found_as))))
    return found


def _skills_in(folder: Path, rules: Rules) -> list[Asset]:
    """Every skill folder directly inside ``folder``, plus what ``folder`` itself has to say."""
    found: list[Asset] = []
    notes: list[Finding] = []
    for entry in _listed(folder):
        if rules.ignored(entry.name):
            notes.append(Finding(_named(entry, folder), (), DROPPED))
        elif entry.is_dir() and (entry / SKILL_MD).is_file():
            found.append(_skill(entry, rules))
        else:
            # A folder with no skill file in it is a folder somebody keeps beside their
            # skills, and refusing the run over it would lose the skills that are there. A
            # refusal belongs to a path the person named (FR-3a); what is found inside a
            # named folder and looks like no entity is a row saying nobody declared it.
            notes.append(Finding(_named(entry, folder), (), UNDECLARED))
    return _part(Kind.SKILL, folder, notes, found)


def _files_in(folder: Path, kind: Kind, rules: Rules) -> list[Asset]:
    """Every entity of ``kind`` under ``folder``, plus what ``folder`` itself has to say.

    Walked to the bottom rather than one level deep: a set is free to group its subagents in
    folders, and one that does must not lose them for it.
    """
    found: list[Asset] = []
    notes: list[Finding] = []
    pending = [folder]
    while pending:
        for entry in _listed(pending.pop()):
            if rules.ignored(entry.relative_to(folder).as_posix()):
                notes.append(Finding(_named(entry, folder), (), DROPPED))
            elif entry.is_dir() and not entry.is_symlink():
                pending.append(entry)
            elif entry.is_dir():
                # Not descended into, and said out loud for it: a path left out in silence
                # is the one thing this reading exists to prevent, and a guard against a
                # loop is a reason to skip a folder, never a reason to lose it.
                notes.append(Finding(_named(entry, folder), (), LINKED))
            elif entry.suffix == MARKDOWN:
                found.append(READERS[kind](entry))
            else:
                notes.append(Finding(_named(entry, folder), (), UNDECLARED))
    return _part(kind, folder, notes, found)


def _header(file: Path, prefix: str) -> tuple[dict[str, Any], list[Finding]]:
    """The header of ``file``, and one finding per key of it under ``prefix``."""
    front, rewritten = frontmatter(file)
    findings = [Finding(f"frontmatter key `{key}`", (f"{prefix}{key}",)) for key in front]
    findings += [Finding(f"frontmatter of `{file.name}`", (), line) for line in rewritten]
    return front, findings


def _skill(folder: Path, rules: Rules) -> Asset:
    """One skill folder: its header, what it bundles, the hooks it declares, what is dropped."""
    file = folder / SKILL_MD
    if not file.is_file():
        raise ReadError(f"{folder}: no {SKILL_MD} here, so this is not a skill folder")
    front, rewritten = frontmatter(file, required=REQUIRED_FIELDS)
    findings = [
        Finding(f"frontmatter key `{key}`", (f"{SKILL_FRONTMATTER}{key}",)) for key in front
    ]
    held = [entry for entry in _listed(folder) if not rules.ignored(entry.name)]
    findings += [
        Finding(f"bundled directory `{entry.name}/`", (f"{SKILL_DIR}{entry.name}",))
        for entry in held
        if entry.is_dir()
    ]
    # Everything else at the top of the folder, the skill file aside: a README, a licence, a
    # diagram. Nothing says where they go in the target environment, and a file that fell out
    # of the report would be content lost under an exit code that called the transfer clean.
    findings += [
        Finding(f"top-level file `{entry.name}`", (f"{SKILL_TOP}{entry.name}",))
        for entry in held
        if not entry.is_dir() and entry.name != SKILL_MD
    ]
    # ponytail: hooks are read from the frontmatter alone, which is where a skill declares
    # its own. Workspace-level hook files belong to the workspace and not to one skill, and
    # they arrive with the part of the composition that names them.
    declared = front.get(HOOKS_KEY)
    events = declared if isinstance(declared, Mapping) else {}
    findings += [
        Finding(
            f"hook event `{event}` declared in frontmatter key `{HOOKS_KEY}`",
            (f"{EVENT}{event}", BLOCK),
        )
        for event in events
    ]
    findings += _dropped(folder, rules)
    findings += [Finding(f"frontmatter of `{file.name}`", (), line) for line in rewritten]
    return Asset(Kind.SKILL, folder, folder.name, front, tuple(findings))


def _subagent(file: Path) -> Asset:
    """One subagent file: the fields of its header and the prompt below it."""
    front, findings = _header(file, SUBAGENT_FRONTMATTER)
    findings.append(Finding("the prompt below the frontmatter", (SUBAGENT_BODY,)))
    return Asset(Kind.SUBAGENT, file, file.stem, front, tuple(findings))


def _plain(file: Path, kind: Kind, entry_id: str, word: str) -> Asset:
    """One file read as itself: it asks about one entry and its header is nobody's business.

    A command, a rule file and a manifest are carried or refused whole; what is written
    inside them is read by whatever translates them, and not by the reading of the set.
    """
    if not file.is_file():
        raise ReadError(f"{file}: no such file")
    return Asset(kind, file, file.stem, {}, (Finding(f"{word} `{file.name}`", (entry_id,)),))


READERS: dict[Kind, Callable[[Path], Asset]] = {
    Kind.SUBAGENT: _subagent,
    Kind.COMMAND: lambda file: _plain(file, Kind.COMMAND, COMMAND_FILE, "command file"),
}
"""How a file inside a named folder is read, by the part of the composition that named it."""


def _dropped(root: Path, rules: Rules) -> list[Finding]:
    """One finding for every path under ``root`` the rules keep out of the transfer.

    Each is named once: an ignored folder is not descended into, because listing every file
    inside a build cache is not an audit, it is the noise an audit is meant to cut through.
    """
    findings: list[Finding] = []
    pending = [root]
    while pending:
        for entry in _listed(pending.pop()):
            if rules.ignored(entry.relative_to(root).as_posix()):
                findings.append(Finding(_named(entry, root), (), DROPPED))
            elif entry.is_dir() and not entry.is_symlink():
                pending.append(entry)
            elif entry.is_dir():
                # The same branch as in `_files_in`, and for the same reason. Below the top
                # of the folder there is no `skill.dir.<name>` to name a link instead, so a
                # link left unsaid here is not an audit gap but the folder itself lost.
                findings.append(Finding(_named(entry, root), (), LINKED))
    return sorted(findings, key=lambda finding: finding.found_as)


UNHOLDABLE = "JSON has no way to hold it, and no text it is always written as"
NO_TEXT_FOR = {
    "float": "JSON has no `nan` and no infinity: `json.dumps` spells them `NaN` and "
    "`Infinity`, which is Python's own extension to the format and not a number a strict "
    "reader will accept",
    "set": "a set has no order, so the same header would put different bytes in the "
    "assembled file on the next run",
    "bytes": "bytes have no spelling of their own, and the nearest thing to one is a Python "
    "repr handed to whatever reads the file next",
}
"""Why a shape YAML carries and JSON does not is refused -- one reason each, the one that fired.

Printing all of them would have a person holding a `!!binary` read about the order of sets.
The module answers this way throughout: the anchor names its line, the size limit its number.
"""


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

FRONTMATTER_CLOSE = re.compile(r"\r?\n---[ \t]*(?:\r?\n|\Z)")
"""The line that closes a header: exactly ``---``, not merely a line starting with it.

A YAML key is free to start with three dashes -- ``---note: below`` is as valid a mapping
entry as any other -- so a scan for the text ``---`` at the start of a line would close the
header there and read everything past it as body, unnoticed by the person and the
frontmatter parser both. Every conventional frontmatter reader closes only at a line with
nothing else on it, which is what this pattern asks for.

CRLF line endings close a header exactly as LF ones do: a skill file written on Windows is
a skill file, and the bytes are copied as they were found either way.
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
        # The parser goes first. A key YAML allows and a mapping cannot hold -- `? [a, b]`
        # builds a list -- is refused there, as the `ConstructorError` every other structural
        # break arrives as; asked about before that, it is a key that cannot go into a set,
        # and the answer to the caller would be a traceback rather than a report.
        mapping = super().construct_mapping(node, deep=deep)
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
        return mapping


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


def _as_spelled(key: Any) -> str:
    """The key as the header writes it, asked of `yaml` rather than printed as a Python value.

    A `repr` would name the type -- `datetime.date(2026, 9, 14)` -- which is a string the
    file does not contain, and this module names a value by what it reads as and never by
    its type. Dumped back into YAML, a key comes out the way it is written there: bare where
    the format reads it as a date or a number, quoted where it is text. That quoting is the
    whole of the difference between two keys that collapse into one, so it is the difference
    a person is shown.
    """
    return yaml.safe_dump(key, default_flow_style=True).removesuffix("...\n").strip()


def _as_written(key: Any) -> str:
    """The text a key ends up as in what this run writes, asked of `json` and not guessed.

    Two keys that differ here are two keys in the result; two that agree are one key in it,
    whatever they were in the file. Asking by dumping and reading back rather than by a
    table of pairs, because the rules for spelling a key belong to the format and not to us:
    a date and the quoted text of it collapse here, and so do `1` and `"1"`, `true` and
    `"true"`, `null` and `"null"` -- and so will whatever else the format decides to spell
    the same way, without a line added here. A key that is unwritable never reaches this:
    `_portable` refuses it above, which is what leaves only keys `json` can hold.
    """
    return str(next(iter(json.loads(json.dumps({key: 0})))))


def _portable(value: Any, where: str, path: Path, rewritten: list[str]) -> Any:
    """``value`` as something JSON holds, and a line for every value that had to change.

    YAML carries shapes JSON does not, and they fall in two halves. A date and a timestamp
    have one text they are always written as -- the one ISO 8601 spells -- so they cross as
    that text, and the line this appends is how a reader learns that they did. A set has no
    order and bytes have no spelling: there is no text they read back as, and the nearest
    thing to one comes out differently on every run, which would put different bytes in the
    assembled file on the same skill. Those are refused, where every other header this
    command cannot carry across is refused.

    Keys go through this too, and not because they might be dates: JSON has no key but a
    string, and `json.dumps` refuses a date one whatever is done about its values.
    """
    if isinstance(value, Mapping):
        # Gathered key by key into a mapping of its own rather than built as a comprehension:
        # two keys that differ in the file can end up as one in what this run writes, and a
        # comprehension would keep the last of them without a word. That silence is what
        # `_StrictLoader` refuses a key declared twice for, and this is the same duplicate,
        # made by carrying the header across rather than by the person who wrote it. Which
        # keys those are is `_as_written`, asked of the format rather than listed here: where
        # the collapse happens on the way is our business and not the reader's -- the value
        # is gone either way.
        carried: dict[Any, Any] = {}
        spelled: dict[str, Any] = {}
        for key, item in value.items():
            inside = f"{where}.{key}"
            name = _portable(key, inside, path, rewritten)
            written = _as_written(name)
            if written in spelled:
                raise ReadError(
                    f"{path}: `{where}` declares {_as_spelled(spelled[written])} and "
                    f"{_as_spelled(key)}, which are two keys in the file and the one key "
                    f"`{written}` in what this run writes; the value of the first would be "
                    "dropped here without a word. Rename one of them, or remove it -- "
                    "quoting will not part them, because both cross as that same text",
                )
            spelled[written] = key
            carried[name] = _portable(item, inside, path, rewritten)
        return carried
    if isinstance(value, list):
        return [
            _portable(item, f"{where}[{index}]", path, rewritten)
            for index, item in enumerate(value)
        ]
    # `datetime` is a `date`, and both answer `isoformat`. A `bool` is an `int` and neither
    # is touched: JSON holds them as they are, and `true` is what `true` was written as.
    if isinstance(value, date):
        text = value.isoformat()
        rewritten.append(
            f"`{where}` was written as a {type(value).__name__} and is carried as the text "
            f"`{text}`: YAML has a date and JSON has none, so that text is what any file "
            "this run writes puts there, and what the target environment will read"
        )
        return text
    if value is None or isinstance(value, (str, int)):
        return value
    # A float JSON holds is a finite one. `nan` and the two infinities leave `json.dumps` as
    # a bare `NaN` or `Infinity` -- Python's own extension to the format, which a strict
    # reader refuses -- so the file would leave here looking assembled and arrive unreadable.
    # They belong with the set and the bytes below, and they get past a check written against
    # exactly them only because asking the type is not asking whether the value can be
    # written down.
    if isinstance(value, float) and isfinite(value):
        return value
    # Named by what it reads as, not by its type, where the two differ: every number JSON
    # holds is a float too, so "reads as a float" would send a person to the wrong line.
    form = repr(value) if isinstance(value, float) else type(value).__name__
    raise ReadError(
        f"{path}: `{where}` reads as `{form}`, and "
        + NO_TEXT_FOR.get(type(value).__name__, UNHOLDABLE)
        + "; quote the value to move it across as text",
    )


def frontmatter(path: Path, *, required: Sequence[str] = ()) -> tuple[dict[str, Any], list[str]]:
    """The frontmatter of ``path`` as JSON holds it, the lines its rewrites owe the report,
    or a refusal naming what is wrong and where.

    Every refusal here is structural: the file is not the shape a skill file has, so no
    part of it can be trusted to mean what it appears to mean.
    """
    if not path.is_file():
        raise ReadError(f"{path}: no such file to read a header from")
    size = path.stat().st_size
    if size > SKILL_FILE_BYTES:
        raise ReadError(
            f"{path}: the file is {size} bytes, past the {SKILL_FILE_BYTES} this command "
            "will read; a skill file that size is not one, and reading it to find out would "
            "be letting the folder decide how much memory the run takes",
        )
    raw = path.read_bytes()
    if raw.startswith(codecs.BOM_UTF8):
        raise ReadError(
            f"{path}: the file opens with a UTF-8 byte order mark, so the `---` that opens "
            "the frontmatter is not the first byte; save the file without a BOM",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReadError(f"{path}: not UTF-8 text ({error})") from error
    if not text.startswith("---"):
        raise ReadError(f"{path}: no frontmatter; a skill file opens with a `---` line")
    closing = FRONTMATTER_CLOSE.search(text, 3)
    if closing is None:
        raise ReadError(
            f"{path}: the frontmatter opened on line 1 is never closed by a `---` line",
        )
    header = text[3 : closing.start()]
    if len(header.encode("utf-8")) > FRONTMATTER_BYTES:
        raise ReadError(
            f"{path}: the frontmatter is longer than {FRONTMATTER_BYTES} bytes, which is "
            "not a header any more; what belongs in the body of the skill goes below the "
            "closing `---` line",
        )
    try:
        # A header nested past what the parser itself can carry arrives as a `RecursionError`,
        # which is the depth limit being hit before this function gets to apply its own.
        loaded = yaml.load(header, _StrictLoader)
    except _Anchored as error:
        raise ReadError(
            f"{path}: the frontmatter declares a YAML anchor on line {error.line}. Anchors "
            "and the aliases repeating them are valid YAML and are refused here all the "
            "same (FR-15): the text a person reads in the file and the value the parser "
            "builds stop being the same thing, and this command cannot carry both across",
        ) from error
    except (yaml.YAMLError, RecursionError) as error:
        raise ReadError(f"{path}: the frontmatter is not valid YAML ({error})") from error
    if not isinstance(loaded, dict):
        raise ReadError(
            f"{path}: the frontmatter is not a mapping of keys "
            f"(it reads as {type(loaded).__name__})",
        )
    if _depth(loaded) > FRONTMATTER_DEPTH:
        raise ReadError(
            f"{path}: the frontmatter nests deeper than {FRONTMATTER_DEPTH} levels; a skill "
            "header that deep is a data file, and reading one is not what this command does",
        )
    missing = [key for key in required if key not in loaded]
    if missing:
        raise ReadError(
            f"{path}: the frontmatter declares no "
            + " and no ".join(f"`{key}`" for key in missing)
            + "; the description of the target environment marks the field required, so "
            "there is nothing here that could be assembled for it, and a value invented "
            "for the field would be this command writing the skill rather than moving it",
        )
    rewritten: list[str] = []
    carried: dict[str, Any] = _portable(loaded, "frontmatter", path, rewritten)
    return carried, rewritten
