"""Score predictions against actual next-day moves."""

from __future__ import annotations

from dataclasses import dataclass

from paper_trader.backtest.baseline import Direction
from paper_trader.backtest.sample import PredictionPoint


@dataclass
class EvaluationResult:
    n_predictions: int  # non-HOLD/None predictions scored (the denominator)
    n_correct: int
    hit_rate: float  # n_correct / n_predictions
    n_distinct_symbols: int
    n_distinct_days: int


@dataclass
class ComparisonResult:
    llm: EvaluationResult
    baseline: EvaluationResult
    n_overlapping_predictions: int  # both made a non-HOLD prediction
    n_llm_beat_baseline: int  # LLM correct, baseline incorrect
    n_baseline_beat_llm: int  # baseline correct, LLM incorrect
    n_both_correct: int
    n_both_wrong: int
    edge_pp: float  # (llm.hit_rate - baseline.hit_rate) * 100, in percentage points


def evaluate(
    predictions: list[Direction | None],
    points: list[PredictionPoint],
) -> EvaluationResult:
    """Compute hit rate, dropping HOLD/None predictions from the denominator.

    `predictions[i]` is the predicted direction for `points[i]` (or None for
    HOLD / refused / error). Only non-None predictions count toward the hit rate.
    """
    if len(predictions) != len(points):
        raise ValueError(
            f"predictions ({len(predictions)}) and points ({len(points)}) length mismatch"
        )

    n_predictions = 0
    n_correct = 0
    symbols: set[str] = set()
    days: set = set()

    for pred, point in zip(predictions, points, strict=True):
        if pred is None:
            continue
        n_predictions += 1
        symbols.add(point.symbol)
        days.add(point.prediction_date.normalize())
        if pred == point.actual_direction:
            n_correct += 1

    hit_rate = (n_correct / n_predictions) if n_predictions else 0.0
    return EvaluationResult(
        n_predictions=n_predictions,
        n_correct=n_correct,
        hit_rate=hit_rate,
        n_distinct_symbols=len(symbols),
        n_distinct_days=len(days),
    )


def compare(
    llm_predictions: list[Direction | None],
    baseline_predictions: list[Direction | None],
    points: list[PredictionPoint],
) -> ComparisonResult:
    """Build a head-to-head ComparisonResult.

    Overlap stats are computed only on points where BOTH the LLM and the baseline
    made a non-HOLD prediction.
    """
    llm_result = evaluate(llm_predictions, points)
    baseline_result = evaluate(baseline_predictions, points)

    n_overlap = 0
    n_llm_beat = 0
    n_baseline_beat = 0
    n_both_correct = 0
    n_both_wrong = 0

    for llm_pred, base_pred, point in zip(
        llm_predictions, baseline_predictions, points, strict=True
    ):
        if llm_pred is None or base_pred is None:
            continue
        n_overlap += 1
        llm_ok = llm_pred == point.actual_direction
        base_ok = base_pred == point.actual_direction
        if llm_ok and base_ok:
            n_both_correct += 1
        elif llm_ok and not base_ok:
            n_llm_beat += 1
        elif base_ok and not llm_ok:
            n_baseline_beat += 1
        else:
            n_both_wrong += 1

    edge_pp = (llm_result.hit_rate - baseline_result.hit_rate) * 100.0

    return ComparisonResult(
        llm=llm_result,
        baseline=baseline_result,
        n_overlapping_predictions=n_overlap,
        n_llm_beat_baseline=n_llm_beat,
        n_baseline_beat_llm=n_baseline_beat,
        n_both_correct=n_both_correct,
        n_both_wrong=n_both_wrong,
        edge_pp=edge_pp,
    )
