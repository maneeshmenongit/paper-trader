"""Momentum baseline: predict the same direction as yesterday's move.

If close[t-1] > close[t-2]: predict UP for day t
Else: predict DOWN for day t

This is the simplest possible directional strategy. The LLM has to beat this
to be worth building.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

Direction = Literal["UP", "DOWN"]


def momentum_prediction(ohlcv: pd.DataFrame, prediction_date: pd.Timestamp) -> Direction:
    """Predict the direction for `prediction_date` based on the move from
    `prediction_date - 2 trading days` to `prediction_date - 1 trading day`.

    Raises ValueError if there is insufficient history before prediction_date.
    """
    prior = ohlcv.loc[ohlcv.index < prediction_date]
    if len(prior) < 2:
        raise ValueError(
            f"insufficient history before {prediction_date.date()}: "
            f"need 2 prior rows, have {len(prior)}"
        )

    yesterday_close = float(prior["Close"].iloc[-1])
    day_before_close = float(prior["Close"].iloc[-2])
    return "UP" if yesterday_close > day_before_close else "DOWN"
