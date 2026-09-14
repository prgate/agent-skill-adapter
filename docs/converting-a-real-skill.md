# Converting a real skill

Three runs of `agent-skill-adapter convert` over skills that were installed in
`~/.claude/skills/` on **2026-09-14**, against the descriptions in `specs/` as they stood
that day. Nothing was invented for this page: the output below is what the commands
printed. Every run wrote only into a throwaway folder passed as `--out`.

Common arguments: `--source anthropic/claude-code@2.1.0 --target google/antigravity@2.0.0`.

**Reproducing this later takes one more flag.** The descriptions carry
`checked_at: 2026-09-14` and `stale_after_days: 30`; from 2026-10-14 on, `select` refuses
them and the same commands answer "due for a re-check" instead of the output below. Add
`--allow-stale` to read them anyway, or re-check them first with
`uv run python -m agent_skill_adapter.envspec.freshness --root specs --write` — the only
command here that uses the network. A skill folder that has changed since will of course
print its own rows, not these.

## 1. A skill that transfers — exit code 0

```
uv run agent-skill-adapter convert ~/.claude/skills/document-summary-arrangement \
  --source anthropic/claude-code@2.1.0 --target google/antigravity@2.0.0 --out /tmp/out
```

```
~/.claude/skills/document-summary-arrangement: clean (exit 0)
  clean        skill.frontmatter.name -- frontmatter key `name` (reproduced, specification)
  clean        skill.frontmatter.description -- frontmatter key `description` (reproduced, specification)
  clean        skill.dir.scripts -- bundled directory `scripts/` (reproduced, specification)
  wrote /tmp/out/.agents/skills/document-summary-arrangement/SKILL.md (it belongs at .agents/skills/document-summary-arrangement/SKILL.md)
  wrote /tmp/out/.agents/skills/document-summary-arrangement/scripts (it belongs at .agents/skills/document-summary-arrangement/scripts/)
```

The assembled folder, with the six scripts of the bundle carried over:

```
/tmp/out/.agents/skills/document-summary-arrangement/SKILL.md
/tmp/out/.agents/skills/document-summary-arrangement/scripts/…
```

`.agents/skills/` is not written in the converter: it is the `path` of the `skills.project`
entry of `specs/google/antigravity-2.0.yaml`, with `<workspace-root>` standing for the
folder `--out` names and `<skill-name>` for the folder that was read. `--scope user` takes
`skills.user` instead, whose path begins with `~`; the report then names the home folder as
the destination, and the files are still assembled under `--out` and nowhere else.

## 2. A skill that transfers with a loss — exit code 1

```
uv run agent-skill-adapter convert ~/.claude/skills/autopilot … --out /tmp/out
```

```
~/.claude/skills/autopilot: lossy (exit 1)
  clean        skill.frontmatter.name -- frontmatter key `name` (reproduced, specification)
  clean        skill.frontmatter.description -- frontmatter key `description` (reproduced, specification)
  lossy        skill.frontmatter.argument-hint -- frontmatter key `argument-hint` (unknown, extension)
  lossy        skill.dir.phases -- bundled directory `phases/` (unknown, extension); no entry with this id in either description
  lossy        skill.dir.prompts -- bundled directory `prompts/` (unknown, extension); no entry with this id in either description
  lossy        skill.dir.tools -- bundled directory `tools/` (unknown, extension); no entry with this id in either description
  wrote /tmp/out/.agents/skills/autopilot/SKILL.md (it belongs at .agents/skills/autopilot/SKILL.md)
```

`argument-hint` is Claude Code's own field, and `phases/`, `prompts/` and `tools/` are this
skill's own directories: no open format ever promised them elsewhere, so their loss is the
ordinary price of moving between two products, and the exit code says the transfer is worth
making with eyes open. The three directories are not carried to an invented place — the
target description names none for them — and each is a line of the report rather than a
silence.

## 3. A skill that does not transfer — exit code 3

```
uv run agent-skill-adapter convert ~/.claude/skills/pr-review … --out /tmp/out
```

```
~/.claude/skills/pr-review: undecidable (exit 3)
  clean        skill.frontmatter.name -- frontmatter key `name` (reproduced, specification)
  clean        skill.frontmatter.description -- frontmatter key `description` (reproduced, specification)
  clean        skill.frontmatter.metadata -- frontmatter key `metadata` (out-of-scope, specification)
  lossy        skill.dir..omc -- bundled directory `.omc/` (unknown, extension); no entry with this id in either description
  undecidable  skill.dir.references -- bundled directory `references/` (unknown, specification)
  lossy        skill.dir.resources -- bundled directory `resources/` (unknown, extension); no entry with this id in either description
  clean        skill.dir.scripts -- bundled directory `scripts/` (reproduced, specification)
  lossy        skill.top.CHANGELOG.md -- top-level file `CHANGELOG.md` (unknown, extension); no entry with this id in either description
  lossy        skill.top.README.md -- top-level file `README.md` (unknown, extension); no entry with this id in either description
  lossy        skill.top.config.md -- top-level file `config.md` (unknown, extension); no entry with this id in either description
  lossy        skill.top.diagram.svg -- top-level file `diagram.svg` (unknown, extension); no entry with this id in either description
```

`/tmp/out` was never created. One line decides it: `references/` is a directory the open
Agent Skills specification declares, Antigravity claims to implement that format, and its
documentation says nothing about that directory. Silence from an implementer of a format
about a part of that format is not a denial and not a promise — it is a hole in someone
else's documentation, and guessing across it is what this tool exists not to do.

This is a deliberate outcome, not a defect to be patched here. Antigravity names `examples/`
and `resources/` where the specification names `references/` and `assets/`; pairing them is a
translation rule (FR-6), a separate piece of work with its own decisions. Until it exists, a
skill with a `references/` folder stops at exit code 3, and the report says which line
stopped it.

The four `skill.top.*` lines are the other half of the same rule. `CHANGELOG.md`,
`README.md`, `config.md` and `diagram.svg` sit at the top of the skill folder beside
`SKILL.md`; neither description says what the target environment does with such a file, so
each is a loss the report names. They are why no folder carrying loose files can come out of
this command with exit code 0.
