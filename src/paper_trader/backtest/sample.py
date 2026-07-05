"""Sample prediction points across the historical dataset.

A 'prediction point' is a (symbol, date) pair where we have:
- At least 30 trading days of history before `date` (for technicals + LLM context)
- A valid close price on `date` (for ground-truth evaluation)
- A valid close price on `date + 1 trading day` (the prediction target)

For T03 evaluation, we need >= 200 prediction points across >= 20 distinct stocks
and >= 6 months of distinct trading days.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

import pandas as pd

HISTORY_WINDOW_DAYS = 30


@dataclass
class PredictionPoint:
    symbol: str
    prediction_date: pd.Timestamp  # the day "as of which" the prediction is made
    target_date: pd.Timestamp  # next trading day
    history_window: pd.DataFrame  # last 30 trading days through prediction_date
    actual_direction: Literal["UP", "DOWN"]  # ground truth: close(target) vs close(prediction_date)
    actual_magnitude_pct: float  # (close(target) - close(pred)) / close(pred) * 100


def _valid_indices(df: pd.DataFrame) -> list[int]:
    """Positional indices i in df where a prediction point can be formed:
    >= 30 rows of history before i, and a valid next row i+1.
    """
    n = len(df)
    # i needs HISTORY_WINDOW_DAYS rows before it (positions 0..i-1) and a row at i+1.
    return [i for i in range(HISTORY_WINDOW_DAYS, n - 1)]


def _build_point(symbol: str, df: pd.DataFrame, i: int) -> PredictionPoint:
    prediction_date = df.index[i]
    target_date = df.index[i + 1]
    close_pred = float(df["Close"].iloc[i])
    close_target = float(df["Close"].iloc[i + 1])
    magnitude = (close_target - close_pred) / close_pred * 100.0
    direction: Literal["UP", "DOWN"] = "UP" if close_target > close_pred else "DOWN"
    history = df.iloc[i - HISTORY_WINDOW_DAYS : i + 1]  # last 30 days through prediction_date
    return PredictionPoint(
        symbol=symbol,
        prediction_date=prediction_date,
        target_date=target_date,
        history_window=history,
        actual_direction=direction,
        actual_magnitude_pct=magnitude,
    )


def sample_prediction_points(
    ohlcv_by_symbol: dict[str, pd.DataFrame],
    n_samples: int = 500,
    min_distinct_symbols: int = 20,
    min_distinct_days: int = 130,  # ~6 months of trading days
    seed: int = 42,
) -> list[PredictionPoint]:
    """Sample `n_samples` prediction points subject to diversity constraints.

    Algorithm:
    1. Build the full set of valid (symbol, positional-index) candidates.
    2. Stratify first: take one point from each symbol (round-robin over shuffled
       per-symbol candidates) so the diversity floor is met by construction, then
       fill the remainder by random sampling from what's left.
    3. Validate the diversity constraints on the final set.

    Raises ValueError if the dataset cannot meet the diversity constraints
    (e.g., user passed in only 5 stocks, or too few distinct days exist).
    """
    rng = random.Random(seed)

    # 1. Build candidates per symbol.
    candidates: dict[str, list[int]] = {}
    for symbol, df in ohlcv_by_symbol.items():
        if df is None or df.empty:
            continue
        df = df.sort_index()
        idxs = _valid_indices(df)
        if idxs:
            candidates[symbol] = idxs

    n_symbols_available = len(candidates)
    total_candidates = sum(len(v) for v in candidates.values())

    if n_symbols_available < min_distinct_symbols:
        raise ValueError(
            f"need >= {min_distinct_symbols} distinct symbols with valid history, "
            f"have {n_symbols_available}"
        )
    if total_candidates < n_samples:
        # Not fatal on its own, but warn-by-clamp: we can't sample more than exist.
        n_samples = total_candidates

    sorted_frames = {s: ohlcv_by_symbol[s].sort_index() for s in candidates}

    # Flat pool of all candidates, tagged with their trading day, shuffled once.
    pool: list[tuple[str, int, pd.Timestamp]] = []
    for s in candidates:
        idx = sorted_frames[s].index
        for i in candidates[s]:
            pool.append((s, i, idx[i].normalize()))
    rng.shuffle(pool)

    chosen: set[tuple[str, int]] = set()
    seen_symbols: set[str] = set()
    seen_days: set[pd.Timestamp] = set()

    # 2a. Symbol-stratified pass — guarantee one point per symbol.
    by_symbol: dict[str, tuple[str, int, pd.Timestamp]] = {}
    for cand in pool:
        by_symbol.setdefault(cand[0], cand)
    for s in sorted(by_symbol):
        if len(chosen) >= n_samples:
            break
        sym, i, day = by_symbol[s]
        chosen.add((sym, i))
        seen_symbols.add(sym)
        seen_days.add(day)

    # 2b. Day-greedy fill — prefer candidates on days not yet covered, so the
    # distinct-day floor is met whenever the pool can support it; then top up
    # with whatever remains.
    for prefer_new_day in (True, False):
        for cand in pool:
            if len(chosen) >= n_samples:
                break
            sym, i, day = cand
            if (sym, i) in chosen:
                continue
            if prefer_new_day and day in seen_days:
                continue
            chosen.add((sym, i))
            seen_days.add(day)
        if len(chosen) >= n_samples:
            break

    # 3. Build points and validate diversity.
    points = [_build_point(s, sorted_frames[s], i) for (s, i) in chosen]
    # Deterministic order: by symbol then date.
    points.sort(key=lambda p: (p.symbol, p.prediction_date))

    distinct_symbols = len({p.symbol for p in points})
    distinct_days = len({p.prediction_date.normalize() for p in points})

    if distinct_symbols < min_distinct_symbols:
        raise ValueError(
            f"sampled only {distinct_symbols} distinct symbols, need {min_distinct_symbols}"
        )
    if distinct_days < min_distinct_days:
        raise ValueError(
            f"sampled only {distinct_days} distinct trading days, need {min_distinct_days}. "
            f"Provide more history or more symbols."
        )

    return points
