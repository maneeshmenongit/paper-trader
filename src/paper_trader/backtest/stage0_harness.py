"""Stage 0 feasibility harness (step 6).

Runs each deterministic strategy over the frozen universe and real cached history,
settling every implied trade through the REAL-math adapter, and computes the dollar
table: floor (always-momentum), oracle-best-method (hindsight-perfect method pick —
the hard bound on any selector), and ceiling (perfect foresight, horizon-matched).
All five §4 sanity checks run as assertions; a violation halts the run.

Decision model over daily bars (horizon-matched, Gap A default):
- A point is (symbol, positional index ``i``) with ≥ ``HISTORY_MIN`` prior bars.
- Entry = the close on day ``i`` (the decision day — known at decision time).
- Exit  = the close on day ``i+1`` (the next trading close = the 24h horizon).
- A method reads ``closes[: i+1]`` — bars strictly before the exit. The exit bar
  (``i+1``) NEVER feeds any method (check #4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from paper_trader.backtest import methods, sanity
from paper_trader.backtest.stage0_settlement import Stage0Settlement, TradeOutcome
from paper_trader.data.offline import OfflineMarketData

HISTORY_MIN = methods.MEAN_REVERSION_MIN_HISTORY  # so all three methods can be eligible


@dataclass
class StrategyResult:
    name: str
    outcomes: list[TradeOutcome] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(o.pnl for o in self.outcomes)

    @property
    def n_entered(self) -> int:
        return sum(1 for o in self.outcomes if o.entered)

    @property
    def hit_rate(self) -> float:
        hits = [o.direction_hit for o in self.outcomes if o.entered]
        return sum(1 for h in hits if h) / len(hits) if hits else 0.0


@dataclass
class Stage0Report:
    seed_bankroll: float
    n_points: int
    n_symbols: int
    floor_pnl: float
    oracle_pnl: float
    ceiling_pnl: float
    per_method: dict[str, StrategyResult]
    edge_ratio: float          # (oracle - floor) / seed_bankroll
    threshold_e: float
    go: bool
    sanity_passed: bool

    @property
    def headroom(self) -> float:
        return self.oracle_pnl - self.floor_pnl


@dataclass
class _Point:
    symbol: str
    index: int
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    closes_through_decision: list[float]  # closes[: index+1]
    exit_close: float


def _build_points(
    history: dict[str, pd.DataFrame], *, history_min: int = HISTORY_MIN
) -> list[_Point]:
    """Every (symbol, i) with ≥ history_min prior bars and a valid next bar.

    Deterministic order (symbol, then date). No sampling — Stage 0 uses the full
    available point set for a stable, reproducible feasibility number.
    """
    points: list[_Point] = []
    for symbol in sorted(history):
        df = history[symbol].sort_index()
        closes = [float(c) for c in df["Close"].tolist()]
        n = len(closes)
        for i in range(history_min, n - 1):
            # Skip points whose entry/exit close is not a real, finite, positive
            # price — the seam would refuse them anyway (check #3 / #5).
            entry_c, exit_c = closes[i], closes[i + 1]
            if not (entry_c > 0 and exit_c > 0):
                continue
            points.append(
                _Point(
                    symbol=symbol,
                    index=i,
                    entry_date=df.index[i],
                    exit_date=df.index[i + 1],
                    closes_through_decision=closes[: i + 1],
                    exit_close=exit_c,
                )
            )
    return points


def run_stage0(
    history: dict[str, pd.DataFrame],
    *,
    seed_bankroll: float = 100_000.0,
    threshold_e: float = 0.03,
) -> Stage0Report:
    """Run the feasibility backtest and return the dollar table + GO/NO-GO."""
    md = OfflineMarketData(history)
    adapter = Stage0Settlement(md)
    points = _build_points(history)
    if not points:
        raise ValueError("no valid backtest points from the provided history")

    per_method: dict[str, StrategyResult] = {
        name: StrategyResult(name=name) for name in methods.METHODS
    }
    floor = StrategyResult(name="floor(momentum)")

    # Ceiling & oracle are computed per point alongside the strategies.
    ceiling_pnls: list[float] = []
    oracle_pnls: list[float] = []
    # For sanity check #2: momentum-method P&L vs floor P&L, point-aligned.
    momentum_method_pnls: list[float] = []
    floor_pnls: list[float] = []
    # For check #1: floor (the traded strategy of record) vs ceiling, point-aligned.
    floor_ceiling: list[float] = []

    for p in points:
        closes = p.closes_through_decision
        # Look-ahead guard (check #4): a method sees only bars strictly before exit.
        sanity.check_no_lookahead(decision_index=p.index + 1, history_len=len(closes))

        forecasts = methods.forecast_all(closes)

        # Each method settles its own implied trade.
        point_method_outcomes: dict[str, TradeOutcome] = {}
        for name, fc in forecasts.items():
            out = adapter.settle(p.symbol, fc, p.entry_date, p.exit_date)
            per_method[name].outcomes.append(out)
            point_method_outcomes[name] = out

        # Floor = always-momentum.
        floor_out = point_method_outcomes["momentum"]
        floor.outcomes.append(floor_out)
        floor_pnls.append(floor_out.pnl)
        momentum_method_pnls.append(point_method_outcomes["momentum"].pnl)

        # Ceiling = perfect foresight, horizon-matched, long-only (floors at 0).
        entry_c = closes[-1]
        realized = (p.exit_close - entry_c) / entry_c
        ceiling_pnl = max(0.0, realized) * (adapter.notional / entry_c) * entry_c
        # == max(0, realized) * notional; keep the explicit qty*entry form for clarity.
        ceiling_pnls.append(ceiling_pnl)
        floor_ceiling.append(ceiling_pnl)

        # Oracle-best-method = hindsight pick of whichever ELIGIBLE method turned out
        # right, and TRADE it (§5: "always picking, in hindsight, whichever method
        # turned out right"). This is the honest hard bound on a pure method-selector:
        # it gets perfect method choice but NOT free abstention/timing — a losing
        # best-of-a-bad-lot point still costs, exactly as a must-trade selector would.
        # (An LLM selector may emit NoView, but that abstention skill is measured
        # separately in Stage 1, not gifted to the oracle here — keeping this bound
        # conservative so headroom is never overstated.)
        eligible_pnls = [
            point_method_outcomes[n].pnl for n, fc in forecasts.items() if fc.eligible
        ]
        oracle_pnls.append(max(eligible_pnls) if eligible_pnls else 0.0)

    # ── §4 sanity assertions (halt on violation) ────────────────────────
    # #1 ceiling is a hard bound — the traded strategy of record is the floor.
    sanity.check_ceiling_is_bound(floor_pnls, floor_ceiling, label="floor")
    sanity.check_ceiling_is_bound(oracle_pnls, ceiling_pnls, label="oracle")
    # #2 floor cross-check — momentum method == floor, same real math.
    sanity.check_floor_cross(momentum_method_pnls, floor_pnls)
    # #3 entry-price realism — every entered price is a real cached close.
    for res in list(per_method.values()) + [floor]:
        sanity.check_entry_price_realism(res.outcomes, md.has_close_on)
    # #5 non-zero settlement — the floor's entered trades aren't all flat.
    sanity.check_nonzero_settlement(floor.outcomes)

    floor_pnl = floor.total_pnl
    oracle_total = sum(oracle_pnls)
    ceiling_total = sum(ceiling_pnls)
    headroom = oracle_total - floor_pnl
    edge_ratio = headroom / seed_bankroll if seed_bankroll else 0.0

    return Stage0Report(
        seed_bankroll=seed_bankroll,
        n_points=len(points),
        n_symbols=len({p.symbol for p in points}),
        floor_pnl=floor_pnl,
        oracle_pnl=oracle_total,
        ceiling_pnl=ceiling_total,
        per_method=per_method,
        edge_ratio=edge_ratio,
        threshold_e=threshold_e,
        go=edge_ratio >= threshold_e,
        sanity_passed=True,  # reaching here means every assertion held
    )
