"""Unit tests for the momentum baseline. Synthetic OHLCV, fully deterministic."""

from __future__ import annotations

import pandas as pd
import pytest

from paper_trader.backtest.baseline import momentum_prediction


def _frame(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start=start, periods=len(closes), name="Date")
    return pd.DataFrame({"Close": closes}, index=idx)


def test_predicts_up_when_yesterday_rose():
    df = _frame([10.0, 11.0, 12.0])  # close[t-1]=11 > close[t-2]=10 → UP
    pred_date = df.index[2]
    assert momentum_prediction(df, pred_date) == "UP"


def test_predicts_down_when_yesterday_fell():
    df = _frame([10.0, 9.0, 8.0])  # close[t-1]=9 < close[t-2]=10 → DOWN
    pred_date = df.index[2]
    assert momentum_prediction(df, pred_date) == "DOWN"


def test_flat_is_down():
    df = _frame([10.0, 10.0, 10.0])  # not strictly greater → DOWN
    pred_date = df.index[2]
    assert momentum_prediction(df, pred_date) == "DOWN"


def test_only_uses_history_strictly_before_prediction_date():
    # The value ON prediction_date must be ignored; only prior two closes matter.
    df = _frame([5.0, 7.0, 100.0])  # prior to idx2: 5 then 7 → UP regardless of idx2's close
    pred_date = df.index[2]
    assert momentum_prediction(df, pred_date) == "UP"


def test_raises_on_insufficient_history():
    df = _frame([10.0, 11.0])
    pred_date = df.index[1]  # only 1 prior row
    with pytest.raises(ValueError, match="insufficient history"):
        momentum_prediction(df, pred_date)
