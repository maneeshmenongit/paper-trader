"""Store B (ledger) DoD tests (DT-8.2, Steward Wave 1).

Proves: exact columns per spec §5.3, the membrane absence (no action/
recommendation/severity), physical separation, insert round-trip, nullable
invocation_id, append-only no-mutation triggers, and an insert-only surface.
"""

from __future__ import annotations

import inspect
import sqlite3

import pytest

from steward.storage.store_b import StoreB

LEDGER_COLUMNS = [
    "entry_id",
    "cycle_id",
    "invocation_id",
    "observed_at",
    "author",
    "subject",
    "observation_type",
    "evidence",
]

# Fields whose PRESENCE would breach the membrane (spec §5.3).
FORBIDDEN_COLUMNS = {"action", "recommendation", "severity"}


def _entry_kwargs(entry_id: str = "ent-1", **overrides) -> dict:
    base = dict(
        entry_id=entry_id,
        cycle_id="cyc-1",
        invocation_id="inv-1",
        observed_at="2026-07-04T00:00:03Z",
        author="correction-officer",
        subject="Predict@v1",
        observation_type="constraint-violation",
        evidence='{"detail": "confidence below threshold"}',
    )
    base.update(overrides)
    return base


@pytest.fixture
def store(tmp_path):
    return StoreB(tmp_path / "store_b.sqlite")


def _columns(store: StoreB, table: str) -> list[str]:
    with store.connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r["name"] for r in rows]


# ─── schema shape ────────────────────────────────────────────────────────

def test_ledger_table_exact_columns(store):
    assert _columns(store, "ledger_entries") == LEDGER_COLUMNS


def test_membrane_absence(store):
    """No action / recommendation / severity — the absence IS the membrane."""
    cols = set(_columns(store, "ledger_entries"))
    assert cols.isdisjoint(FORBIDDEN_COLUMNS)


def test_membrane_absence_in_schema_source():
    from steward.storage.store_b import SCHEMA_PATH

    # Strip comments; the prose intentionally names the forbidden fields.
    ddl = "\n".join(
        line.split("--", 1)[0] for line in SCHEMA_PATH.read_text().splitlines()
    ).lower()
    for forbidden in FORBIDDEN_COLUMNS:
        assert forbidden not in ddl


def test_only_one_table(store):
    with store.connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    assert tables == {"ledger_entries"}


def test_replay_index_present(store):
    with store.connection() as conn:
        indexes = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_ledger_entries_cycle_id" in indexes


# ─── round-trip ──────────────────────────────────────────────────────────

def test_insert_and_roundtrip(store):
    store.insert_ledger_entry(**_entry_kwargs())
    with store.connection() as conn:
        row = conn.execute(
            "SELECT * FROM ledger_entries WHERE entry_id='ent-1'"
        ).fetchone()
    assert row["cycle_id"] == "cyc-1"
    assert row["author"] == "correction-officer"
    assert row["observation_type"] == "constraint-violation"
    assert row["evidence"] == '{"detail": "confidence below threshold"}'


def test_invocation_id_nullable(store):
    # Outcome-mismatch settling in a later cycle: no single owning invocation.
    store.insert_ledger_entry(**_entry_kwargs(entry_id="ent-2", invocation_id=None))
    with store.connection() as conn:
        row = conn.execute(
            "SELECT invocation_id FROM ledger_entries WHERE entry_id='ent-2'"
        ).fetchone()
    assert row["invocation_id"] is None


# ─── no-mutation triggers ────────────────────────────────────────────────

def test_update_rejected_by_trigger(store):
    store.insert_ledger_entry(**_entry_kwargs())
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE ledger_entries SET author='tamper'")


def test_delete_rejected_by_trigger(store):
    store.insert_ledger_entry(**_entry_kwargs())
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM ledger_entries")


# ─── physical separation ─────────────────────────────────────────────────

def test_store_b_file_is_distinct_path(tmp_path):
    app_db = tmp_path / "paper_trader.sqlite"
    checkpointer = tmp_path / "checkpointer.sqlite"
    store_a = tmp_path / "store_a.sqlite"
    store_b = StoreB(tmp_path / "store_b.sqlite")

    assert store_b.path.exists()
    assert store_b.path not in {app_db, checkpointer, store_a}


# ─── no update/delete surface ────────────────────────────────────────────

def test_writer_surface_has_no_update_or_delete():
    public = [
        name
        for name, _ in inspect.getmembers(StoreB, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    assert set(public) == {"insert_ledger_entry", "connection"}


def test_module_sql_literals_have_no_update_or_delete():
    import ast

    import steward.storage.store_b as mod

    tree = ast.parse(inspect.getsource(mod))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc.upper())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.upper()
            if s in docstrings:
                continue
            assert "UPDATE" not in s
            assert "DELETE" not in s
