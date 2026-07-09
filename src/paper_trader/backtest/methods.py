"""The three deterministic forecasting methods (Stage 0 step 3).

Each method takes a symbol's daily closes **strictly before** the decision date
(chronological, oldest→newest) and returns a ``MethodForecast``. No LLM, no
network — pure functions over history. Long-only (§3 fence): a DOWN forecast means
"don't enter", never a short; the settlement adapter enters iff ``direction == UP``.

Eligibility is per-method, per-point: a method with too little history to form its
forecast is ``eligible=False`` and is skipped for that point. A point may therefore
have 1, 2, or 3 eligible methods — this is exactly the eligible set Stage 1's R4
LLM selector will later choose among.

``momentum`` reuses the existing rule VERBATIM (same as
``backtest/baseline.momentum_prediction`` and ``agents/predict._momentum``): last
close vs the prior close. Stage-0 sanity check #2 verifies bit-for-bit agreement.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from paper_trader.domain import ForecastDirection

# Minimum history each method needs to form a forecast (its R1 eligibility floor).
MOMENTUM_MIN_HISTORY = 2      # yesterday vs the day before
MEAN_REVERSION_WINDOW = 20    # short SMA window
MEAN_REVERSION_MIN_HISTORY = MEAN_REVERSION_WINDOW + 1
ARIMA_MIN_HISTORY = 10        # minimal AR(1) fit needs a handful of points


@dataclass(frozen=True)
class MethodForecast:
    """One method's call for one point.

    ``direction`` is the forecast's directional call (UP/DOWN/HOLD). ``magnitude_pct``
    is the method's own predicted move size in percent (always ≥ 0; the sign lives in
    ``direction``, never in the magnitude — guards the -0.0/M12 bug class). ``eligible``
    is False when the method lacks its minimum history for this point, in which case
    direction/magnitude are not meaningful and the point is skipped for this method.
    """

    direction: ForecastDirection
    magnitude_pct: float
    eligible: bool

    @staticmethod
    def ineligible() -> MethodForecast:
        return MethodForecast(direction="HOLD", magnitude_pct=0.0, eligible=False)


def momentum(closes: list[float]) -> MethodForecast:
    """Prior-move momentum: direction of the last close vs the one before.

    VERBATIM the rule in ``baseline.momentum_prediction`` / ``predict._momentum``:
    UP if last > prev, DOWN if last < prev, HOLD on a flat move. Magnitude is the
    absolute relative move in percent.
    """
    if len(closes) < MOMENTUM_MIN_HISTORY:
        return MethodForecast.ineligible()
    prev, last = closes[-2], closes[-1]
    move = (last - prev) / prev if prev else 0.0
    direction: ForecastDirection = "UP" if last > prev else "DOWN" if last < prev else "HOLD"
    return MethodForecast(direction=direction, magnitude_pct=abs(move) * 100.0, eligible=True)


def mean_reversion(closes: list[float]) -> MethodForecast:
    """Fade the recent move: forecast reversion toward a short SMA.

    If the last close sits ABOVE its ``MEAN_REVERSION_WINDOW``-day SMA, the move is
    stretched up and we forecast a pull-back DOWN; below the SMA → forecast a bounce
    UP. Magnitude is the absolute gap to the SMA in percent (how stretched it is).
    """
    if len(closes) < MEAN_REVERSION_MIN_HISTORY:
        return MethodForecast.ineligible()
    window = closes[-MEAN_REVERSION_WINDOW:]
    sma = sum(window) / len(window)
    last = closes[-1]
    if sma == 0:
        return MethodForecast.ineligible()
    gap = (last - sma) / sma
    # Above the mean → expect reversion DOWN; below → UP; exactly on it → HOLD.
    direction: ForecastDirection = "DOWN" if last > sma else "UP" if last < sma else "HOLD"
    return MethodForecast(direction=direction, magnitude_pct=abs(gap) * 100.0, eligible=True)


def arima(closes: list[float]) -> MethodForecast:
    """Minimal AR(1) one-step forecast via OLS on the close series.

    Fits ``close[t] = a + b * close[t-1]`` by least squares over the pre-decision
    window, predicts the next close, and derives the directional call from the
    predicted move vs the last close. Ineligible if the fit cannot be formed (too
    little history, or a degenerate/constant series). Kept deliberately minimal —
    "minimal AR(1)/ARIMA" per the build prompt — with no statsmodels dependency.
    """
    if len(closes) < ARIMA_MIN_HISTORY:
        return MethodForecast.ineligible()
    series = np.asarray(closes, dtype=float)
    x = series[:-1]
    y = series[1:]
    # Degenerate if x has no variance (constant history) → OLS slope undefined.
    if np.ptp(x) == 0:
        return MethodForecast.ineligible()
    # OLS for y = a + b*x.
    design = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    a, b = float(coef[0]), float(coef[1])
    last = float(series[-1])
    predicted = a + b * last
    if not np.isfinite(predicted) or last == 0:
        return MethodForecast.ineligible()
    move = (predicted - last) / last
    direction: ForecastDirection = (
        "UP" if predicted > last else "DOWN" if predicted < last else "HOLD"
    )
    return MethodForecast(direction=direction, magnitude_pct=abs(move) * 100.0, eligible=True)


# The roster, in the order the domain's ForecastMethod Literal declares them.
METHODS = {
    "momentum": momentum,
    "mean_reversion": mean_reversion,
    "arima": arima,
}


def forecast_all(closes: list[float]) -> dict[str, MethodForecast]:
    """Run every method over ``closes``; return name → forecast (incl. ineligible)."""
    return {name: fn(closes) for name, fn in METHODS.items()}
