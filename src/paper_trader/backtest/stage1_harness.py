"""Stage 1 LLM-selector backtest harness (step 4).

Runs five strategies over the frozen Stage 0 universe and point set, all scored
through the SAME real-math adapter (no new P&L/horizon math here):

- ``always_momentum``       — the inherited floor.
- ``null_selector``         — ex-ante trailing-performance pick (the real bar).
- ``random_among_eligible`` — seeded reference sub-floor.
- ``llm_selector``          — the R4 LLM path (injected; stubbable for tests).

plus the hindsight ``oracle_best_method`` and ``ceiling`` for band context.

Chronology is load-bearing for the null selector (§2.3): points are processed in
global DECISION-DATE order, and a point may feed the trailing scoreboard only once
its horizon has closed STRICTLY BEFORE the current decision date. A pending queue
enforces this — a point can never inform its own (or a same-day) selection.

The verdict (§6) measures the LLM edge over ``max(always_momentum, null_selector)``
in return-on-bankroll terms, and is SUCCEEDED / FAILED / INCONCLUSIVE.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pandas as pd

from paper_trader.backtest import methods, sanity
from paper_trader.backtest.llm_selector import LLMSelector, MaxCallsExceededError
from paper_trader.backtest.null_selector import (
    Selection,
    TrailingScoreboard,
    horizon_closed_before,
    null_select,
    random_select,
)
from paper_trader.backtest.stage0_harness import HISTORY_MIN, _build_points, _Point
from paper_trader.backtest.stage0_settlement import Stage0Settlement, TradeOutcome
from paper_trader.data.offline import OfflineMarketData

# Diversity floors (§5) for the LLM path to be judgeable.
MIN_SYMBOLS = 20
MIN_DECISION_DATES = 130
# Minimum settled LLM points to render a non-INCONCLUSIVE verdict (§6).
MIN_LLM_SETTLED = 100


@dataclass
class StrategyTally:
    name: str
    outcomes: list[TradeOutcome] = field(default_factory=list)
    selections: list[Selection] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(o.pnl for o in self.outcomes)

    @property
    def n_entered(self) -> int:
        return sum(1 for o in self.outcomes if o.entered)

    @property
    def n_abstained(self) -> int:
        return sum(1 for s in self.selections if s.method is None)


@dataclass
class Stage1Report:
    seed_bankroll: float
    n_points: int
    n_symbols: int
    threshold_e: float
    floor_momentum_pnl: float
    null_pnl: float
    random_pnl: float
    llm_pnl: float
    oracle_pnl: float
    ceiling_pnl: float
    effective_floor_pnl: float
    llm_edge: float                 # llm_pnl - effective_floor_pnl
    llm_edge_ratio: float           # / seed_bankroll
    headroom_capture: float         # llm_edge / (oracle - effective_floor), clipped
    llm_settled: int
    llm_llm_path_points: int        # points that actually hit the LLM (≥2 eligible)
    llm_distinct_symbols: int
    llm_distinct_dates: int
    llm_abstain_rate: float
    llm_calls: int
    llm_cache_hits: int
    llm_tokens: int
    verdict: str                    # SUCCEEDED | FAILED | INCONCLUSIVE | INCOMPLETE
    sanity_passed: bool
    sampled: bool = False           # True → LLM ran on a subsample of points
    llm_points_evaluated: int = 0   # points the LLM path actually evaluated
    incomplete_reason: str | None = None


def _settle_selection(
    adapter: Stage0Settlement,
    point: _Point,
    forecasts: dict[str, methods.MethodForecast],
    sel: Selection,
) -> TradeOutcome:
    """Settle a selector's chosen method through the real-math adapter (abstain →
    don't-enter). No arithmetic here — the adapter carries the real math."""
    fc = (
        methods.MethodForecast.ineligible()
        if sel.method is None
        else forecasts[sel.method]
    )
    return adapter.settle(point.symbol, fc, point.entry_date, point.exit_date)


def _ordered_points(history: dict[str, pd.DataFrame]) -> list[_Point]:
    """All Stage 0 points, globally ordered by decision date then symbol."""
    pts = _build_points(history)
    return sorted(pts, key=lambda p: (p.entry_date, p.symbol))


def _point_id(p: _Point) -> tuple[str, object]:
    """Stable identity for a point (symbol, decision-date)."""
    return (p.symbol, pd.Timestamp(p.entry_date).normalize())


def select_sample(
    points: list[_Point], *, target: int, seed: int = 42
) -> set[tuple[str, object]]:
    """A date-stratified sample of ~``target`` point-ids for the LLM path.

    Stratifying by decision-date (not truncating chronologically) preserves the
    full date range and symbol spread so §5's diversity floors can be met on a
    fraction of the calls. Every non-sampled point still feeds the floor / null /
    random / oracle strategies and the trailing scoreboard — only the (expensive)
    LLM call is subsampled. Deterministic given ``seed``.
    """
    if target <= 0 or target >= len(points):
        return {_point_id(p) for p in points}
    rng = random.Random(seed)
    by_date: dict[pd.Timestamp, list[_Point]] = {}
    for p in points:
        by_date.setdefault(pd.Timestamp(p.entry_date).normalize(), []).append(p)
    dates = sorted(by_date)
    per_date = max(1, target // len(dates))
    chosen: set[tuple[str, object]] = set()
    for d in dates:
        bucket = by_date[d]
        rng.shuffle(bucket)
        for p in bucket[:per_date]:
            chosen.add(_point_id(p))
    # Top up (or trim) toward the target from a global shuffle for stability.
    if len(chosen) < target:
        pool = [p for p in points if _point_id(p) not in chosen]
        rng.shuffle(pool)
        for p in pool:
            if len(chosen) >= target:
                break
            chosen.add(_point_id(p))
    return chosen


def run_stage1(
    history: dict[str, pd.DataFrame],
    llm_selector: LLMSelector,
    *,
    seed_bankroll: float = 100_000.0,
    threshold_e: float = 0.03,
    random_seed: int = 42,
    sample_llm_points: set[tuple[str, object]] | None = None,
) -> Stage1Report:
    md = OfflineMarketData(history)
    adapter = Stage0Settlement(md)
    points = _ordered_points(history)
    if not points:
        raise ValueError("no valid backtest points from the provided history")

    momentum = StrategyTally("always_momentum")
    null = StrategyTally("null_selector")
    rnd = StrategyTally("random_among_eligible")
    llm = StrategyTally("llm_selector")
    rng = random.Random(random_seed)
    scoreboard = TrailingScoreboard()

    # Pending queue: (exit_date, method, outcome) for null-selector points not yet
    # closed. Flushed into the scoreboard once exit_date < current decision date.
    pending: list[tuple[pd.Timestamp, str, TradeOutcome]] = []

    # For sanity checks and verdict.
    momentum_pnls: list[float] = []
    floor_ceiling: list[float] = []
    ceiling_pnls: list[float] = []
    oracle_pnls: list[float] = []
    llm_settled = 0
    llm_path_points = 0
    llm_symbols: set[str] = set()
    llm_dates: set[pd.Timestamp] = set()
    # Sampled-subset sums so the verdict compares LLM vs floor/null/oracle over the
    # SAME points (fair when sampling; identical to the full sums when not).
    s_momentum = s_null = s_oracle = 0.0

    try:
        for p in points:
            closes = p.closes_through_decision
            sanity.check_no_lookahead(decision_index=p.index + 1, history_len=len(closes))

            # Flush closed points into the trailing scoreboard (ex-ante, strict).
            still_pending = []
            for exit_date, method, out in pending:
                if horizon_closed_before(exit_date, p.entry_date):
                    scoreboard.record_closed(
                        method, entered=out.entered,
                        hit=bool(out.direction_hit), pnl=out.pnl,
                    )
                else:
                    still_pending.append((exit_date, method, out))
            pending = still_pending

            forecasts = methods.forecast_all(closes)

            # always_momentum (floor of record).
            mom_out = adapter.settle(p.symbol, forecasts["momentum"], p.entry_date, p.exit_date)
            momentum.outcomes.append(mom_out)
            momentum_pnls.append(mom_out.pnl)

            # null_selector.
            null_sel = null_select(forecasts, scoreboard)
            null_out = _settle_selection(adapter, p, forecasts, null_sel)
            null.outcomes.append(null_out)
            null.selections.append(null_sel)
            # Queue this point's REALIZED outcome for the scoreboard (future dates only).
            if null_sel.method is not None:
                pending.append((p.exit_date, null_sel.method, null_out))

            # random_among_eligible.
            rnd_sel = random_select(forecasts, rng)
            rnd.outcomes.append(_settle_selection(adapter, p, forecasts, rnd_sel))
            rnd.selections.append(rnd_sel)

            # ceiling & oracle (band context) — computed before the LLM block so the
            # per-point oracle can feed the sampled-subset comparison.
            entry_c = closes[-1]
            realized = (p.exit_close - entry_c) / entry_c
            ceiling_pnl = max(0.0, realized) * adapter.notional
            ceiling_pnls.append(ceiling_pnl)
            floor_ceiling.append(ceiling_pnl)
            elig_pnls = [
                adapter.settle(p.symbol, forecasts[n], p.entry_date, p.exit_date).pnl
                for n, fc in forecasts.items() if fc.eligible
            ]
            oracle_pnl = max(elig_pnls) if elig_pnls else 0.0
            oracle_pnls.append(oracle_pnl)

            # llm_selector — only on sampled points (if a sample is given). A
            # non-sampled point is skipped for the LLM path entirely (no call, not
            # counted); it still contributes to every other strategy + the scoreboard.
            if sample_llm_points is None or _point_id(p) in sample_llm_points:
                llm_sel = llm_selector.select(p.symbol, forecasts, closes, p.entry_date)
                llm_out = _settle_selection(adapter, p, forecasts, llm_sel)
                llm.outcomes.append(llm_out)
                llm.selections.append(llm_sel)
                # Same-point sums for a fair sampled comparison.
                s_momentum += mom_out.pnl
                s_null += null_out.pnl
                s_oracle += oracle_pnl
                if llm_sel.selection_mode == "llm":
                    llm_path_points += 1
                    llm_symbols.add(p.symbol)
                    llm_dates.add(pd.Timestamp(p.entry_date).normalize())
                    if llm_out.entered:
                        llm_settled += 1
    except MaxCallsExceededError as exc:
        return _incomplete_report(seed_bankroll, threshold_e, len(points), str(exc))

    # ── sanity assertions ───────────────────────────────────────────────
    sanity.check_ceiling_is_bound(momentum_pnls, floor_ceiling, label="momentum")
    sanity.check_ceiling_is_bound(oracle_pnls, ceiling_pnls, label="oracle")
    sanity.check_floor_cross(momentum_pnls, [o.pnl for o in momentum.outcomes])
    for tally in (momentum, null, rnd, llm):
        sanity.check_entry_price_realism(tally.outcomes, md.has_close_on)
    sanity.check_nonzero_settlement(momentum.outcomes)

    # Full-universe totals (dollar table / band context).
    floor_pnl = momentum.total_pnl
    null_pnl = null.total_pnl
    oracle_total = sum(oracle_pnls)
    llm_pnl = llm.total_pnl

    # Verdict is measured over the SAME points the LLM actually ran on — the sampled
    # subset when sampling, else the full set (s_* == full sums then). This keeps the
    # edge honest: LLM vs floor/null/oracle on identical points.
    sampled = sample_llm_points is not None
    v_floor = s_momentum if sampled else floor_pnl
    v_null = s_null if sampled else null_pnl
    v_oracle = s_oracle if sampled else oracle_total
    effective_floor = max(v_floor, v_null)
    llm_edge = llm_pnl - effective_floor
    denom = v_oracle - effective_floor
    capture = (llm_edge / denom) if denom > 0 else 0.0

    verdict = _verdict(
        llm_edge_ratio=llm_edge / seed_bankroll,
        threshold_e=threshold_e,
        llm_pnl=llm_pnl,
        null_pnl=v_null,
        llm_settled=llm_settled,
        n_symbols=len(llm_symbols),
        n_dates=len(llm_dates),
    )

    return Stage1Report(
        seed_bankroll=seed_bankroll,
        n_points=len(points),
        n_symbols=len({p.symbol for p in points}),
        threshold_e=threshold_e,
        floor_momentum_pnl=floor_pnl,
        null_pnl=null_pnl,
        random_pnl=rnd.total_pnl,
        llm_pnl=llm_pnl,
        oracle_pnl=oracle_total,
        ceiling_pnl=sum(ceiling_pnls),
        effective_floor_pnl=effective_floor,
        llm_edge=llm_edge,
        llm_edge_ratio=llm_edge / seed_bankroll,
        headroom_capture=capture,
        llm_settled=llm_settled,
        llm_llm_path_points=llm_path_points,
        llm_distinct_symbols=len(llm_symbols),
        llm_distinct_dates=len(llm_dates),
        llm_abstain_rate=(llm.n_abstained / len(llm.outcomes)) if llm.outcomes else 0.0,
        llm_calls=llm_selector.stats.calls,
        llm_cache_hits=llm_selector.stats.cache_hits,
        llm_tokens=llm_selector.stats.tokens,
        verdict=verdict,
        sanity_passed=True,
        sampled=sampled,
        llm_points_evaluated=len(llm.outcomes),
    )


def _verdict(
    *, llm_edge_ratio: float, threshold_e: float, llm_pnl: float, null_pnl: float,
    llm_settled: int, n_symbols: int, n_dates: int,
) -> str:
    # INCONCLUSIVE first: insufficient coverage or too few settled points (§6).
    if (llm_settled < MIN_LLM_SETTLED or n_symbols < MIN_SYMBOLS
            or n_dates < MIN_DECISION_DATES):
        return "INCONCLUSIVE"
    # FAILED if it can't even beat the null selector, or edge < E.
    if llm_pnl < null_pnl or llm_edge_ratio < threshold_e:
        return "FAILED"
    return "SUCCEEDED"


def _incomplete_report(
    seed_bankroll: float, threshold_e: float, n_points: int, reason: str
) -> Stage1Report:
    return Stage1Report(
        seed_bankroll=seed_bankroll, n_points=n_points, n_symbols=0,
        threshold_e=threshold_e, floor_momentum_pnl=0.0, null_pnl=0.0, random_pnl=0.0,
        llm_pnl=0.0, oracle_pnl=0.0, ceiling_pnl=0.0, effective_floor_pnl=0.0,
        llm_edge=0.0, llm_edge_ratio=0.0, headroom_capture=0.0, llm_settled=0,
        llm_llm_path_points=0, llm_distinct_symbols=0, llm_distinct_dates=0,
        llm_abstain_rate=0.0, llm_calls=0, llm_cache_hits=0, llm_tokens=0,
        verdict="INCOMPLETE", sanity_passed=False, incomplete_reason=reason,
    )


__all__ = ["Stage1Report", "run_stage1", "HISTORY_MIN"]
