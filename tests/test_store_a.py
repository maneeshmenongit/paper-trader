"""Store A DoD tests (DT-8.1, Steward Wave 1).

Proves: exact columns + CHECK constraints, physical separation of the trace file,
insert round-trip, enforced cycle_id FK, and a writer surface with NO
update/delete capability.
"""

from __future__ import annotations

import inspect
import sqlite3

import pytest

from steward.storage.store_a import StoreA

# ─── fixtures / helpers ──────────────────────────────────────────────────

def _header_kwargs(cycle_id: str = "cyc-1", **overrides) -> dict:
    base = dict(
        cycle_id=cycle_id,
        application_id="paper-trader",
        started_at="2026-07-04T00:00:00Z",
        ended_at="2026-07-04T00:00:05Z",
        trigger_kind="schedule",
        orchestrator_input='{"situation": "snapshot"}',
        orchestrator_decision='{"shape": "decision"}',
        decision_mode="rule",
        orchestrator_rationale=None,
        status="completed",
    )
    base.update(overrides)
    return base


def _invocation_kwargs(invocation_id: str = "inv-1", cycle_id: str = "cyc-1", **overrides) -> dict:
    base = dict(
        invocation_id=invocation_id,
        cycle_id=cycle_id,
        application_id="paper-trader",
        agent_name="analyst",
        skill_version_id="skill@v1",
        agent_input='{"in": 1}',
        agent_output='{"out": 2}',
        started_at="2026-07-04T00:00:01Z",
        ended_at="2026-07-04T00:00:02Z",
        status="ok",
    )
    base.update(overrides)
    return base


@pytest.fixture
def store(tmp_path):
    return StoreA(tmp_path / "store_a.sqlite")


# ─── schema shape: exact columns ─────────────────────────────────────────

CYCLE_HEADER_COLUMNS = [
    "cycle_id",
    "application_id",
    "started_at",
    "ended_at",
    "trigger_kind",
    "orchestrator_input",
    "orchestrator_decision",
    "decision_mode",
    "orchestrator_rationale",
    "status",
]

AGENT_INVOCATION_COLUMNS = [
    "invocation_id",
    "cycle_id",
    "application_id",
    "agent_name",
    "skill_version_id",
    "agent_input",
    "agent_output",
    "started_at",
    "ended_at",
    "status",
]


def _columns(store: StoreA, table: str) -> list[str]:
    with store.connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r["name"] for r in rows]


def test_tables_exist_with_exact_columns(store):
    with store.connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "cycle_headers" in tables
    assert "agent_invocations" in tables
    assert _columns(store, "cycle_headers") == CYCLE_HEADER_COLUMNS
    assert _columns(store, "agent_invocations") == AGENT_INVOCATION_COLUMNS


def test_only_two_tables(store):
    with store.connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    assert tables == {"cycle_headers", "agent_invocations"}


def test_replay_index_present(store):
    with store.connection() as conn:
        indexes = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='agent_invocations'"
            ).fetchall()
        }
    assert "idx_agent_invocations_cycle_id" in indexes


# ─── CHECK constraints ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "field,bad",
    [
        ("trigger_kind", "cron"),
        ("decision_mode", "heuristic"),
        ("status", "done"),
    ],
)
def test_cycle_header_check_constraints(store, field, bad):
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_cycle_header(**_header_kwargs(**{field: bad}))


@pytest.mark.parametrize(
    "field,good",
    [
        ("trigger_kind", "event"),
        ("trigger_kind", "manual"),
        ("decision_mode", "llm"),
        ("status", "failed"),
        ("status", "partial"),
    ],
)
def test_cycle_header_accepts_valid_enum_values(store, field, good):
    store.insert_cycle_header(**_header_kwargs(**{field: good}))


# ─── round-trip ──────────────────────────────────────────────────────────

def test_insert_and_roundtrip(store):
    store.insert_cycle_header(**_header_kwargs())
    store.insert_agent_invocation(**_invocation_kwargs())

    with store.connection() as conn:
        header = conn.execute(
            "SELECT * FROM cycle_headers WHERE cycle_id='cyc-1'"
        ).fetchone()
        inv = conn.execute(
            "SELECT * FROM agent_invocations WHERE invocation_id='inv-1'"
        ).fetchone()

    assert header["application_id"] == "paper-trader"
    assert header["orchestrator_input"] == '{"situation": "snapshot"}'
    assert header["orchestrator_rationale"] is None
    assert inv["cycle_id"] == "cyc-1"
    assert inv["skill_version_id"] == "skill@v1"
    assert inv["agent_output"] == '{"out": 2}'


def test_rationale_nullable(store):
    store.insert_cycle_header(**_header_kwargs(orchestrator_rationale="because momentum"))
    with store.connection() as conn:
        row = conn.execute(
            "SELECT orchestrator_rationale FROM cycle_headers WHERE cycle_id='cyc-1'"
        ).fetchone()
    assert row["orchestrator_rationale"] == "because momentum"


# ─── FK enforcement ──────────────────────────────────────────────────────

def test_invocation_requires_existing_cycle(store):
    # No matching cycle_headers row -> intra-file FK must reject.
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_agent_invocation(**_invocation_kwargs(cycle_id="does-not-exist"))


def test_invocation_succeeds_after_header(store):
    store.insert_cycle_header(**_header_kwargs(cycle_id="cyc-2"))
    store.insert_agent_invocation(**_invocation_kwargs(cycle_id="cyc-2"))  # no raise


# ─── physical separation ─────────────────────────────────────────────────

def test_store_a_file_is_distinct_path(tmp_path):
    app_db = tmp_path / "paper_trader.sqlite"
    checkpointer = tmp_path / "checkpointer.sqlite"
    store_b = tmp_path / "store_b.sqlite"
    store_a = StoreA(tmp_path / "store_a.sqlite")

    assert store_a.path.exists()
    distinct = {store_a.path, app_db, checkpointer, store_b}
    assert len(distinct) == 4  # four distinct paths
    assert store_a.path not in {app_db, checkpointer, store_b}


# ─── no update/delete surface ────────────────────────────────────────────

def test_writer_surface_has_no_update_or_delete():
    public = [
        name
        for name, _ in inspect.getmembers(StoreA, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    # Exactly the two inserts plus the connection helper — nothing mutating.
    assert set(public) == {"insert_cycle_header", "insert_agent_invocation", "connection"}
    for name in public:
        assert "update" not in name.lower()
        assert "delete" not in name.lower()


def test_module_source_has_no_update_or_delete_sql():
    """No UPDATE/DELETE in any SQL the module can execute.

    Scan the module's string literals (where SQL lives) rather than the whole
    source, so prose in docstrings/comments doesn't trip the check.
    """
    import ast

    import steward.storage.store_a as mod

    tree = ast.parse(inspect.getsource(mod))
    literals = [
        node.value.upper()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    # Exclude docstrings (the first statement's constant in module/func bodies).
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc.upper())
    sql_literals = [s for s in literals if s not in docstrings]

    for s in sql_literals:
        assert "UPDATE" not in s, f"UPDATE found in SQL literal: {s!r}"
        assert "DELETE" not in s, f"DELETE found in SQL literal: {s!r}"


def test_no_mutation_triggers_present():
    """DT-8.2 ruling: Store A carries the same no-mutation triggers as Store B."""
    from steward.storage.store_a import SCHEMA_PATH

    ddl = SCHEMA_PATH.read_text().upper()
    for table in ("CYCLE_HEADERS", "AGENT_INVOCATIONS"):
        assert f"BEFORE UPDATE ON {table}" in ddl
        assert f"BEFORE DELETE ON {table}" in ddl


@pytest.mark.parametrize("table", ["cycle_headers", "agent_invocations"])
def test_update_rejected_by_trigger(store, table):
    store.insert_cycle_header(**_header_kwargs())
    if table == "agent_invocations":
        store.insert_agent_invocation(**_invocation_kwargs())
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"UPDATE {table} SET status='hacked'")


@pytest.mark.parametrize("table", ["cycle_headers", "agent_invocations"])
def test_delete_rejected_by_trigger(store, table):
    store.insert_cycle_header(**_header_kwargs())
    if table == "agent_invocations":
        store.insert_agent_invocation(**_invocation_kwargs())
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"DELETE FROM {table}")
