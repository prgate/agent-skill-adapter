"""The description format as JSON Schema, for tools that do not import this package.

An editor completing a `specs/*.yaml` file, or someone else's validator checking one, cannot
read pydantic classes. This module renders the same shape as a standalone document so the
format can be checked without installing anything of ours.

The schema is generated, never hand-edited: a hand-kept copy drifts from the model silently,
and a schema that disagrees with the model is worse than no schema, because it is believed.
:mod:`tests.unit.test_envspec_schema` fails when the committed file and the model disagree.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_skill_adapter.envspec.model import EnvSpec

DIALECT = "https://json-schema.org/draft/2020-12/schema"

OUT = Path("specs/schema/envspec.schema.json")
"""Where the committed schema lives, relative to the repository root -- see :func:`main`."""

COMMAND = "uv run python -m agent_skill_adapter.envspec.schema"
"""How to rebuild it. Named in the failure message of the test that guards the file."""


def render() -> str:
    """:class:`EnvSpec` as a JSON Schema document, in the spelling the YAML files use.

    ``by_alias`` is what makes it usable: a ``tool_names`` entry is ``from``/``to`` on disk and
    ``from_name``/``to_name`` in Python, and a schema describing the Python names would reject
    every file it is pointed at.
    """
    schema = {"$schema": DIALECT, **EnvSpec.model_json_schema(by_alias=True)}
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    """Write the schema to :data:`OUT`, resolved against the current directory.

    Run from the repository root, as the sibling developer commands are (`make schema`).
    """
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"{OUT}: schema of EnvSpec, {len(EnvSpec.model_fields)} top-level fields")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
