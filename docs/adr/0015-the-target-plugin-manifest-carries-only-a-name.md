# 0015. The target's plugin manifest carries only `name`

## Context and Problem Statement

The brief described the target's plugin manifest as a `plugin.json` listing the plugin's skills and
rules plus its `hooks.json` and `mcp_config.json`, and the plan was to rewrite the source manifest
into that shape.

The documentation shipped with the CLI says otherwise (`agy-customizations/docs/plugins.md`,
section "Manifest (`plugin.json`)"): the manifest carries `name`, optional and defaulting to the
folder name, and `disabled`, optional. Skills, rules, hooks and MCP configuration are found by the
structure of the plugin folder, not named by the manifest. This is `D02` — what the run established
against what the plan assumed.

## Decision Outcome

Rewriting the manifest means a `plugin.json` with `name`, and the plugin's parts laid out in its
folder. `description`, `version`, `homepage` and the source manifest's lists of skills and rules
have no place in the target format, and each earns its own report row rather than being carried or
dropped.

So the converter can ask rather than know, the target description declares the manifest's fields as
entries of their own — `settings.file.plugin-manifest.<field>` — against the shipped source
(ADR-0014). The vendor's field list is data, like every other vendor fact.

## Considered Options

- **Build the manifest the brief described.** Rejected on evidence: nothing documents that shape.
  The result would be a file the environment ignores, over a report saying the plugin transferred —
  the same silence the whole track is written against, this time manufactured by us.
- **Carry the source manifest's extra fields into the target `plugin.json`, on the grounds that an
  unknown key is harmless.** Rejected: the format has two fields, and an unrecognised key is at best
  ignored and at worst rejected. Either way the information in it — a version, a homepage — would be
  reported as having crossed while nothing reads it. A row saying the field has no counterpart in
  the target format tells the owner something true and actionable.
- **Keep the field list in the converter.** Rejected: it is one vendor's vocabulary written into
  code, which the conventions forbid, and it would sit outside `specs/` where nothing dates it,
  hashes it or compares it.

## Consequences

The brief is wrong on this point and stays on the record as written; anyone reading it later needs
this ADR beside it. That is the cost of keeping the brief a record of what was asked rather than a
document edited to match what was found.

A transferred plugin loses its description, version and homepage. They remain in the source set,
which is not modified, and the report names each one.

Because the environment finds the parts of a plugin by the folder's structure, whether a plugin
transfer works is a property of the layout entries rather than of the manifest. Getting `layout`
right is what matters here; the manifest is almost nothing.
