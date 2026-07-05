"""Unit tests for prediction-point sampling and its diversity constraints."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from paper_trader.backtest.sample import sample_prediction_points


def _synthetic(symbol_seed: int, n_days: int = 250) -> pd.DataFrame:
    """Deterministic random-walk OHLCV with `n_days` trading days."""
    rng = np.random.default_rng(symbol_seed)
    idx = pd.bdate_range("2023-01-02", periods=n_days, name="Date")
    closes = 100 + np.cumsum(rng.normal(0, 1, n_days))
    return pd.DataFrame({"Close": closes, "Open": closes, "Volume": 1_000_000}, index=idx)


def _universe(n_symbols: int, n_days: int = 250) -> dict[str, pd.DataFrame]:
    return {f"SYM{i:02d}": _synthetic(i, n_days) for i in range(n_symbols)}


def test_sampling_is_reproducible():
    data = _universe(25)
    a = sample_prediction_points(data, n_samples=200, seed=7)
    b = sample_prediction_points(data, n_samples=200, seed=7)
    assert [(p.symbol, p.prediction_date) for p in a] == [
        (p.symbol, p.prediction_date) for p in b
    ]


def test_meets_diversity_constraints():
    data = _universe(25)
    points = sample_prediction_points(data, n_samples=300)
    assert len(points) == 300
    assert len({p.symbol for p in points}) >= 20
    assert len({p.prediction_date.normalize() for p in points}) >= 130


def test_derived_fields_are_correct():
    data = _universe(25)
    points = sample_prediction_points(data, n_samples=200)
    p = points[0]
    df = data[p.symbol].sort_index()
    close_pred = float(df.loc[p.prediction_date, "Close"])
    close_target = float(df.loc[p.target_date, "Close"])
    expected_dir = "UP" if close_target > close_pred else "DOWN"
    expected_mag = (close_target - close_pred) / close_pred * 100
    assert p.actual_direction == expected_dir
    assert p.actual_magnitude_pct == pytest.approx(expected_mag)
    assert len(p.history_window) == 31  # 30 days + prediction_date row


def test_raises_when_too_few_symbols():
    data = _universe(5)  # below the 20-symbol floor
    with pytest.raises(ValueError, match="distinct symbols"):
        sample_prediction_points(data, n_samples=200)


def test_raises_when_too_few_distinct_days():
    # 25 symbols but each only long enough for a couple of points → can't hit 130 days.
    data = _universe(25, n_days=33)  # only ~2 valid indices each
    with pytest.raises(ValueError, match="distinct trading days"):
        sample_prediction_points(data, n_samples=200)
