"""Stage 0 harness (step 6): end-to-end run on a small synthetic slice."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from paper_trader.backtest.stage0_gate_report import render_gate_report
from paper_trader.backtest.stage0_harness import _build_points, run_stage0


def _synthetic_history(n_symbols=22, n_days=80, seed=7):
    """Random-walk daily closes — enough symbols/days for all methods to be
    eligible and for non-zero moves (so sanity #5 holds)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")
    history = {}
    for k in range(n_symbols):
        closes = [100.0]
        for _ in range(n_days - 1):
            closes.append(max(1.0, closes[-1] * (1 + rng.normal(0.0005, 0.02))))
        history[f"SYM{k:02d}"] = pd.DataFrame({"Close": closes}, index=dates)
    return history


def test_run_end_to_end_produces_dollar_table():
    rep = run_stage0(_synthetic_history(), seed_bankroll=100_000.0, threshold_e=0.03)
    assert rep.n_points > 0
    assert rep.sanity_passed is True
    # The band ordering must hold: floor ≤ oracle ≤ ceiling (the whole point).
    assert rep.floor_pnl <= rep.oracle_pnl + 1e-6
    assert rep.oracle_pnl <= rep.ceiling_pnl + 1e-6
    assert set(rep.per_method) == {"momentum", "mean_reversion", "arima"}


def test_headroom_and_edge_ratio_consistent():
    rep = run_stage0(_synthetic_history())
    assert rep.headroom == pytest.approx(rep.oracle_pnl - rep.floor_pnl)
    assert rep.edge_ratio == pytest.approx(rep.headroom / rep.seed_bankroll)
    assert rep.go == (rep.edge_ratio >= rep.threshold_e)


def test_floor_equals_momentum_method():
    # Sanity #2 lives inside the run; if it passed, floor P&L == momentum method P&L.
    rep = run_stage0(_synthetic_history())
    assert rep.floor_pnl == pytest.approx(rep.per_method["momentum"].total_pnl)


def test_points_respect_history_floor():
    hist = _synthetic_history(n_symbols=3, n_days=60)
    points = _build_points(hist)
    # Every point has at least HISTORY_MIN prior bars (index >= HISTORY_MIN).
    from paper_trader.backtest.stage0_harness import HISTORY_MIN
    assert all(p.index >= HISTORY_MIN for p in points)


def test_gate_report_renders():
    rep = run_stage0(_synthetic_history())
    md = render_gate_report(rep)
    assert "Feasibility Backtest" in md
    assert "VERDICT:" in md
    assert "H3" in md  # the loud Stage-3 precondition flag
    assert ("GO" in md or "NO-GO" in md)


def test_empty_history_raises():
    with pytest.raises(ValueError, match="no valid backtest points"):
        run_stage0({})
