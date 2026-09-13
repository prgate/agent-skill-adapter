"""Fill and verify the provenance hashes of an environment spec manifest.

Usage:
    python scripts/spec_provenance.py fill   specs/claude-code/1.0.0/spec.yaml
    python scripts/spec_provenance.py verify specs/claude-code/1.0.0/spec.yaml

Hash contract (fixed):
1. HTML to text; tags dropped, `<code>` keeps its content, `<script>`/`<style>`
   content discarded.
2. Unicode NFC; `\\r\\n` to `\\n`.
3. Runs of whitespace to one space; trim.
4. UTF-8 bytes to sha256, written with the `sha256:` prefix.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_skill_adapter.specs.loader import dump_manifest, load_manifest  # noqa: E402
from agent_skill_adapter.specs.models import Manifest, Provenance  # noqa: E402

_USER_AGENT = "agent-skill-adapter-spec-provenance/1.0"
_SKIPPED_TAGS = {"script", "style"}


def _heading_level(tag: str) -> int | None:
    if len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
        return int(tag[1])
    return None


class _SectionExtractor(HTMLParser):
    """Collects the text of the heading section that carries a given `id`."""

    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self._target_id = target_id
        self._collecting = False
        self._level: int | None = None
        self._skip_depth = 0
        self.found = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        level = _heading_level(tag)
        if level is not None:
            if not self._collecting and dict(attrs).get("id") == self._target_id:
                self._collecting = True
                self.found = True
                self._level = level
            elif self._collecting and self._level is not None and level <= self._level:
                self._collecting = False
                self._level = None
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._collecting and self._skip_depth == 0:
            self.chunks.append(data)


def normalize(text: str) -> str:
    """Steps 2-3 of the hash contract."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    return " ".join(text.split())


def extract_section(html: str, anchor: str) -> str | None:
    """Step 1 of the hash contract: cut the section addressed by `anchor`."""
    parser = _SectionExtractor(anchor.lstrip("#"))
    parser.feed(html)
    parser.close()
    if not parser.found:
        return None
    return "".join(parser.chunks)


def section_hash(text: str) -> str:
    """Steps 2-4 of the hash contract."""
    digest = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        body: bytes = response.read()
    return body.decode("utf-8", errors="replace")


def iter_records(manifest: Manifest) -> list[tuple[str, Provenance]]:
    """Every provenance-carrying record, addressed as it is in the dumped dict."""
    spec = manifest.spec
    records: list[tuple[str, Provenance]] = []
    for group_name, group in (
        ("skillFields", spec.skill_fields),
        ("agentFields", spec.agent_fields),
        ("hooks", spec.hooks),
    ):
        records.extend((f"{group_name}/{record.name}", record.provenance) for record in group)
    records.extend((f"tools/{record.name}", record.provenance) for record in spec.tools)
    records.extend((f"limits/{record.name}", record.provenance) for record in spec.limits)
    records.extend(
        (f"invisibleSources/{source.path}", source.provenance) for source in spec.invisible_sources
    )
    if spec.frontmatter is not None:
        records.append(("frontmatter", spec.frontmatter.provenance))
    if spec.layout is not None:
        records.append(("layout", spec.layout.provenance))
    return records


def _section_text(provenance: Provenance) -> tuple[str | None, str | None]:
    """Return `(text, reason)`: text is None exactly when reason explains why."""
    if provenance.selector is not None:
        return None, "selector-not-supported"
    try:
        html = fetch(provenance.url)
    except (urllib.error.URLError, OSError) as error:
        return None, f"fetch-failed: {error}"
    assert provenance.anchor is not None
    section = extract_section(html, provenance.anchor)
    if section is None:
        return None, "anchor-not-found"
    return section, None


def _provenance_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Locate the mutable `provenance` mapping addressed by an `iter_records` key."""
    spec = data["spec"]
    if "/" in key:
        group, name = key.split("/", 1)
        id_field = "path" if group == "invisibleSources" else "name"
        for item in spec[group]:
            if item[id_field] == name:
                provenance: dict[str, Any] = item["provenance"]
                return provenance
        raise KeyError(key)
    singleton: dict[str, Any] = spec[key]["provenance"]
    return singleton


def fill(path: Path) -> int:
    """Fill `hash` and `checkedAt` for every record whose `hash` is still empty."""
    manifest = load_manifest(path)
    data = manifest.model_dump(mode="python", by_alias=True)
    failed = False
    for key, provenance in iter_records(manifest):
        if provenance.hash is not None:
            continue
        text, reason = _section_text(provenance)
        if text is None:
            print(f"FAILED {key}: {reason}")
            failed = True
            continue
        target = _provenance_dict(data, key)
        target["hash"] = section_hash(text)
        target["checkedAt"] = date.today()
        print(f"filled {key}")
    revalidated = Manifest.model_validate(data)
    path.write_text(dump_manifest(revalidated), encoding="utf-8")
    return 1 if failed else 0


def verify(path: Path) -> int:
    """Recompute every hash; record drift and refresh `status`."""
    manifest = load_manifest(path)
    data = manifest.model_dump(mode="python", by_alias=True)
    drift: list[dict[str, Any]] = []
    for key, provenance in iter_records(manifest):
        if provenance.hash is None:
            drift.append({"record": key, "reason": "hash-missing"})
            print(f"DRIFT {key}: hash-missing")
            continue
        text, reason = _section_text(provenance)
        if text is None:
            drift.append({"record": key, "reason": reason})
            print(f"DRIFT {key}: {reason}")
            continue
        actual = section_hash(text)
        if actual != provenance.hash:
            drift.append(
                {
                    "record": key,
                    "expected": provenance.hash,
                    "actual": actual,
                    "reason": "section-text-changed",
                }
            )
            print(f"DRIFT {key}: section-text-changed")
    data["status"]["drift"] = drift
    data["status"]["stale"] = bool(drift)
    data["status"]["verifiedAt"] = date.today()
    revalidated = Manifest.model_validate(data)
    path.write_text(dump_manifest(revalidated), encoding="utf-8")
    return 1 if drift else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spec_provenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fill", "verify"):
        sub = subparsers.add_parser(name)
        sub.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command == "fill":
        return fill(args.path)
    return verify(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
