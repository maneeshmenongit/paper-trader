# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            with open(SCHEMA_PATH) as f:
                conn.executescript(f.read())

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
