"""Store B — correction ledger store (DT-8.2, Steward Wave 1).

FRAMEWORK layer (DC-1). Authored from STEWARD_FRAMEWORK_SPEC_001.md §5.3.

The ledger is the membrane between the two loops (§2.3): the observer's only
output and the proposer's only input. It OBSERVES and never PRESCRIBES — the
absence of any `action`/`recommendation`/`severity` field is deliberate.

Store B is append-only. This module exposes ONLY insert_ledger_entry and no
path to UPDATE or DELETE any row; the schema additionally installs no-mutation
triggers (§5.4). The file is physically separate from Store A, the app db, and
the checkpointer — the caller injects its path; this module never hardcodes it.

Write-authority narrowing (officer-only INSERT + rejection) is Wave 4
(DT-11.4), not this task; the writer here is a plain insert-only surface.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "store_b_schema.sql"


class StoreB:
    """Connection/init helper + INSERT-only writer for the ledger file.

    Creates the SQLite file if absent, applies the schema, and — on every
    connection — sets ``PRAGMA foreign_keys=ON`` and ``PRAGMA journal_mode=WAL``
    (WAL so slow-loop / replay reads never block fast-loop ledger writes).
    """

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

    # ─── INSERT-only writer surface ──────────────────────────────────────
    # One method. No update/delete anywhere in this module.

    def insert_ledger_entry(
        self,
        *,
        entry_id: str,
        cycle_id: str,
        invocation_id: str | None,
        observed_at: str,
        author: str,
        subject: str,
        observation_type: str,
        evidence: str,
    ) -> None:
        """Append one ledger entry. Fields arrive already serialized.

        ``cycle_id`` and ``invocation_id`` are LOGICAL references to Store A
        (cross-file, verified at the app layer, not DB FKs). ``invocation_id``
        is the only nullable field — an outcome-mismatch settling in a later
        cycle may reference the cycle without a single owning invocation.
        ``evidence`` is a FROZEN JSON string.
        """
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO ledger_entries (
                    entry_id, cycle_id, invocation_id, observed_at,
                    author, subject, observation_type, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    cycle_id,
                    invocation_id,
                    observed_at,
                    author,
                    subject,
                    observation_type,
                    evidence,
                ),
            )
