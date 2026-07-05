"""Predict agent — PROVISIONAL, momentum-only (Wave 2.5 Task 7).

Born registry-loading (predict@v1). Emits the G6 View/NoView union — NEVER a
DirectionalPrediction. Runs the rules-first method selector from the loaded skill.

PROVISIONAL SCOPE: the skill's declared method roster is {momentum, mean_reversion,
arima}, but only `momentum` is implemented in this wave — enough to close the loop.
The agent READS the full declared roster from the skill and REPORTS it
(`declared_roster`), but only momentum is ever eligible. Consequence: with a single
implemented method, R3 (exactly one eligible → rule-select) is the operative path
and R4 (multiple eligible → LLM selection) never fires yet. No LLM call is needed
for momentum. Building the rest of the roster + the LLM selector is a later step.

  R1: a method lacking its minimum input history is ineligible this invocation.
  R2: zero eligible methods → NoView(no_eligible_method).
  R3: exactly one eligible method → select it; selection_mode: rule.
  R4: multiple eligible → escalate to LLM selection (NOT reachable provisionally).
  C1: a View requires confidence ≥ 0.60; below → NoView(below_confidence_threshold).
  C4: the momentum baseline shadow is computed for every researched symbol,
      independent of selection, tagged is_baseline.
"""

from __future__ import annotations

import re
from typing import Any

from paper_trader.domain import ForecastDirection, NoView, View
from paper_trader.graph.state import CycleState

# The one method implemented this wave. Its declared minimum input history: the
# momentum baseline needs the two prior closes (yesterday vs the day before).
IMPLEMENTED_METHODS = {"momentum"}
MOMENTUM_MIN_HISTORY = 2


class PredictAgent:
    name = "predict"
    writes = ["predictions", "baseline_predictions"]

    def __init__(self, skill: Any, *, confidence_threshold: float | None = None):
        self.skill = skill
        # The declared roster is READ from the skill and reported — not invented.
        self.declared_roster = [m["name"] for m in skill["methods"]["roster"]]
        self.implemented = [m for m in self.declared_roster if m in IMPLEMENTED_METHODS]
        # C1 threshold parsed from the loaded skill (default 0.60 if absent).
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else _parse_confidence_threshold(skill)
        )

    def unimplemented_roster(self) -> list[str]:
        """Declared-but-not-built methods (reported, not silently dropped)."""
        return [m for m in self.declared_roster if m not in IMPLEMENTED_METHODS]

    async def run(self, state: CycleState) -> CycleState:
        predictions = dict(state.predictions)
        baselines = dict(state.baseline_predictions)

        for symbol, bundle in state.research_bundles.items():
            closes = _closes(bundle)

            # C4: momentum baseline shadow, every symbol, independent of selection.
            baseline = self._baseline_view(symbol, closes)
            if baseline is not None:
                baselines[symbol] = baseline

            predictions[symbol] = self._predict_one(symbol, closes)

        state.predictions = predictions
        state.baseline_predictions = baselines
        return state

    def _predict_one(self, symbol: str, closes: list[float]) -> View | NoView:
        # R1 eligibility: which implemented methods have their minimum history.
        eligible = [
            m for m in self.implemented
            if m == "momentum" and len(closes) >= MOMENTUM_MIN_HISTORY
        ]

        if not eligible:
            return NoView(
                symbol=symbol, reason="no_eligible_method",
                methods_considered=list(self.implemented),
            )

        # R3: exactly one eligible → rule-select it (selection_mode: rule).
        # R4 (multiple → LLM) is unreachable provisionally (one method only).
        method = eligible[0]
        direction, magnitude, confidence = _momentum(closes)

        # C1: below the confidence threshold → NoView (never a low-confidence View).
        if confidence < self.confidence_threshold:
            return NoView(symbol=symbol, reason="below_confidence_threshold",
                          methods_considered=eligible)

        return View(
            symbol=symbol,
            method_selected=method,          # 'momentum'
            selection_mode="rule",           # C3: no rationale (rationale iff llm)
            selection_rationale=None,
            direction=direction,
            magnitude_pct=magnitude,
            horizon=24,
            confidence=confidence,
            method_inputs_summary={"n_closes": len(closes), "last_close": closes[-1]},
            is_baseline=False,
        )

    def _baseline_view(self, symbol: str, closes: list[float]) -> View | None:
        if len(closes) < MOMENTUM_MIN_HISTORY:
            return None
        direction, magnitude, confidence = _momentum(closes)
        return View(
            symbol=symbol, method_selected="momentum", selection_mode="rule",
            direction=direction, magnitude_pct=magnitude, horizon=24,
            confidence=confidence, is_baseline=True,  # C4: tagged, never traded
            method_inputs_summary={"n_closes": len(closes)},
        )


def _closes(bundle: Any) -> list[float]:
    return [float(bar["close"]) for bar in bundle.ohlcv if "close" in bar]


def _momentum(closes: list[float]) -> tuple[ForecastDirection, float, float]:
    """Prior-move momentum: direction of the last close vs the one before.

    Returns (direction, magnitude_pct, confidence). Same rule as the baseline
    (backtest/baseline.py), mapped into the View payload.
    """
    prev, last = closes[-2], closes[-1]
    move = (last - prev) / prev if prev else 0.0
    direction: ForecastDirection = "UP" if last > prev else "DOWN" if last < prev else "HOLD"
    magnitude = abs(move) * 100.0
    # Provisional confidence proxy: larger relative move → higher confidence,
    # centred so a ~0.5% move sits near the 0.60 gate.
    confidence = min(0.5 + abs(move) * 20.0, 0.99)
    return direction, magnitude, confidence


def _parse_confidence_threshold(skill: Any) -> float:
    for c in skill["constraints"]:
        m = re.search(r"confidence\s*≥\s*([\d.]+)", c["text"])
        if m:
            return float(m.group(1))
    return 0.60
