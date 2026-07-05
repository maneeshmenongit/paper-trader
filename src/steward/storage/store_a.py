"""Store A — execution-trace store (DT-8.1, Steward Wave 1).

FRAMEWORK layer (DC-1): the framework defines the record shapes; the app injects
the file path and the already-serialized field values.

Store A is an immutable, append-only execution trace. This module exposes ONLY
two insert methods and no path to UPDATE or DELETE any row. Append-only is
enforced at the app layer in this task — there are no rejection triggers here
(that is Store B / DT-8.2 territory).

The file is physically separate from the app db, the checkpointer, and Store B:
the caller supplies its path, and the four-connection factory (DT-8.5) is what
keeps the four paths distinct. This module never hardcodes where the file lives.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "store_a_schema.sql"


class StoreA:
    """Connection/init helper + INSERT-only writer for the Store A trace file.

    Creates the SQLite file if absent, applies the schema, and — on every
    connection — sets ``PRAGMA foreign_keys=ON`` (so the intra-file cycle_id FK
    is enforced) and ``PRAGMA journal_mode=WAL`` (so replay reads never block
    fast-loop writes).
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
        # foreign_keys is connection-scoped in SQLite; set it every time.
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL so replay reads never block fast-loop writes. journal_mode is a
        # persistent, file-level setting; re-asserting it is cheap and harmless.
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
    # Exactly two methods. No update/delete anywhere in this module.

    def insert_cycle_header(
        self,
        *,
        cycle_id: str,
        application_id: str,
        started_at: str,
        ended_at: str,
        trigger_kind: str,
        orchestrator_input: str,
        orchestrator_decision: str,
        decision_mode: str,
        orchestrator_rationale: str | None,
        status: str,
    ) -> None:
        """Append one cycle header. Fields arrive already serialized.

        ``orchestrator_input``/``orchestrator_decision`` are FROZEN JSON strings.
        ``orchestrator_rationale`` is the only nullable field.
        """
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO cycle_headers (
                    cycle_id, application_id, started_at, ended_at,
                    trigger_kind, orchestrator_input, orchestrator_decision,
                    decision_mode, orchestrator_rationale, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    application_id,
                    started_at,
                    ended_at,
                    trigger_kind,
                    orchestrator_input,
                    orchestrator_decision,
                    decision_mode,
                    orchestrator_rationale,
                    status,
                ),
            )

    def insert_agent_invocation(
        self,
        *,
        invocation_id: str,
        cycle_id: str,
        application_id: str,
        agent_name: str,
        skill_version_id: str,
        agent_input: str,
        agent_output: str,
        started_at: str,
        ended_at: str,
        status: str,
    ) -> None:
        """Append one agent invocation. Fields arrive already serialized.

        ``cycle_id`` is an enforced intra-file FK to ``cycle_headers``.
        ``skill_version_id`` is a LOGICAL reference only (verified at the app
        layer, not a DB FK). ``agent_input``/``agent_output`` are FROZEN; "no
        output" is serialized explicitly, never left null.
        """
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_invocations (
                    invocation_id, cycle_id, application_id, agent_name,
                    skill_version_id, agent_input, agent_output,
                    started_at, ended_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invocation_id,
                    cycle_id,
                    application_id,
                    agent_name,
                    skill_version_id,
                    agent_input,
                    agent_output,
                    started_at,
                    ended_at,
                    status,
                ),
            )
