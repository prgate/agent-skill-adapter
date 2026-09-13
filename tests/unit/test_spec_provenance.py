"""Unit tests for the provenance script. No network access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import spec_provenance  # type: ignore[import-not-found]  # noqa: E402

SAME_TEXT_A = """
<html><body>
<h2 id="name-field">name field</h2>
<p>Must be <code>1-64</code> characters.</p>
<h2 id="next">Next</h2>
<p>Ignored.</p>
</body></html>
"""

SAME_TEXT_B = """
<html><body>
<h2 id="name-field"><span class="x">name</span>
   field</h2>
<div><p>Must be    <code>1-64</code>
characters.</p></div>
<h2 id="next">Next</h2><p>Ignored.</p>
</body></html>
"""

CHANGED_TEXT = SAME_TEXT_A.replace("1-64", "1-128")


def test_same_text_different_markup_hashes_equal() -> None:
    a = spec_provenance.extract_section(SAME_TEXT_A, "#name-field")
    b = spec_provenance.extract_section(SAME_TEXT_B, "#name-field")
    assert a is not None and b is not None
    assert spec_provenance.section_hash(a) == spec_provenance.section_hash(b)


def test_changed_text_changes_hash() -> None:
    a = spec_provenance.extract_section(SAME_TEXT_A, "#name-field")
    c = spec_provenance.extract_section(CHANGED_TEXT, "#name-field")
    assert a is not None and c is not None
    assert spec_provenance.section_hash(a) != spec_provenance.section_hash(c)


def test_section_stops_at_next_heading_of_same_level() -> None:
    section = spec_provenance.extract_section(SAME_TEXT_A, "#name-field")
    assert section is not None
    assert "Ignored." not in section


def test_missing_anchor_returns_none() -> None:
    assert spec_provenance.extract_section(SAME_TEXT_A, "#absent") is None


def test_hash_carries_prefix() -> None:
    assert spec_provenance.section_hash("text").startswith("sha256:")
