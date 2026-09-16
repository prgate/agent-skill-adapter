# Live acceptance: asking the target environment what it actually loaded

A report is a claim. This procedure turns the claim into an observation: the set is carried
over, a throwaway workspace is handed to the live Antigravity CLI, and the environment is
asked questions it can only answer by having read the carried files.

**What counts as proof.** A line quoted back verbatim from a carried file, or an explicit
"there is no such file". "Yes, I see it" proves nothing — the model will say that about a
file it never opened. Every answer below is reproduced exactly as the environment printed it.

**What is never touched.** The live user root `~/.gemini/` is off limits: every run assembles
with `--out` into a temporary workspace and the environment is asked from there. The sample
sets are read-only inputs and are never edited to make a run succeed.

## Prerequisites

- `agy --version` → `1.2.4`. Another version may answer differently; record the one you ran.
- The repository checked out, `make install` done.
- Two inputs, and they must stay two. One is the set this project was shaped around; the
  other is a small set in a layout nobody here chose, which is what catches a rule
  accidentally written for one repository. Both run with one command each and **no code
  change between them**.

## Step 1 — carry both sets over

`$SP` is any scratch directory; `$KIT` is the first set; `$B` is the second.

```sh
uv run agent-skill-adapter convert \
  --skills "$KIT/skills" --agents "$KIT/agents" --commands "$KIT/commands" \
  --rules "$KIT/GEMINI.md" \
  --rules "$KIT/patterns/native-language.md" --rules "$KIT/patterns/review-patterns.md" \
  --rules "$KIT/patterns/smell-baseline.md" \
  --rules "$KIT/contexts/dev.md" --rules "$KIT/contexts/review.md" \
  --source anthropic/claude-code@2.1.0 --target google/antigravity@2.0.0 \
  --out "$SP/run-kit" --allow-stale --report "$SP/kit-report.json"

uv run agent-skill-adapter convert \
  --skills "$B/bundles" --agents "$B/roles" --commands "$B/shortcuts" \
  --rules "$B/policy/tone.md" \
  --source anthropic/claude-code@2.1.0 --target google/antigravity@2.0.0 \
  --out "$SP/run-b" --allow-stale --report "$SP/b-report.json"
```

`--allow-stale` is needed because the descriptions are past their re-check date; drop it once
they are refreshed. Both runs exit 1 (`lossy`) — the rows say why, and the exit code is the
verdict, not a failure of the run.

## Step 2 — make each assembled tree a workspace

Antigravity reads workspace rules only inside a project, and only when the session is told
to make one. A plain directory is not enough; `git init` and one commit are.

```sh
for r in run-kit run-b; do
  mkdir -p "$SP/ws-$r" && cp -R "$SP/$r/.agents" "$SP/ws-$r/"
  ( cd "$SP/ws-$r" && git init -q && git add -A && git commit -qm init )
done
```

## Step 3 — ask the environment

Run every question from inside the workspace directory, with `--new-project`. **Without
`--new-project` the workspace rules are not loaded at all**, so a missing answer would say
nothing about the carried files. Add `--print`/`-p` for a single non-interactive turn.

```sh
cd "$SP/ws-run-b"
agy --new-project -p='<question>'
```

Ask for the answer *from context only, without any tool* wherever the point is that the
environment loaded the file by itself. Only the bundle-file question below is allowed a
file-reading tool, because there the point is that the file exists where it was put.

There is also `agy agents`, which lists subagents without going through a model.

Headless runs cannot prompt for tool permissions: a question whose answer needs a shell
command dies with `no output produced — a tool required the "command" permission`. Phrase the
question so no tool is needed, or allow the tool in `settings.json`.

## Results, `agy` 1.2.4, 2026-09-17

### Rules — carried, loaded, quoted

Question (kit workspace, no tools): quote verbatim the first line of the workspace rule whose
title mentions "Native language".

> `# Native language — качество перевода в порождаемом тексте`

Byte for byte the first line of `.agents/rules/native-language.md`. The same question in the
second workspace, asking for the line beginning with `ANCHOR-`:

> ANCHOR-SAMPLE-B-9X2P: notes are written in plain sentences, never bullet fragments.

Both files reached the environment because the converter added `trigger: always_on` to them.
Without that header the same file is silent — that was measured separately (ADR-0009).

### Skills — named, and a bundled file read

Second workspace, list of skills from context:

> agy-customizations, antigravity-guide, issue-pr-authoring, note-taker, pr-business,
> pr-conventions, pr-loop, pr-publish, pr-review

`note-taker` exists nowhere but this workspace, and the environment names it by its
frontmatter `name`, not by the directory name the converter wrote
(`note-taker-antigravity/`).

In the kit workspace the same question returns only `agy-customizations` — but asked whether
a skill named `pr-review` is among them, the environment quotes its own reason:

> `The following items were excluded due to context budget limits: antigravity-guide,
> issue-pr-authoring, pr-business, pr-conventions, pr-loop, pr-publish, pr-review`

So the six carried skills are registered and named; they are dropped from the loaded context
by a budget, which is a property of the environment, not of the transfer.

A file inside a bundle, opened with the environment's own file tool
(`.agents/skills/pr-review-antigravity/references/risk-triggers.md`, first line):

> `# Risk Triggers and Severity — калибровка рисков и важности`

### Subagents — visible, and the `tools` field decides it

Kit workspace, from context only:

> `self`, `research`, `prg-developer`, `prg-fix`, `prg-reviewer`, `prg-security-reviewer`

and, asked for one of them verbatim:

> Автономный fix-оркестратор для прод-бага. Diagnose → regression-тест (RED) → минимальный
> безопасный фикс (GREEN) → verify. Использовать когда есть блокирующий баг в state machine /
> транзакциях / idempotency / retry, и нужно восстановить корректность, а не «починить тест».

That is the `description` of `.agents/agents/prg-fix.md` word for word, so the environment
read the carried file. **This contradicts the earlier conclusion of this project that no
user subagent is ever named by this version.**

A model can read a directory, so a list of names could in principle be a retelling of
`ls .agents/agents/` rather than an answer from the environment. What rules that out here is
that `self` and `research` stand beside the four carried names: they are the environment's
built-ins and no file for them exists in the carried folder. The answer therefore comes from
the registry the environment assembled while loading, not from the contents of a directory.

The second workspace, run the same way, once named only `self` and `research`. One field
explained it. Its subagent had been carried with

```yaml
tools: view_file, Write, grep_search, SendMessage
```

because that is how the source file spelled it, while the kit's subagents spell it as a list.
Rewriting that one line by hand, and nothing else, made the environment answer:

> `self`, `research`, `note-keeper`

So a subagent whose `tools` is a comma-separated string is dropped without a word; the same
subagent with `tools` as a list appears. The converter now writes the second form, because
the target's frontmatter table types the field `string[]` and its example spells the value as
a list: the form is the closed value set of `subagent.frontmatter.tools.form` in the target
description, and turning one form into the other is a pair in the translation rules, reported
like every other translated value. Carried by the command in step 1 and asked again, the same
workspace answers:

> self, research, note-keeper

The `agy agent` and `agy agents` subcommands print nothing and exit 0 in every workspace,
whatever is on disk — confirmed twice, independently. Neither is a usable probe on this
version; the question has to go through a session.

**Where this was measured.** All of it is the project level: `.agents/agents/` inside a
throwaway workspace, which is where `--scope project` puts a subagent. The user level
(`~/.gemini/config/agents/`) was written to by nobody over this whole effort, and nothing
above says anything about it. That is a limit of the check, not a property of the transfer.

### Commands — absent, and the report says so

Both workspaces, asked for user-defined slash commands:

> NO COMMANDS

Which is what both reports print: the target names no root for a command, so no command file
is written anywhere, and each one earns a row saying to call the skill it wrapped by name.
Report and environment agree.

## Failures this procedure found, and what answered them

Both were found by running it and are fixed; they are kept here because the procedure is
what turned them up, and re-running it is how a return of either would be noticed.

- **A `README.md` in the subagents folder stopped the whole run** with exit 6, saying the
  file carried no frontmatter. A file in a named folder that does not look like an entity
  earns a row instead (FR-3a), and what a subagent looks like is the header line it opens
  with. The first set carries `agents/README.md` and `commands/README.md` and now crosses in
  one command with a row for each.
- **`__pycache__` was reported as dropped and written anyway** — rows said the ignore list
  kept it out, `written` did not list it, and five `.pyc` files were on disk under
  `.agents/skills/*/scripts/__pycache__/`, because a bundled directory is copied whole and
  the ignore list had only spoken while the set was read. The copy asks the same rules now.
  The check is to compare `written` with what is under the assembled tree: every file on
  disk has to sit under something that list names.
