"""Checking recorded sources against the vendor documentation.

This is the only module of the project allowed to reach the network, and it reaches it
through one injected function: :func:`check` takes ``fetch`` as a parameter, so nothing
below this module — and no test — needs a network at all.
"""

from __future__ import annotations

import gzip
import ipaddress
import re
import socket
import zlib
from argparse import ArgumentParser
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from http.client import HTTPException, HTTPMessage
from pathlib import Path
from typing import IO
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
# (HTTPException, which is not an OSError), a section that is no longer there.
# A failure outside this set is a defect of ours and must not be filed as a
# discrepancy against the vendor. A body we cannot decode is one of those: it says
# we read the answer wrong, not that the vendor's page changed, and filing it would
# quietly make the description stale over a fault of our own.
#
# The line is drawn by what failed, not by the type: being refused the page — by the
# server, the connection, or our own rule about where we may go — is the other side
# saying no, and is a discrepancy. Holding the page and being unable to read it is our
# limit, and must surface.
_UNREACHABLE = (OSError, HTTPException, AnchorError)


class UndecodableBody(Exception):
    """A body arrived whole in an encoding we cannot read.

    Deliberately outside :data:`_UNREACHABLE`, next to ``UnicodeDecodeError``: it says
    the run needs a decoder it does not have, not that the vendor's page changed.
    """


def markdown_url(source: Source) -> str:
    """The markdown twin of the documented page: the hash is taken from that, never from HTML.

    An HTML page changes with its styling; the markdown one changes with its content.
    """
    return source.markdown_url or f"{source.url}.md"


class CheckFailed(RuntimeError):
    """A source failed in a way that is a defect of ours, not a statement about the vendor.

    It carries what the run did establish, so a failure on one source neither hides the
    defect nor throws away the discrepancies the other sources already showed.
    """

    def __init__(self, found: list[Discrepancy], failures: list[tuple[str, BaseException]]) -> None:
        listed = "; ".join(f"{source_id}: {type(e).__name__}: {e}" for source_id, e in failures)
        super().__init__(f"{len(failures)} source(s) failed unexpectedly: {listed}")
        self.found = found
        self.failures = failures


def check(spec: EnvSpec, *, fetch: Fetch, today: date | None = None) -> list[Discrepancy]:
    """Re-read every source of ``spec`` and report the ones that no longer confirm it.

    A section whose hash moved is ``changed`` and carries both hashes. A page that could
    not be read, or that no longer has the anchored section, is ``unreachable`` — an
    unreadable source is a discrepancy, never a confirmation that the entry still holds.

    Any other failure is a defect of ours: the remaining sources are still checked, and
    :class:`CheckFailed` is raised at the end carrying both the defects and the
    discrepancies found, so neither is lost.
    """
    when = today or date.today()
    found: list[Discrepancy] = []
    failures: list[tuple[str, BaseException]] = []
    for source in spec.sources:
        if source.retrieved_from == "shipped":
            # It came with the environment, not from a page: there is nothing to re-fetch,
            # and it changes when the environment is reinstalled, not between runs.
            continue
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
        # Everything else is a defect of ours; it is re-raised below, never swallowed.
        except Exception as error:
            failures.append((source.id, error))
            continue
        if fresh != source.sha256:
            found.append(
                Discrepancy(
                    source_id=source.id,
                    kind=DiscrepancyKind.CHANGED,
                    detail=f"{when}: {url}: recorded {source.sha256}, now {fresh}",
                )
            )
    if failures:
        raise CheckFailed(found, failures)
    return found


def confirmed_sources(
    spec: EnvSpec, found: Sequence[Discrepancy], failed: Iterable[str] = ()
) -> set[str]:
    """The sources this run read and found unchanged.

    A source the run never reached is not confirmed by the run's silence — that is the
    same rule that makes an unreadable page a discrepancy.
    """
    unconfirmed = {entry.source_id for entry in found} | set(failed)
    return {source.id for source in spec.sources} - unconfirmed


_DISCREPANCIES = re.compile(r"^discrepancies:(.*)$")
_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}: ")


def _identity(entry: dict[str, object]) -> tuple[object, object, str]:
    """What makes two records the same finding: everything but the day it was found."""
    detail = entry.get("detail")
    return (
        entry.get("source_id"),
        entry.get("kind"),
        _DATED.sub("", detail) if isinstance(detail, str) else "",
    )


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


def record(
    path: str | Path,
    discrepancies: Sequence[Discrepancy],
    *,
    confirmed: Iterable[str] = (),
) -> None:
    """Write ``discrepancies`` into the ``discrepancies:`` block of the description at ``path``.

    Only that block is rewritten: the rest of the file keeps its own wording and order, so
    the change reads as a few added lines in review. A recorded discrepancy is what lets a
    later run without a network see that the description no longer holds.

    The same finding is not filed twice — records match on everything but the day they
    were found — and records of a source named in ``confirmed`` are dropped, because that
    source has just been read and found unchanged. Nothing else is dropped: a run that
    could not reach a source has learned nothing about it. A run that changes nothing
    leaves the file untouched.
    """
    file = Path(path)
    lines = file.read_text(encoding="utf-8").splitlines()

    found_at = next((n for n, line in enumerate(lines) if _DISCREPANCIES.match(line)), None)
    if found_at is None:
        lines.append("discrepancies:")
        start, end = len(lines) - 1, len(lines)
        existing: list[dict[str, object]] = []
    else:
        inline = lines[found_at].split(":", 1)[1].strip()
        if inline not in ("", "[]"):
            raise ValueError(f"{file}: discrepancies: expected a block or [], got {inline!r}")
        start, end = found_at, _section_end(lines, found_at)
        existing = yaml.safe_load("\n".join(lines[start + 1 : end])) or []

    kept = [entry for entry in existing if entry.get("source_id") not in set(confirmed)]
    known = {_identity(entry) for entry in kept}
    for entry in discrepancies:
        fresh = entry.model_dump(mode="json", exclude_none=True)
        if _identity(fresh) not in known:
            known.add(_identity(fresh))
            kept.append(fresh)
    if kept == existing:
        return

    indent = _block_indent(lines, start, end)
    if kept:
        dumped = yaml.safe_dump(
            kept,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            width=10**6,
        )
        block = ["discrepancies:"] + [indent + line for line in dumped.splitlines()]
    else:
        block = ["discrepancies: []"]
    lines[start:end] = block
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def decode_body(body: bytes, content_encoding: str | None) -> str:
    """Turn a response body into text, honouring the encoding the server declared.

    A server may compress an answer we did not ask to have compressed, and the same URL
    may come back compressed on one request and plain on the next. Decoding the bytes
    without reading ``Content-Encoding`` turns that into a decode failure, and a decode
    failure must never be filed as a discrepancy against the vendor — a freshness run
    would then make the description stale over nothing. The header decides, never the
    bytes.
    """
    declared = (content_encoding or "identity").strip().lower()
    if declared in ("gzip", "x-gzip"):
        try:
            body = gzip.decompress(body)
        # A body that stops mid-stream is the same event as a response that stops
        # mid-answer, and must be classed with it rather than end the run.
        except (EOFError, zlib.error) as error:
            raise OSError(f"broken gzip body: {type(error).__name__}: {error}") from error
    elif declared not in ("identity", ""):
        raise UndecodableBody(f"unsupported Content-Encoding {declared!r}")
    return body.decode("utf-8")


def _addresses(host: str, port: int) -> list[str]:
    """Every address ``host`` resolves to. Its own function so a test can stand in for DNS."""
    return [str(info[4][0]) for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)]


def guard_url(url: str) -> None:
    """Refuse to fetch anything but ``https`` to a public address.

    The address comes out of a description file, and description files arrive as pull
    requests written by a language model against repositories we do not own. An address
    in data decides where our process connects, so ``file://`` and anything resolving to
    the loopback, a private network or a link-local range is refused — and refused as an
    :class:`OSError`, so the run reports the source as unreachable instead of dying.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise OSError(f"refusing {url!r}: only https is fetched, not {parts.scheme or 'no'} scheme")
    host = parts.hostname
    if not host:
        raise OSError(f"refusing {url!r}: no host")
    # The address is resolved here and connected to a moment later, so a name that
    # answers differently between the two calls still gets through. Closing that needs
    # a connection we pin to the address we checked; this refuses the honest cases.
    for found in _addresses(host, parts.port or 443):
        address = ipaddress.ip_address(found)
        if not address.is_global:
            raise OSError(f"refusing {url!r}: {address} is not a public address")


class _GuardedRedirects(HTTPRedirectHandler):
    """Follow redirects only while every hop still passes :func:`guard_url`.

    A trusted first address means nothing if the answer is ``302 -> http://127.0.0.1``.
    """

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        guard_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = build_opener(_GuardedRedirects())


def _fetch(url: str) -> str:
    """Read ``url`` over HTTP. Anything but a 200 is a failure, never an empty page."""
    guard_url(url)
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, identity"},
    )
    with _opener.open(request, timeout=30) as response:
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        body: bytes = response.read()
        declared: str | None = response.headers.get("Content-Encoding")
    return decode_body(body, declared)


def _report(file: Path, found: Sequence[Discrepancy], confirmed: set[str], *, write: bool) -> None:
    """Print every discrepancy of one description, and record it when asked to."""
    for entry in found:
        print(f"{file}: {entry.source_id}: {entry.kind.value}: {entry.detail}")
    if write:
        record(file, found, confirmed=confirmed)


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
        spec = load(file)
        try:
            found = check(spec, fetch=fetch)
        except CheckFailed as failure:
            # Report and record what this file did show, then let the defect out.
            failed = [source_id for source_id, _ in failure.failures]
            _report(
                file,
                failure.found,
                confirmed_sources(spec, failure.found, failed),
                write=args.write,
            )
            raise
        _report(file, found, confirmed_sources(spec, found), write=args.write)
        found_any = found_any or bool(found)
    if not found_any:
        print("every source still confirms its entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
