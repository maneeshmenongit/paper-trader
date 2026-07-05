"""Unit tests for the scoring math: hit rate, HOLD-dropping, head-to-head compare."""

from __future__ import annotations

import pandas as pd
import pytest

from paper_trader.backtest.evaluation import compare, evaluate
from paper_trader.backtest.sample import PredictionPoint


def _point(symbol: str, day: str, direction: str, mag: float = 1.0) -> PredictionPoint:
    ts = pd.Timestamp(day)
    return PredictionPoint(
        symbol=symbol,
        prediction_date=ts,
        target_date=ts + pd.Timedelta(days=1),
        history_window=pd.DataFrame(),
        actual_direction=direction,  # type: ignore[arg-type]
        actual_magnitude_pct=mag,
    )


def test_hit_rate_basic():
    points = [
        _point("AAPL", "2024-01-02", "UP"),
        _point("AAPL", "2024-01-03", "DOWN"),
        _point("MSFT", "2024-01-02", "UP"),
        _point("MSFT", "2024-01-03", "UP"),
    ]
    preds = ["UP", "DOWN", "DOWN", "UP"]  # 3 of 4 correct
    res = evaluate(preds, points)
    assert res.n_predictions == 4
    assert res.n_correct == 3
    assert res.hit_rate == 0.75
    assert res.n_distinct_symbols == 2
    assert res.n_distinct_days == 2


def test_hold_and_none_dropped_from_denominator():
    points = [
        _point("AAPL", "2024-01-02", "UP"),
        _point("AAPL", "2024-01-03", "DOWN"),
        _point("MSFT", "2024-01-02", "UP"),
    ]
    preds = ["UP", None, None]  # only one scored, and it's correct
    res = evaluate(preds, points)
    assert res.n_predictions == 1
    assert res.n_correct == 1
    assert res.hit_rate == 1.0
    # Symbols/days counted only over scored predictions.
    assert res.n_distinct_symbols == 1


def test_empty_hit_rate_is_zero_not_nan():
    points = [_point("AAPL", "2024-01-02", "UP")]
    res = evaluate([None], points)
    assert res.n_predictions == 0
    assert res.hit_rate == 0.0


def test_length_mismatch_raises():
    points = [_point("AAPL", "2024-01-02", "UP")]
    with pytest.raises(ValueError, match="length mismatch"):
        evaluate(["UP", "DOWN"], points)


def test_compare_head_to_head_buckets():
    points = [
        _point("AAPL", "2024-01-02", "UP"),  # llm right, base right
        _point("AAPL", "2024-01-03", "UP"),  # llm right, base wrong
        _point("MSFT", "2024-01-02", "UP"),  # llm wrong, base right
        _point("MSFT", "2024-01-03", "UP"),  # both wrong
        _point("NVDA", "2024-01-02", "UP"),  # baseline HOLD → not overlapping
    ]
    llm = ["UP", "UP", "DOWN", "DOWN", "UP"]
    base = ["UP", "DOWN", "UP", "DOWN", None]
    cmp = compare(llm, base, points)

    assert cmp.n_overlapping_predictions == 4
    assert cmp.n_both_correct == 1
    assert cmp.n_llm_beat_baseline == 1
    assert cmp.n_baseline_beat_llm == 1
    assert cmp.n_both_wrong == 1

    # LLM: 3/5 correct (UP,UP,DOWN→wrong,DOWN→wrong,UP→correct) = 3 of 5
    assert cmp.llm.n_correct == 3
    assert cmp.llm.n_predictions == 5
    # Baseline: UP(correct), DOWN(wrong), UP(correct), DOWN(wrong), None → 2 of 4
    assert cmp.baseline.n_correct == 2
    assert cmp.baseline.n_predictions == 4
    expected_edge = (3 / 5 - 2 / 4) * 100
    assert cmp.edge_pp == pytest.approx(expected_edge)
