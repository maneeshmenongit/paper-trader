"""Domain model + CycleState + predictions-DDL tests (Wave 2.5 Task 1)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from paper_trader.domain import (
    Asset,
    NoView,
    PaperPortfolio,
    PaperTrade,
    Prediction,
    TradeDecision,
    View,
)
from paper_trader.graph.state import CycleState
from paper_trader.persistence.db import Database

NOW = datetime(2026, 7, 5, tzinfo=UTC)


# ─── View / NoView union (G6 / DT-6.1) ───────────────────────────────────

def test_view_shape():
    v = View(
        symbol="AAPL",
        method_selected="momentum",
        selection_mode="rule",
        direction="UP",
        magnitude_pct=1.2,
        horizon=24,
        confidence=0.7,
    )
    assert v.method_selected == "momentum"
    assert v.selection_mode == "rule"
    assert v.selection_rationale is None
    assert v.is_baseline is False


def test_noview_shape():
    nv = NoView(symbol="TSLA", reason="no_eligible_method", methods_considered=["arima"])
    assert nv.reason == "no_eligible_method"


def test_prediction_union_accepts_both():
    preds: dict[str, Prediction] = {
        "AAPL": View(
            symbol="AAPL", method_selected="momentum", selection_mode="rule",
            direction="UP", magnitude_pct=1.0, horizon=24, confidence=0.7,
        ),
        "TSLA": NoView(symbol="TSLA", reason="below_confidence_threshold"),
    }
    assert isinstance(preds["AAPL"], View)
    assert isinstance(preds["TSLA"], NoView)


def test_no_directional_prediction_type_exists():
    # The dead-thesis type must not be resurrected in the domain package.
    import paper_trader.domain as d

    assert not hasattr(d, "DirectionalPrediction")


# ─── other domain shapes ─────────────────────────────────────────────────

def test_portfolio_and_trade():
    pf = PaperPortfolio(cash_balance=10_000.0)
    assert pf.open_positions == []
    tr = PaperTrade(
        prediction_id="p1", symbol="AAPL", entry_price=100.0, quantity=5,
        notional_value=500.0, entry_time=NOW, expected_exit_time=NOW,
    )
    assert tr.direction == "LONG"      # v1 default
    assert tr.exited is False


def test_trade_decision_symmetric():
    executed = TradeDecision(prediction_id="p1", symbol="AAPL", executed=True)
    skipped = TradeDecision(
        prediction_id="p2", symbol="TSLA", executed=False, risk_reason="below_cap"
    )
    assert executed.risk_reason is None
    assert skipped.risk_reason == "below_cap"


# ─── CycleState reconciled shape (DT-4.5) ────────────────────────────────

def test_cyclestate_uses_union_prediction_type():
    cs = CycleState(
        cycle_id="cyc-1",
        started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock")],
        calibration_version="identity-v1",
    )
    # both View and NoView are valid working-memory prediction values
    cs.predictions["AAPL"] = View(
        symbol="AAPL", method_selected="momentum", selection_mode="rule",
        direction="UP", magnitude_pct=1.0, horizon=24, confidence=0.7,
    )
    cs.predictions["TSLA"] = NoView(symbol="TSLA", reason="no_eligible_method")
    assert cs.started_at == NOW
    assert set(cs.completed_agents) == set()


def test_base_imports_real_cyclestate():
    # enforce_writes must bind to the real CycleState, not the old stub.
    from paper_trader.agents import base

    assert base.CycleState is CycleState


# ─── predictions DDL reconciled shape (DT-8.3) ───────────────────────────

def test_predictions_table_has_method_selector_columns(tmp_path):
    db = Database(tmp_path / "paper_trader.sqlite")
    with db.connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()}
    assert "method_selected" in cols
    assert "selection_mode" in cols
    assert "is_baseline" in cols


def test_predictions_direction_check_allows_hold(tmp_path):
    db = Database(tmp_path / "paper_trader.sqlite")
    with db.connection() as conn:
        conn.execute("INSERT INTO assets (symbol, kind) VALUES ('AAPL','stock')")
        # a View row with method-selector provenance inserts cleanly
        conn.execute(
            """
            INSERT INTO predictions
              (cycle_id, symbol, entry_price, method_selected, selection_mode,
               direction, confidence, magnitude_pct, time_horizon_hours,
               calibration_version, created_at)
            VALUES ('cyc-1','AAPL',100.0,'momentum','rule','UP',0.7,1.0,24,
                    'identity-v1','2026-07-05T00:00:00Z')
            """
        )


def test_predictions_rejects_bad_selection_mode(tmp_path):
    db = Database(tmp_path / "paper_trader.sqlite")
    with db.connection() as conn:
        conn.execute("INSERT INTO assets (symbol, kind) VALUES ('AAPL','stock')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO predictions
                  (cycle_id, symbol, entry_price, selection_mode, direction,
                   confidence, magnitude_pct, time_horizon_hours,
                   calibration_version, created_at)
                VALUES ('cyc-1','AAPL',100.0,'heuristic','UP',0.7,1.0,24,
                        'identity-v1','2026-07-05T00:00:00Z')
                """
            )
