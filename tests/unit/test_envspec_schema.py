"""The committed JSON Schema and the model it is generated from must not drift apart."""

import json
from pathlib import Path
from typing import Any

from agent_skill_adapter.envspec.schema import COMMAND, OUT, render

REBUILD = f"the committed schema is no longer the model's -- re-run `{COMMAND}` (or `make schema`)"


def test_committed_schema_matches_the_model() -> None:
    """`specs/schema/envspec.schema.json` is generated, and only this test notices a skipped run.

    A new field in `model.py` is an ordinary rebuild, not a break: run the command and commit
    the file. A schema that disagrees with the model is worse than no schema -- it is believed.
    """
    committed = (Path(__file__).resolve().parents[2] / OUT).read_text(encoding="utf-8")

    assert committed == render(), REBUILD


def test_schema_speaks_the_yaml_spelling_of_tool_names() -> None:
    """A `tool_names` entry is `from`/`to` on disk and `from_name`/`to_name` in Python.

    Generated without the aliases, the schema would reject every file it is pointed at, and
    the drift test above would stay green: it compares the committed file to the generator,
    not the generator to the format on disk.
    """
    document: dict[str, Any] = json.loads(render())

    assert sorted(document["$defs"]["ToolName"]["properties"]) == ["from", "source_id", "to"]
