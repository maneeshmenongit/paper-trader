"""Cheap ex-ante null selectors (Stage 1 step 2).

STAGE1_BUILD_PROMPT §1: Stage 0's headroom is a HINDSIGHT bound. The real bar the
LLM must clear is a cheap selector that uses only information available at decision
time. Two are defined here:

- ``null_selector`` — per point, among the ELIGIBLE methods, pick the one with the
  best TRAILING realized performance over points whose horizon closed STRICTLY
  BEFORE the decision date. Purely ex-ante; no look-ahead. This is the "does a
  5-line rule already capture the edge?" bar.
- ``random_among_eligible`` — a seeded random pick among eligible methods. The
  reference sub-floor: if the LLM can't beat random, the thesis is dead on arrival.

Both are scored through the SAME real-math adapter as every other strategy — these
modules choose a method; they do not compute P&L.

The fusion-trap guard (§2.3) is structural here: the scoreboard only ever ingests a
point's outcome AFTER that point's horizon has closed, and the selector reads the
scoreboard as-of the decision date, so a point can never inform its own selection.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from paper_trader.backtest.methods import MethodForecast

# Trailing metric: hit rate (fraction of that method's past entered trades that were
# directionally correct). Ties broken by realized-P&L, then by a fixed method order
# for full determinism.
_METHOD_ORDER = {"momentum": 0, "mean_reversion": 1, "arima": 2}


@dataclass
class _MethodRecord:
    entered: int = 0
    hits: int = 0
    realized_pnl: float = 0.0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.entered if self.entered else 0.0


@dataclass
class TrailingScoreboard:
    """Per-method running track record, fed only by CLOSED points.

    The harness calls ``record_closed`` for a point strictly after another point's
    decision consumes it, so the scoreboard a selection sees never includes the
    current point (or any point whose horizon closes on/after this decision date).
    """

    _by_method: dict[str, _MethodRecord] = field(default_factory=dict)

    def record_closed(
        self, method: str, *, entered: bool, hit: bool, pnl: float
    ) -> None:
        """Ingest one CLOSED outcome for a method (only entered trades count)."""
        rec = self._by_method.setdefault(method, _MethodRecord())
        if entered:
            rec.entered += 1
            rec.hits += 1 if hit else 0
            rec.realized_pnl += pnl

    def best_among(self, eligible: list[str]) -> str | None:
        """The eligible method with the best trailing record, or None if there is
        no trailing evidence yet for ANY eligible method (cold start).

        Ranking: higher hit rate, then higher realized P&L, then fixed method order.
        A method with zero trailing entered trades ranks below any with evidence.
        """
        scored = [m for m in eligible if self._by_method.get(m, _MethodRecord()).entered > 0]
        if not scored:
            return None
        return max(
            scored,
            key=lambda m: (
                self._by_method[m].hit_rate,
                self._by_method[m].realized_pnl,
                -_METHOD_ORDER.get(m, 99),
            ),
        )


@dataclass(frozen=True)
class Selection:
    """A selector's choice for one point."""

    method: str | None          # None → abstain / don't-enter (no eligible pick)
    selection_mode: str          # "rule" | "llm" | "random" | "cold_start"
    rationale: str | None = None


def eligible_methods(forecasts: dict[str, MethodForecast]) -> list[str]:
    """The eligible method names for a point, in fixed order (deterministic)."""
    return sorted(
        (m for m, fc in forecasts.items() if fc.eligible),
        key=lambda m: _METHOD_ORDER.get(m, 99),
    )


def null_select(
    forecasts: dict[str, MethodForecast],
    scoreboard: TrailingScoreboard,
) -> Selection:
    """Ex-ante trailing-performance pick among eligible methods.

    Cold start (no trailing evidence for any eligible method) falls back to the
    first eligible method in fixed order — a deterministic, ex-ante default (NOT a
    hindsight pick). Zero eligible → abstain.
    """
    elig = eligible_methods(forecasts)
    if not elig:
        return Selection(method=None, selection_mode="rule", rationale="no_eligible")
    best = scoreboard.best_among(elig)
    if best is None:
        return Selection(method=elig[0], selection_mode="cold_start",
                         rationale="no_trailing_evidence")
    return Selection(method=best, selection_mode="rule", rationale="best_trailing")


def random_select(
    forecasts: dict[str, MethodForecast],
    rng: random.Random,
) -> Selection:
    """Seeded random pick among eligible methods (the reference sub-floor)."""
    elig = eligible_methods(forecasts)
    if not elig:
        return Selection(method=None, selection_mode="random", rationale="no_eligible")
    return Selection(method=rng.choice(elig), selection_mode="random")


def horizon_closed_before(exit_date: datetime, decision_date: datetime) -> bool:
    """True iff a point's horizon (its exit) closed strictly before ``decision_date``.

    The harness uses this to decide whether a past point may feed the scoreboard for
    the current decision — the ex-ante / no-look-ahead contract (§2.3).
    """
    return exit_date < decision_date
