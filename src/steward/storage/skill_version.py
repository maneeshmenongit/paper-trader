"""Skill-version registry (DT-10.1, Steward Wave 1).

FRAMEWORK layer (DC-1). Authored from reconcile G2 and spec §6.

One row per version of one agent's skill; the anchor for the Store A pin (§5.2),
the proposal fork chain (§8.2), and the officer's comparison baseline (§4.3).

Two tables in ONE file on its OWN connection path (DT-10.1: not co-located with
Store A):
- ``skill_versions`` — append-only. Content lives IN the row; version rows are
  INSERT-only and backed by no-mutation triggers.
- ``skill_currency`` — the currency pointer, THE ONE MUTABLE CELL in the
  subsystem. ``set_current_version`` upserts it; a gated fork (DT-12.1, Wave 5)
  flips it atomically with a version insert. That atomic transaction is NOT this
  task; here the insert and the pointer flip are separate primitives.

Content hashing / hash verification (first consumer: replay) is not computed
here — callers pass an already-computed ``content_hash``. The invocation pin in
Store A is a logical, app-layer-verified reference to ``version_id``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "skill_version_schema.sql"


class SkillVersionRegistry:
    """Connection/init helper + writer for the skill-version registry file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA_PATH.read_text())

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ─── skill_versions: append-only writer ──────────────────────────────

    def insert_skill_version(
        self,
        *,
        version_id: str,
        application_id: str,
        agent_name: str,
        skill_name: str,
        version_ordinal: int,
        content_hash: str,
        content: str,
        parent_version_id: str | None,
        created_by_proposal_id: str | None,
        origin: str,
        grounding_refs: str | None,
        validation_status: str,
        validation_updated_at: str | None,
        validation_evidence_refs: str | None,
        created_at: str,
    ) -> None:
        """Append one skill version. Content and refs arrive already serialized.

        ``parent_version_id`` / ``created_by_proposal_id`` are null only for
        ``@v1`` (``origin: initial-authoring``) — the anti-floating rule is
        enforced at the app layer, not here. ``content_hash`` is precomputed.
        """
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO skill_versions (
                    version_id, application_id, agent_name, skill_name,
                    version_ordinal, content_hash, content,
                    parent_version_id, created_by_proposal_id,
                    origin, grounding_refs,
                    validation_status, validation_updated_at,
                    validation_evidence_refs, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    application_id,
                    agent_name,
                    skill_name,
                    version_ordinal,
                    content_hash,
                    content,
                    parent_version_id,
                    created_by_proposal_id,
                    origin,
                    grounding_refs,
                    validation_status,
                    validation_updated_at,
                    validation_evidence_refs,
                    created_at,
                ),
            )

    # ─── skill_currency: the one mutable cell ────────────────────────────

    def set_current_version(
        self,
        *,
        application_id: str,
        agent_name: str,
        skill_name: str,
        current_version_id: str,
        updated_at: str,
    ) -> None:
        """Point (application, agent, skill) at a version. Upsert — the pointer
        is the one cell in the subsystem that legitimately moves."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO skill_currency (
                    application_id, agent_name, skill_name,
                    current_version_id, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (application_id, agent_name, skill_name)
                DO UPDATE SET
                    current_version_id = excluded.current_version_id,
                    updated_at = excluded.updated_at
                """,
                (
                    application_id,
                    agent_name,
                    skill_name,
                    current_version_id,
                    updated_at,
                ),
            )

    def get_current_version_id(
        self,
        *,
        application_id: str,
        agent_name: str,
        skill_name: str,
    ) -> str | None:
        """Return the live version_id for (application, agent, skill), or None."""
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT current_version_id FROM skill_currency
                WHERE application_id = ? AND agent_name = ? AND skill_name = ?
                """,
                (application_id, agent_name, skill_name),
            ).fetchone()
        return row["current_version_id"] if row is not None else None
