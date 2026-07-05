"""Canonical content-hash — the sole hashing authority (Task 1, Steward Wave 2).

FRAMEWORK layer (DC-1). G2's tamper-evidence property rests on the stored hash
being a faithful digest of the stored content at the moment it was written. So
ONE function pins the algorithm (SHA-256) and the serialization (UTF-8 of the
content string). Every producer and every consumer must call THIS function:
- the skill-version writer computes the stored hash with it at insert time;
- the loader (DT-10.2) recomputes with it and compares;
- replay (DT-13.2, Wave 6) verifies with it.

Hashing a serialized string is content-agnostic, so this lives in the storage
layer without violating its neutrality — it never interprets the content.
"""

from __future__ import annotations

import hashlib


def compute_content_hash(content: str) -> str:
    """Return the SHA-256 hex digest of ``content.encode("utf-8")``."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
