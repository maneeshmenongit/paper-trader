"""cycle_id ULID tests (DT-4.1, Wave 3 Task 2). 26-char TEXT; from injected Clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from paper_trader.domain import Asset, PaperPortfolio
from paper_trader.graph.ids import new_cycle_id
from paper_trader.graph.state import CycleState
from paper_trader.persistence.db import Database
from paper_trader.persistence.repository import Repository
from tests.fixtures.fakes import FrozenClock

T0 = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)


def test_ulid_is_26_char_text():
    cid = new_cycle_id(FrozenClock(now=T0))
    assert isinstance(cid, str)
    assert len(cid) == 26


def test_ulid_timestamp_from_injected_clock():
    # Two clocks an hour apart -> the later id sorts after the earlier (ULID
    # timestamp prefix is monotonic in time). Deterministic, no wall-clock.
    early = new_cycle_id(FrozenClock(now=T0))
    late = new_cycle_id(FrozenClock(now=T0 + timedelta(hours=1)))
    assert late > early


def test_ulid_lexicographic_orders_by_time():
    ids = [new_cycle_id(FrozenClock(now=T0 + timedelta(minutes=m))) for m in (0, 30, 90)]
    assert ids == sorted(ids)


def test_cyclestate_accepts_ulid():
    cid = new_cycle_id(FrozenClock(now=T0))
    cs = CycleState(
        cycle_id=cid, started_at=T0,
        portfolio=PaperPortfolio(cash_balance=1.0),
        watchlist=[Asset(symbol="AAPL", kind="stock")],
        calibration_version="identity-v1",
    )
    assert cs.cycle_id == cid


def test_db_consumers_accept_ulid(tmp_path):
    # predictions / trade_decisions / paper_trades all store cycle_id as TEXT;
    # a 26-char ULID inserts with no schema or behavior change.
    cid = new_cycle_id(FrozenClock(now=T0))
    repo = Repository(Database(tmp_path / "paper_trader.sqlite"))
    repo.upsert_asset(Asset(symbol="AAPL", kind="stock"))
    pid = repo.insert_prediction(
        cycle_id=cid, symbol="AAPL", entry_price=100.0,
        method_selected="momentum", selection_mode="rule", selection_rationale=None,
        direction="UP", confidence=0.7, magnitude_pct=1.0, time_horizon_hours=24,
        calibration_version="identity-v1", is_baseline=False,
        created_at=T0.isoformat(),
    )
    with repo.db.connection() as conn:
        row = conn.execute("SELECT cycle_id FROM predictions WHERE id=?", (pid,)).fetchone()
    assert row["cycle_id"] == cid
    assert len(row["cycle_id"]) == 26
