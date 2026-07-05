"""Skill loader (DT-10.2, Steward Wave 2).

FRAMEWORK layer (DC-1). Materializes a pinned skill version from the registry as
a READ-ONLY structure, after verifying the stored content against its stored
hash with the canonical function (Task 1).

Integrity policy is STRICT at load time (Wave 2 ruling): a hash mismatch raises
``SkillIntegrityError`` and NOTHING is materialized. This differs from replay's
flag-and-continue (I-8, Wave 6) — at runtime a corrupted skill must never reach
an agent.

The returned structure is recursively frozen: an agent that loads a skill cannot
mutate the structure, and there is no path from it back into the row (the loader
returns data only and holds no writer). The registry ROW remains the single
source of truth (G2 content-in-row); files, if any, are non-authoritative.
"""

from __future__ import annotations

import sqlite3
from types import MappingProxyType
from typing import Any

import yaml

from steward.storage.content_hash import compute_content_hash


class SkillIntegrityError(Exception):
    """Raised when a skill row's stored content does not match its stored hash."""


class SkillNotFoundError(Exception):
    """Raised when no skill row exists for the requested version id."""


def _freeze(value: Any) -> Any:
    """Recursively convert parsed content into an immutable structure.

    dicts -> MappingProxyType, lists -> tuples, leaves unchanged. Mutating the
    result raises TypeError, so a loaded skill cannot be edited in place.
    """
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def load_skill(registry_conn: sqlite3.Connection, skill_version_id: str) -> Any:
    """Fetch, hash-verify, parse, and return a read-only skill structure.

    - Fetches the row for ``skill_version_id`` from ``skill_versions``.
    - Recomputes the hash over the stored content via ``compute_content_hash``
      and compares to the stored ``content_hash``.
    - On match: parses the YAML content and returns it recursively frozen.
    - On mismatch: raises ``SkillIntegrityError`` (strict; nothing materialized).
    - Absent row: raises ``SkillNotFoundError``.

    Takes a live registry connection (not a path) so the caller controls the
    connection lifecycle, per the injected-path discipline (DT-8.5).
    """
    row = registry_conn.execute(
        "SELECT content, content_hash FROM skill_versions WHERE version_id = ?",
        (skill_version_id,),
    ).fetchone()
    if row is None:
        raise SkillNotFoundError(skill_version_id)

    content = row["content"] if isinstance(row, sqlite3.Row) else row[0]
    stored_hash = row["content_hash"] if isinstance(row, sqlite3.Row) else row[1]

    recomputed = compute_content_hash(content)
    if recomputed != stored_hash:
        raise SkillIntegrityError(
            f"hash mismatch for {skill_version_id}: "
            f"stored={stored_hash} recomputed={recomputed}"
        )

    parsed = yaml.safe_load(content)
    return _freeze(parsed)
