"""Canonical content-hash tests (Task 1, Steward Wave 2)."""

from __future__ import annotations

import hashlib

from steward.storage.content_hash import compute_content_hash


def test_matches_sha256_utf8():
    content = "mandate: produce views\nrules:\n  - R1"
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert compute_content_hash(content) == expected


def test_deterministic():
    assert compute_content_hash("x") == compute_content_hash("x")


def test_distinct_content_distinct_hash():
    assert compute_content_hash("a") != compute_content_hash("b")


def test_hex_digest_shape():
    h = compute_content_hash("anything")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_unicode_content():
    # Non-ASCII must hash via its UTF-8 encoding without error.
    content = "confidence ≥ 0.60 — View"
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert compute_content_hash(content) == expected
