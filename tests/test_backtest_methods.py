"""Stage 0 forecasting methods (step 3).

Key invariant (sanity check #2 precondition): backtest momentum agrees bit-for-bit
with baseline.momentum_prediction. Plus per-method eligibility floors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from paper_trader.backtest import baseline, methods

# ─── momentum: verbatim agreement with the floor rule ────────────────────

def test_momentum_up():
    f = methods.momentum([100.0, 105.0])
    assert f.eligible and f.direction == "UP"
    assert f.magnitude_pct > 0


def test_momentum_down():
    assert methods.momentum([105.0, 100.0]).direction == "DOWN"


def test_momentum_flat_is_hold():
    assert methods.momentum([100.0, 100.0]).direction == "HOLD"


def test_momentum_ineligible_below_min_history():
    assert methods.momentum([100.0]).eligible is False


def test_momentum_matches_baseline_bit_for_bit():
    # The floor rule (baseline.momentum_prediction) reads a DataFrame keyed by date;
    # the method reads a closes list. For every 2-close window they MUST agree.
    rng = np.random.default_rng(0)
    closes = [100.0]
    for _ in range(50):
        closes.append(closes[-1] * (1 + rng.normal(0, 0.02)))
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    df = pd.DataFrame({"Close": closes}, index=dates)
    for i in range(2, len(closes)):
        pred_date = dates[i]
        floor_dir = baseline.momentum_prediction(df, pred_date)  # UP/DOWN only
        method_dir = methods.momentum(closes[:i]).direction
        # baseline never returns HOLD (ties → DOWN); methods returns HOLD on exact
        # ties. Random floats never tie here, so directions must match exactly.
        assert method_dir == floor_dir, f"mismatch at i={i}: {method_dir} vs {floor_dir}"


# ─── mean_reversion: fades the move ──────────────────────────────────────

def test_mean_reversion_above_sma_forecasts_down():
    closes = [100.0] * 20 + [130.0]  # last close well above the flat SMA
    f = methods.mean_reversion(closes)
    assert f.eligible and f.direction == "DOWN"


def test_mean_reversion_below_sma_forecasts_up():
    closes = [100.0] * 20 + [70.0]
    assert methods.mean_reversion(closes).direction == "UP"


def test_mean_reversion_ineligible_short_history():
    assert methods.mean_reversion([100.0] * 5).eligible is False


# ─── arima: minimal AR(1) ────────────────────────────────────────────────

def test_arima_eligible_on_trend():
    closes = [100.0 + i for i in range(15)]  # clean uptrend
    f = methods.arima(closes)
    assert f.eligible and f.direction == "UP"


def test_arima_ineligible_short_history():
    assert methods.arima([100.0, 101.0, 102.0]).eligible is False


def test_arima_ineligible_constant_series():
    assert methods.arima([100.0] * 15).eligible is False


# ─── roster helpers ──────────────────────────────────────────────────────

def test_forecast_all_returns_every_method():
    out = methods.forecast_all([100.0 + i for i in range(25)])
    assert set(out) == {"momentum", "mean_reversion", "arima"}


def test_eligibility_varies_by_history_length():
    # 3 closes: only momentum eligible (others need more history).
    out = methods.forecast_all([100.0, 101.0, 102.0])
    assert out["momentum"].eligible is True
    assert out["mean_reversion"].eligible is False
    assert out["arima"].eligible is False


def test_magnitude_is_never_negative():
    for closes in ([105.0, 100.0], [100.0] * 20 + [130.0], [100.0 + i for i in range(15)]):
        for f in methods.forecast_all(closes).values():
            assert f.magnitude_pct >= 0.0
