"""Store A + Store B config-wiring tests (Wave 3 Task 1 / Wave 4 Task 1)."""

from __future__ import annotations

from paper_trader.config import (
    APPLICATION_ID,
    open_store_a,
    open_store_b,
    store_a_path,
    store_b_path,
)
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB


def test_store_a_path_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_A_DB_PATH", str(tmp_path / "store_a.sqlite"))
    assert store_a_path() == tmp_path / "store_a.sqlite"


def test_store_a_path_default(monkeypatch):
    from pathlib import Path

    monkeypatch.delenv("STORE_A_DB_PATH", raising=False)
    assert store_a_path() == Path("./data/store_a.sqlite")


def test_open_store_a_uses_injected_path_and_applies_schema(tmp_path):
    store = open_store_a(tmp_path / "store_a.sqlite")
    assert isinstance(store, StoreA)
    assert store.path == tmp_path / "store_a.sqlite"
    assert store.path.exists()
    # framework schema applied: both Store A tables present
    with store.connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"cycle_headers", "agent_invocations"} <= tables


def test_store_a_is_distinct_from_other_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("STORE_A_DB_PATH", str(tmp_path / "store_a.sqlite"))
    monkeypatch.setenv("SKILL_REGISTRY_DB_PATH", str(tmp_path / "skills.sqlite"))
    monkeypatch.setenv("PAPER_TRADER_DB_PATH", str(tmp_path / "paper_trader.sqlite"))
    from paper_trader.config import skill_registry_path

    paths = {store_a_path(), skill_registry_path()}
    assert len(paths) == 2  # distinct


def test_store_b_path_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_B_DB_PATH", str(tmp_path / "store_b.sqlite"))
    assert store_b_path() == tmp_path / "store_b.sqlite"


def test_open_store_b_applies_ddl(tmp_path):
    store = open_store_b(tmp_path / "store_b.sqlite")
    assert isinstance(store, StoreB)
    assert store.path.exists()
    with store.connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "ledger_entries" in tables


def test_store_a_and_b_are_distinct(tmp_path, monkeypatch):
    monkeypatch.setenv("STORE_A_DB_PATH", str(tmp_path / "store_a.sqlite"))
    monkeypatch.setenv("STORE_B_DB_PATH", str(tmp_path / "store_b.sqlite"))
    assert store_a_path() != store_b_path()


def test_application_id_constant():
    assert APPLICATION_ID == "paper-trader"
