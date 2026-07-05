"""Proposal store (DT-11.3 / spec §8, Steward Wave 4).

FRAMEWORK layer. Own SQLite file on its own injected path. Wave 4 CREATES
PROPOSED rows only — the APPROVE executor (new version row + currency-pointer
flip + window timestamps) is Wave 5 and is deliberately absent here.

Anti-floating rule (spec §8.2): a proposal with EMPTY evidence_refs is illegal by
construction — insert_proposed rejects it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parent / "proposals_schema.sql"

# Statuses that block a new proposal against the same skill (DT-12.4 guard).
OPEN_STATUSES = ("PROPOSED", "APPROVED", "IN_WINDOW")


class EmptyEvidenceError(ValueError):
    """A proposal with no cited evidence is illegal by construction (§8.2)."""


class ProposalStore:
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

    # ─── create PROPOSED (Wave 4) ────────────────────────────────────────

    def insert_proposed(
        self,
        *,
        proposal_id: str,
        created_at: str,
        author: str,
        application_id: str,
        evidence_refs: list[str],
        target_skill: str,
        base_version_id: str,
        proposed_change: dict[str, Any],
        rationale: str,
        complexity_tag: str,
    ) -> None:
        """Insert a PROPOSED proposal. Rejects empty evidence_refs (§8.2)."""
        if not evidence_refs:
            raise EmptyEvidenceError(
                "proposal has empty evidence_refs — cite-never-assert (§8.2)"
            )
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO proposals (
                    proposal_id, created_at, author, application_id,
                    evidence_refs, target_skill, base_version_id,
                    proposed_change, rationale, complexity_tag, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPOSED')
                """,
                (
                    proposal_id, created_at, author, application_id,
                    json.dumps(evidence_refs), target_skill, base_version_id,
                    json.dumps(proposed_change, sort_keys=True), rationale, complexity_tag,
                ),
            )

    # ─── reads ───────────────────────────────────────────────────────────

    def open_proposal_for(self, target_skill: str) -> dict[str, Any] | None:
        """Return an existing PROPOSED/APPROVED/IN_WINDOW proposal for the skill,
        or None. Backs the one-proposal-at-a-time guard (DT-12.4)."""
        placeholders = ",".join("?" for _ in OPEN_STATUSES)
        with self.connection() as conn:
            row = conn.execute(
                f"SELECT * FROM proposals WHERE target_skill=? "
                f"AND status IN ({placeholders}) LIMIT 1",
                (target_skill, *OPEN_STATUSES),
            ).fetchone()
        return dict(row) if row is not None else None

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_open(self) -> list[dict[str, Any]]:
        """Proposals in PROPOSED/APPROVED/IN_WINDOW (for `gate list`)."""
        placeholders = ",".join("?" for _ in OPEN_STATUSES)
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE status IN ({placeholders}) "
                f"ORDER BY created_at, proposal_id",
                OPEN_STATUSES,
            ).fetchall()
        return [dict(r) for r in rows]

    def set_status_with_decision(
        self,
        proposal_id: str,
        *,
        status: str,
        decided_at: str | None,
        decided_by: str | None,
        decision_note: str | None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Record a gate decision (status + note + decided_by/at). Used by reject
        (Task 4) and — inside the fork transaction — by approve (Task 5). When a
        connection is supplied the write joins that transaction (atomicity)."""
        sql = """
            UPDATE proposals
            SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?
            WHERE proposal_id = ?
        """
        args = (status, decided_at, decided_by, decision_note, proposal_id)
        if conn is not None:
            conn.execute(sql, args)
        else:
            with self.connection() as own:
                own.execute(sql, args)

    def set_in_window(
        self,
        proposal_id: str,
        *,
        new_version_id: str,
        window_opened_at: str,
        window_closes_at: str,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Move an APPROVED proposal to IN_WINDOW, stamping the window + the new
        version id. evaluation stays NULL (v1 stub). Optionally in a transaction."""
        sql = """
            UPDATE proposals
            SET status = 'IN_WINDOW', new_version_id = ?,
                window_opened_at = ?, window_closes_at = ?
            WHERE proposal_id = ?
        """
        args = (new_version_id, window_opened_at, window_closes_at, proposal_id)
        if conn is not None:
            conn.execute(sql, args)
        else:
            with self.connection() as own:
                own.execute(sql, args)

    def record_first_view(
        self, proposal_id: str, *, session: str, viewed_at: str
    ) -> None:
        """Stamp first-viewed session+timestamp ONCE (idempotent — a later view
        never overwrites the first). Backs the cooling-off ritual."""
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE proposals
                SET first_viewed_at = COALESCE(first_viewed_at, ?),
                    first_viewed_session = COALESCE(first_viewed_session, ?)
                WHERE proposal_id = ?
                """,
                (viewed_at, session, proposal_id),
            )
