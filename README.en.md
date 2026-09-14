# Agent Skill Adapter

[Русская версия](README.md)

**Tells you what a skill loses before you move it to another agent environment.**

A skill file moves easily. The guarantees around it do not. The open Agent Skills
specification requires two fields; Claude Code adds eighteen more, plus subagents with
their own permissions and limits, plus hooks. Another environment opens that skill,
silently ignores what it does not recognise, and runs.

The file was read. The behaviour changed. What disappears is not decoration: the skill no
longer runs in its own context, the agent's tools are no longer restricted, the checks
before and after a tool call no longer happen, and the line between "only a human starts
this" and "the model may start it" is gone. A skill with side effects — one that can
commit or deploy — comes out of that transfer more dangerous than it went in.

This adapter answers, from the vendors' own documentation rather than from memory, what
survives the move and what does not.

## How it works

![How the adapter turns vendor documentation into a gap report](docs/assets/how-it-works.svg)

An **environment description** is a YAML file of what one environment documents about
itself. Every record names the documentation section it came from — url, anchor, and the
sha256 of that section's normalized text — so a claim can be traced, and a change on the
vendor's page can be detected rather than assumed.

Two descriptions are then compared entry by entry. The result is the **gap report**: for
each capability the source environment holds, what the target says about it.

Three rules decide how the report reads:

- **Silence is not a denial.** `missing` is reserved for a refusal the vendor wrote in
  words. Documentation that says nothing is `unknown`, and records the target has no entry
  for at all are counted separately from records it leaves without a verdict.
- **Absence is not support.** A capability with no record is unknown, never supported.
- **Doubt refuses.** A description carrying a discrepancy, or checked longer ago than it
  declares, is stale and is not handed out. A version outside every declared range is
  refused rather than resolved to the nearest description.

The comparison never touches the network and returns the same bytes for the same inputs.
Only the freshness check goes online.

## What it says today

Claude Code 2.1 → Google Antigravity 2.0, from documentation checked 2026-09-14:

| Outcome | Entries | Of which the target has no entry for |
|---|---|---|
| reproduced | 22 | 0 |
| missing | 0 | 0 |
| unknown | 70 | 8 |
| out of scope | 3 | — |

Antigravity documents 2 of Claude Code's 20 skill frontmatter fields, 3 of its 33 hook
events, and 7 of its 19 subagent fields. `missing` is zero because across all 91 of its
documentation pages Antigravity never denies a capability in words — it enumerates what it
supports and is silent about the rest.

That distinction is the point of the report. Continuing this project is justified by
documentation that says nothing, not by an environment that says no.

Full list: [`specs/gaps/claude-code-to-antigravity.md`](specs/gaps/claude-code-to-antigravity.md).

## What exists and what does not

**Nothing is converted yet.** Today the tool answers one question — what exactly a transfer
loses — and moves no files at all. The PRD requires that answer **before** any work on the
core: had nothing turned out to be untransferable, the product would reduce to copying
files and would not be worth building.

The whole design — solid lines work today, dashed ones do not yet:

![The adapter end to end, from a skill repository to a build for the target environment](docs/assets/end-to-end.svg)

What works:

- descriptions of two environments, every record anchored to a documentation section by
  url, anchor and digest;
- the loader: selection by environment version, refusal on a stale or ambiguous
  description;
- the freshness check against the vendor documentation, recording drift into the
  description file itself;
- the computed gap list.

Not built yet: reading a repository of skills, grading each capability of a transfer, the
transfer report, rewriting skill text for the target environment, emitting the result, and
the exit codes. Those are blocks B–F of
[PRD-001](docs/prd/PRD-001-agent-skill-adapter.md).

## Quick start

Requires Python 3.10+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone git@github.com:prgate/agent-skill-adapter.git
cd agent-skill-adapter
make install
```

Rebuild the gap report from the descriptions in `specs/`:

```bash
uv run python -m agent_skill_adapter.envspec.gaps
```

It writes `specs/gaps/claude-code-to-antigravity.md` and `.json`. Same inputs, same bytes —
a rerun that changes nothing leaves the files untouched. It exits non-zero when nothing is
missing and nothing is unknown, because that would mean the transfer is a file copy and
this tool is not needed.

Ask a description a question directly:

```bash
uv run python - <<'PY'
from agent_skill_adapter.envspec.loader import select, capability

spec = select("specs", "anthropic", "claude-code", "2.1.270")
print(spec.environment, spec.version_range, spec.checked_at)
print(capability(spec, "skill.frontmatter.allowed-tools"))
PY
```

Check whether the vendors' documentation has moved since the descriptions were written —
the one command that uses the network:

```bash
uv run python -m agent_skill_adapter.envspec.freshness            # report only
uv run python -m agent_skill_adapter.envspec.freshness --write    # record what changed
```

A changed section, an unreachable page, or a vanished anchor is written into the
description file itself, so a later offline run sees the staleness by the file rather than
by a CI log.

## What it does not do

- **It does not install anything.** Laying files out per environment is what `npx skills`
  is for; this produces the standard shape and hands it over.
- **It does not write skills.** The intent is to move existing ones.
- **It does not test behaviour on a live model.** Whether a skill still behaves the same is
  a separate, paid kind of run, and it is deliberately not mixed in here.

One direction only: Claude Code → Google Antigravity. The planned input is a whole
repository; a single skill outside one is not in scope yet.

## Where to read more

- [PRD-001](docs/prd/PRD-001-agent-skill-adapter.md) — the problem, the scope, and the 33
  requirements, including nine decisions consciously left open.
- [`docs/adr/`](docs/adr/) — why the design is the way it is, and what was rejected.
- [`docs/assets/how-it-works.html`](docs/assets/how-it-works.html) and
  [`end-to-end.html`](docs/assets/end-to-end.html) — both diagrams as explorable pages.
- [Documentation hub](docs/README.md).

## Development

```bash
make check          # ruff, ruff format --check, mypy strict, pytest — the gate CI runs
make test           # tests only
make format         # apply formatting and safe fixes
```

Conventions, module boundaries and the pitfalls worth knowing before the first edit are in
[`AGENTS.md`](AGENTS.md).

## License

[Apache-2.0](LICENSE).
