"""Tests for the freshness seam: a fetched page -> a discrepancy, and back into the file.

``fetch`` is always a stub here: the suite makes no network call.
"""

from __future__ import annotations

import gzip
from datetime import date
from email.message import Message
from http.client import HTTPMessage, IncompleteRead
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from agent_skill_adapter.envspec import freshness
from agent_skill_adapter.envspec.freshness import (
    CheckFailed,
    UndecodableBody,
    _fetch,
    check,
    confirmed_sources,
    decode_body,
    guard_url,
    main,
    record,
)
from agent_skill_adapter.envspec.loader import is_stale, load
from agent_skill_adapter.envspec.model import DiscrepancyKind
from agent_skill_adapter.envspec.normalize import digest, section_text

TODAY = date(2026, 9, 14)
ANCHOR = "Frontmatter fields"

PAGE = """# Skills

## Frontmatter fields

- `name` names the skill.
- `description` says when to use it.

## Something else

Not part of the section.
"""


SECOND_URL = "https://example.invalid/docs/hooks"


def write_spec(root: Path, sha256: str, *, second_source: bool = False) -> Path:
    """Write a description whose sources record ``sha256`` for the page section."""

    def source(source_id: str, url: str) -> list[str]:
        return [
            f"  - id: {source_id}",
            f"    url: {url}",
            f'    anchor: "{ANCHOR}"',
            f'    sha256: "{sha256}"',
            f"    checked_at: {TODAY}",
            '    environment_version: "2.1.270"',
        ]

    sources = source("skills-frontmatter", "https://example.invalid/docs/skills")
    if second_source:
        sources += source("hooks-config", SECOND_URL)
    text = "\n".join(
        [
            "schema_version: 1",
            "vendor: anthropic",
            "environment: claude-code",
            'version_range: ">=2.1.0,<2.2.0"',
            f"checked_at: {TODAY}",
            "normalization: v1",
            "sources:",
            *sources,
            "capabilities:",
            "  - id: skill.frontmatter.name",
            "    kind: skill-field",
            "    support: supported",
            "    source_id: skills-frontmatter",
            "discrepancies: []",
            "",
        ]
    )
    path = root / "spec.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def recorded_sha() -> str:
    """The hash a freshness run would have written when the page still read like ``PAGE``."""
    return digest(section_text(PAGE, ANCHOR))


def test_changed_section_text_reports_both_hashes(tmp_path: Path) -> None:
    spec = load(write_spec(tmp_path, recorded_sha()))
    edited = PAGE.replace("names the skill", "names the skill, lowercase only")

    found = check(spec, fetch=lambda _url: edited, today=TODAY)

    assert [d.kind for d in found] == [DiscrepancyKind.CHANGED]
    detail = found[0].detail or ""
    assert recorded_sha() in detail
    assert digest(section_text(edited, ANCHOR)) in detail
    assert str(TODAY) in detail


def test_formatting_only_change_is_not_a_discrepancy(tmp_path: Path) -> None:
    """Normalization is what makes the hash mean content: styling alone must not trip it."""
    spec = load(write_spec(tmp_path, recorded_sha()))
    restyled = PAGE.replace("\n", "\r\n").replace("names the skill.", "names the skill.   ")
    restyled = restyled.replace("## Frontmatter fields", "## Frontmatter fields\r\n\r\n")

    assert check(spec, fetch=lambda _url: restyled, today=TODAY) == []

    reworded = PAGE.replace("names the skill", "is the skill identifier")
    assert len(check(spec, fetch=lambda _url: reworded, today=TODAY)) == 1


def test_unreadable_source_is_unreachable_not_silence(tmp_path: Path) -> None:
    spec = load(write_spec(tmp_path, recorded_sha()))
    failures: list[Exception] = [
        OSError("network is unreachable"),
        HTTPError("https://example.invalid/docs/skills.md", 404, "Not Found", Message(), None),
        # A cut-off answer is the server's failure, and HTTPException is outside OSError.
        IncompleteRead(b"## Frontmatter fi"),
    ]

    for failure in failures:

        def fetch(_url: str, failure: Exception = failure) -> str:
            raise failure

        found = check(spec, fetch=fetch, today=TODAY)
        assert [d.kind for d in found] == [DiscrepancyKind.UNREACHABLE], failure


def test_vanished_anchor_is_unreachable(tmp_path: Path) -> None:
    """The page still loads, but the section it was quoted from is gone."""
    spec = load(write_spec(tmp_path, recorded_sha()))
    renamed = PAGE.replace("## Frontmatter fields", "## Skill metadata")

    found = check(spec, fetch=lambda _url: renamed, today=TODAY)

    assert [d.kind for d in found] == [DiscrepancyKind.UNREACHABLE]
    assert ANCHOR in (found[0].detail or "")


def test_recorded_discrepancy_survives_a_reload_and_makes_the_spec_stale(tmp_path: Path) -> None:
    """A discrepancy lives in the description file, so a run without a network still sees it."""
    path = write_spec(tmp_path, recorded_sha())
    spec = load(path)
    edited = PAGE.replace("says when to use it", "says when to use it (one sentence)")
    found = check(spec, fetch=lambda _url: edited, today=TODAY)

    record(path, found)

    reloaded = load(path)
    assert [(d.source_id, d.kind) for d in reloaded.discrepancies] == [
        (d.source_id, d.kind) for d in found
    ]
    assert reloaded.discrepancies[0].detail == found[0].detail
    assert is_stale(reloaded, TODAY)
    assert "capabilities:" in path.read_text(encoding="utf-8"), "the rest of the file is kept"


def test_a_second_run_appends_next_to_the_first(tmp_path: Path) -> None:
    """The block already holds an entry: the new one is added to it, not written over it."""
    path = write_spec(tmp_path, recorded_sha())
    reworded = PAGE.replace("says when to use it", "says when it applies")
    record(path, check(load(path), fetch=lambda _url: reworded, today=TODAY))

    def unreadable(_url: str) -> str:
        raise OSError("network is unreachable")

    record(path, check(load(path), fetch=unreadable, today=TODAY))

    reloaded = load(path)
    assert [d.kind for d in reloaded.discrepancies] == [
        DiscrepancyKind.CHANGED,
        DiscrepancyKind.UNREACHABLE,
    ]


def test_a_defect_of_ours_is_not_filed_as_a_vendor_discrepancy(tmp_path: Path) -> None:
    """Only a failure to read the page is ``unreachable``; a broken ``fetch`` must surface."""
    spec = load(write_spec(tmp_path, recorded_sha()))

    def broken(_url: str) -> str:
        raise TypeError("a defect in our own code, not the vendor's server")

    with pytest.raises(CheckFailed) as failed:
        check(spec, fetch=broken, today=TODAY)
    assert [(sid, type(e)) for sid, e in failed.value.failures] == [
        ("skills-frontmatter", TypeError)
    ]
    assert failed.value.found == [], "a defect of ours is never filed against the vendor"

    def undecodable(_url: str) -> str:
        raise UnicodeDecodeError("utf-8", b"\x1f\x8b", 1, 2, "invalid start byte")

    with pytest.raises(CheckFailed) as failed:
        check(spec, fetch=undecodable, today=TODAY)
    assert [type(e) for _, e in failed.value.failures] == [UnicodeDecodeError]


def test_appended_entries_take_the_indent_of_the_existing_block(tmp_path: Path) -> None:
    """A block written at column zero is valid YAML: appending must not break the file."""
    path = write_spec(tmp_path, recorded_sha())
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "discrepancies: []",
            "discrepancies:\n- source_id: skills-frontmatter\n  kind: unreachable\n",
        ),
        encoding="utf-8",
    )
    reworded = PAGE.replace("names the skill", "identifies the skill")

    record(path, check(load(path), fetch=lambda _url: reworded, today=TODAY))

    assert [d.kind for d in load(path).discrepancies] == [
        DiscrepancyKind.UNREACHABLE,
        DiscrepancyKind.CHANGED,
    ]


def test_main_writes_into_the_file_only_with_write(tmp_path: Path) -> None:
    path = write_spec(tmp_path, recorded_sha())
    reworded = PAGE.replace("names the skill", "identifies the skill")

    assert main(["--root", str(tmp_path)], fetch=lambda _url: reworded) == 0
    assert load(path).discrepancies == [], "a plain run only reports"

    assert main(["--root", str(tmp_path), "--write"], fetch=lambda _url: reworded) == 0
    assert [d.kind for d in load(path).discrepancies] == [DiscrepancyKind.CHANGED]


def test_main_refuses_a_root_with_nothing_to_check(tmp_path: Path) -> None:
    """Nothing checked is not everything confirmed — a mistyped root must not read as green."""
    with pytest.raises(SystemExit) as exit_code:
        main(["--root", str(tmp_path / "typo")], fetch=lambda _url: PAGE)

    assert exit_code.value.code != 0


def test_the_same_answer_decodes_the_same_way_compressed_or_not(tmp_path: Path) -> None:
    """The vendor may gzip an answer we did not ask to compress — the header decides."""
    plain = PAGE.encode("utf-8")

    assert decode_body(plain, None) == PAGE
    assert decode_body(plain, "identity") == PAGE
    assert decode_body(gzip.compress(plain), "gzip") == PAGE
    assert decode_body(gzip.compress(plain), "GZIP") == PAGE, "header values are case-insensitive"

    with pytest.raises(UndecodableBody):
        decode_body(plain, "br")

    spec = load(write_spec(tmp_path, recorded_sha()))
    with pytest.raises(CheckFailed):
        check(spec, fetch=lambda _url: decode_body(plain, "br"), today=TODAY)


def test_one_failing_source_does_not_discard_the_others(tmp_path: Path) -> None:
    """A defect on the second source must not erase what the first one showed."""
    path = write_spec(tmp_path, recorded_sha(), second_source=True)
    reworded = PAGE.replace("names the skill", "identifies the skill")

    def fetch(url: str) -> str:
        if url.startswith(SECOND_URL):
            raise TypeError("a defect in our own code")
        return reworded

    with pytest.raises(CheckFailed) as failed:
        check(load(path), fetch=fetch, today=TODAY)

    assert [d.source_id for d in failed.value.found] == ["skills-frontmatter"]

    with pytest.raises(CheckFailed):
        main(["--root", str(tmp_path), "--write"], fetch=fetch)
    assert [d.source_id for d in load(path).discrepancies] == ["skills-frontmatter"]


def test_a_truncated_gzip_body_is_a_transport_failure(tmp_path: Path) -> None:
    """A body that stops mid-stream is the server's failure, not a crash of the run."""
    cut = gzip.compress(PAGE.encode("utf-8"))[:12]

    with pytest.raises(OSError):
        decode_body(cut, "gzip")

    spec = load(write_spec(tmp_path, recorded_sha()))
    found = check(spec, fetch=lambda _url: decode_body(cut, "gzip"), today=TODAY)
    assert [d.kind for d in found] == [DiscrepancyKind.UNREACHABLE]


class _Response:
    """The part of an ``http.client`` response that ``_fetch`` uses."""

    def __init__(self, body: bytes, headers: dict[str, str], status: int = 200) -> None:
        self.status = status
        self.headers = Message()
        for name, value in headers.items():
            self.headers[name] = value
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _Opener:
    """Stands in for the urllib opener: hands back one prepared answer, records the request."""

    def __init__(self, response: _Response) -> None:
        self.response = response
        self.sent: list[Request] = []

    def open(self, request: Request, timeout: float = 0) -> _Response:
        self.sent.append(request)
        return self.response


def public_dns(monkeypatch: pytest.MonkeyPatch, address: str = "93.184.216.34") -> None:
    """Resolve every host to ``address`` — the suite never asks a real resolver."""
    monkeypatch.setattr(freshness, "_addresses", lambda _host, _port: [address])


def test_fetch_asks_for_an_encoding_and_honours_the_one_it_gets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wiring under test is the header: what we ask for, and what we do with the answer."""
    public_dns(monkeypatch)
    opener = _Opener(_Response(gzip.compress(PAGE.encode("utf-8")), {"Content-Encoding": "gzip"}))
    monkeypatch.setattr(freshness, "_opener", opener)

    assert _fetch("https://example.invalid/docs/skills.md") == PAGE
    assert opener.sent[0].get_header("Accept-encoding") == "gzip, identity"

    monkeypatch.setattr(freshness, "_opener", _Opener(_Response(b"nope", {}, status=503)))
    with pytest.raises(OSError, match="503"):
        _fetch("https://example.invalid/docs/skills.md")


def test_an_address_out_of_a_description_cannot_send_us_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A description is data: it must not be able to point our process at a private host."""
    public_dns(monkeypatch)
    for refused in ("http://example.invalid/docs.md", "file:///etc/passwd"):
        with pytest.raises(OSError, match="only https"):
            guard_url(refused)

    for address in ("127.0.0.1", "10.0.0.7", "169.254.169.254", "::1"):
        monkeypatch.setattr(freshness, "_addresses", lambda _h, _p, a=address: [a])
        with pytest.raises(OSError, match="not a public address"):
            guard_url("https://internal.invalid/docs.md")

    public_dns(monkeypatch)
    guard_url("https://example.invalid/docs.md")


def test_fetch_refuses_the_address_before_it_opens_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard is wired into the fetch, not merely available next to it."""
    opener = _Opener(_Response(PAGE.encode("utf-8"), {}))
    monkeypatch.setattr(freshness, "_opener", opener)

    public_dns(monkeypatch)
    with pytest.raises(OSError, match="only https"):
        _fetch("http://example.invalid/docs.md")

    monkeypatch.setattr(freshness, "_addresses", lambda _host, _port: ["127.0.0.1"])
    with pytest.raises(OSError, match="not a public address"):
        _fetch("https://internal.invalid/docs.md")

    assert opener.sent == [], "a refused address is never opened"


def test_a_redirect_is_guarded_at_every_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A trusted first address proves nothing: the hop it answers with is checked too."""
    monkeypatch.setattr(freshness, "_addresses", lambda _host, _port: ["127.0.0.1"])
    request = Request("https://example.invalid/docs.md")

    with pytest.raises(OSError, match="not a public address"):
        freshness._GuardedRedirects().redirect_request(
            request,
            BytesIO(b""),
            302,
            "Found",
            HTTPMessage(),
            "https://internal.invalid/docs.md",
        )


def test_the_same_finding_is_not_filed_twice(tmp_path: Path) -> None:
    """Three runs against one broken page must not leave three identical records."""
    path = write_spec(tmp_path, recorded_sha())

    def unreachable(_url: str) -> str:
        raise OSError("HTTP 503")

    for day in (TODAY, date(2026, 9, 15), date(2026, 9, 16)):
        record(path, check(load(path), fetch=unreachable, today=day))

    assert len(load(path).discrepancies) == 1, "the date alone does not make it a new finding"


def test_a_run_clears_only_the_sources_it_actually_read(tmp_path: Path) -> None:
    """A source read and found unchanged is cleared; one the run never reached is kept."""
    path = write_spec(tmp_path, recorded_sha(), second_source=True)

    def nothing_answers(_url: str) -> str:
        raise OSError("HTTP 503")

    spec = load(path)
    record(path, check(spec, fetch=nothing_answers, today=TODAY))
    assert len(load(path).discrepancies) == 2

    def only_the_second_answers(url: str) -> str:
        if url.startswith(SECOND_URL):
            raise OSError("HTTP 503")
        return PAGE

    found = check(spec, fetch=only_the_second_answers, today=TODAY)
    record(path, found, confirmed=confirmed_sources(spec, found))

    assert [d.source_id for d in load(path).discrepancies] == ["hooks-config"]
