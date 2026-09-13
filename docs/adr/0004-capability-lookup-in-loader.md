# 0004. Capability lookup is a loader function, not a model method

## Context and Problem Statement

The drafted module boundaries placed capability lookup on the data class as `EnvSpec.capability(id)`,
while assigning `envspec.model` ownership of the shape of a description and nothing else. Task 02
implemented the lookup and the two statements turned out to be incompatible.

## Decision Outcome

Lookup is `envspec.loader.capability(spec, id) -> Support`. `envspec.model` keeps only the shape of
the data. R22 is unchanged: an id with no record still yields `UNKNOWN`.

## Considered Options

- **Keep `EnvSpec.capability(id)` as planned.** Rejected: it puts search logic into the module that
  was given the shape of the data and nothing more, and adding it mid-build meant editing another
  task's zone while that task was open.
- **A third module for lookup.** Rejected: one function does not justify a seam, and the loader
  already owns reading, validation, selection and staleness — the same "answer questions about a
  description" surface.

## Consequences

A caller that already holds an `EnvSpec` still has to import the loader to ask about a capability;
the model layer alone cannot answer the question. In exchange, `model.py` stays a pure shape
declaration, which is what makes "add an environment by writing a file, not by editing code"
checkable.
