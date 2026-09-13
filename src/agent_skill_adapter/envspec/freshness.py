"""Checking recorded sources against the vendor documentation.

This is the only module of the project allowed to reach the network, and it reaches it
through one injected function: :func:`check` takes ``fetch`` as a parameter, so nothing
below this module — and no test — needs a network at all.
"""

from __future__ import annotations

import re
from argparse import ArgumentParser
from collections.abc import Callable, Sequence
from datetime import date
from http.client import HTTPException
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

from agent_skill_adapter.envspec.loader import load
from agent_skill_adapter.envspec.model import Discrepancy, DiscrepancyKind, EnvSpec, Source
from agent_skill_adapter.envspec.normalize import AnchorError, digest, section_text

USER_AGENT = "Mozilla/5.0"

Fetch = Callable[[str], str]
"""Return the text of a page, or raise ``OSError``.

A non-200 answer is a failure, not an empty page. ``OSError`` is what a network failure
raises (``urllib`` errors derive from it), and it is the only failure :func:`check` reads
as unreachable: anything else coming out of a ``fetch`` is a defect and must surface.
"""

# What reading a source can legitimately fail with: the server or the connection
# (OSError, which covers every urllib error), an answer that breaks off mid-body
# (HTTPException, which is not an OSError), a page that is not UTF-8, a section that
# is no longer there. A failure outside this set is a defect of ours and must not be
# filed as a discrepancy against the vendor.
_UNREACHABLE = (OSError, HTTPException, UnicodeDecodeError, AnchorError)


def markdown_url(source: Source) -> str:
    """The markdown twin of the documented page: the hash is taken from that, never from HTML.

    An HTML page changes with its styling; the markdown one changes with its content.
    """
    return source.markdown_url or f"{source.url}.md"


def check(spec: EnvSpec, *, fetch: Fetch, today: date | None = None) -> list[Discrepancy]:
    """Re-read every source of ``spec`` and report the ones that no longer confirm it.

    A section whose hash moved is ``changed`` and carries both hashes. A page that could
    not be read, or that no longer has the anchored section, is ``unreachable`` — an
    unreadable source is a discrepancy, never a confirmation that the entry still holds.
    """
    when = today or date.today()
    found: list[Discrepancy] = []
    for source in spec.sources:
        url = markdown_url(source)
        try:
            fresh = digest(section_text(fetch(url), source.anchor))
        except _UNREACHABLE as error:
            found.append(
                Discrepancy(
                    source_id=source.id,
                    kind=DiscrepancyKind.UNREACHABLE,
                    detail=f"{when}: {url}: {type(error).__name__}: {error}",
                )
            )
            continue
        if fresh != source.sha256:
            found.append(
                Discrepancy(
                    source_id=source.id,
                    kind=DiscrepancyKind.CHANGED,
                    detail=f"{when}: {url}: recorded {source.sha256}, now {fresh}",
                )
            )
    return found


_DISCREPANCIES = re.compile(r"^discrepancies:(.*)$")


def _block_indent(lines: list[str], start: int, end: int) -> str:
    """The indent the block already uses, so appended entries line up with the existing ones.

    A block written at column zero is valid YAML too: appending two-space entries to it
    would produce a file we ourselves could no longer load.
    """
    return next(
        (line[: len(line) - len(line.lstrip())] for line in lines[start + 1 : end] if line.strip()),
        "  ",
    )


def _section_end(lines: list[str], start: int) -> int:
    """The line after the last entry of the block that ``start`` opens."""
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][:1] in " \t-"):
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def record(path: str | Path, discrepancies: Sequence[Discrepancy]) -> None:
    """Append ``discrepancies`` to the ``discrepancies:`` block of the description at ``path``.

    Only that block is rewritten: the rest of the file keeps its own wording and order, so
    the change reads as a few added lines in review. A recorded discrepancy is what lets a
    later run without a network see that the description no longer holds.
    """
    if not discrepancies:
        return
    file = Path(path)
    lines = file.read_text(encoding="utf-8").splitlines()

    found_at = next((n for n, line in enumerate(lines) if _DISCREPANCIES.match(line)), None)
    if found_at is None:
        lines.append("discrepancies:")
        start, end = len(lines) - 1, len(lines)
    else:
        inline = lines[found_at].split(":", 1)[1].strip()
        if inline not in ("", "[]"):
            raise ValueError(f"{file}: discrepancies: expected a block or [], got {inline!r}")
        lines[found_at] = "discrepancies:"
        start, end = found_at, _section_end(lines, found_at)
    indent = _block_indent(lines, start, end)

    dumped = yaml.safe_dump(
        [entry.model_dump(mode="json", exclude_none=True) for entry in discrepancies],
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=10**6,
    )
    lines[end:end] = [indent + line for line in dumped.splitlines()]
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fetch(url: str) -> str:
    """Read ``url`` over HTTP. Anything but a 200 is a failure, never an empty page."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        body: bytes = response.read()
    return body.decode("utf-8")


def main(argv: Sequence[str] | None = None, *, fetch: Fetch = _fetch) -> int:
    """Check every description under ``--root`` and print what no longer holds.

    ``fetch`` is a parameter here for the same reason it is one in :func:`check`: the
    branch this function owns — printing versus writing — is then testable without a
    network.
    """
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("specs"))
    parser.add_argument(
        "--write",
        action="store_true",
        help="record what was found in the description files themselves",
    )
    args = parser.parse_args(argv)

    files = sorted(Path(args.root).rglob("*.yaml"))
    if not files:
        # Nothing checked is not everything confirmed — the same rule as an unreadable source.
        parser.error(f"{args.root}: no description to check (missing or empty root)")

    found_any = False
    for file in files:
        found = check(load(file), fetch=fetch)
        for entry in found:
            print(f"{file}: {entry.source_id}: {entry.kind.value}: {entry.detail}")
        if args.write:
            record(file, found)
        found_any = found_any or bool(found)
    if not found_any:
        print("every source still confirms its entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
