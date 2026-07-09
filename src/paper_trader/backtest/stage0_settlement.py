"""Stage 0 settlement adapter — a THIN wrapper over the REAL math (step 4).

Per STAGE0_BUILD_PROMPT §1: this contains **no P&L or horizon arithmetic of its
own**. It imports the real functions —

- ``analytics.pnl.realized_pnl`` / ``actual_move_fraction`` (the ONE P&L path,
  shared with the live PostMortem loop),
- ``analytics.direction_score.direction_correct`` (the ONE hit/miss path),
- ``settlement.engine.horizon_exit_time`` (the real horizon shape) —

and drives them over cached offline data via the fixed ``OfflineMarketData`` seam.
Sanity check #2 (floor cross-check) is load-bearing precisely because the momentum
method's P&L flows through these same functions as the momentum floor.

Long-only (§3 fence): a trade is ENTERED iff the forecast direction is ``UP``;
DOWN/HOLD → don't-enter, P&L 0. Direction is carried explicitly — never encoded in
a magnitude sign (guards the -0.0/M12 bug class). Fixed, identical position sizing
across strategies so the METHOD choice, not sizing, drives the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from paper_trader.analytics.direction_score import direction_correct
from paper_trader.analytics.pnl import actual_move_fraction, realized_pnl
from paper_trader.backtest.methods import MethodForecast
from paper_trader.data.offline import OfflineMarketData, OfflineQuoteError
from paper_trader.domain import ForecastDirection
from paper_trader.settlement.engine import horizon_exit_time

# Fixed sizing: every entered trade deploys the same notional, so P&L differences
# come from the method's CHOICE, not from sizing. (Trivial by design, per §3.)
FIXED_NOTIONAL = 1_000.0
HORIZON_HOURS = 24  # v1 horizon; horizon_exit_time uses it (real settlement shape)


@dataclass(frozen=True)
class TradeOutcome:
    """One settled (or not-entered) point for one strategy."""

    symbol: str
    entry_date: datetime
    exit_date: datetime
    entered: bool                       # False for a DOWN/HOLD (long-only don't-enter)
    direction: ForecastDirection
    entry_price: float | None           # None when not entered
    exit_price: float | None
    quantity: float
    pnl: float                          # realized P&L in fake dollars (0 if not entered)
    direction_hit: bool | None          # None when not entered
    actual_move_pct: float | None       # realized move %, None when not entered


class Stage0Settlement:
    """Drives the real math over cached closes. No arithmetic of its own beyond
    computing ``quantity = notional / entry_price`` (position construction, not
    P&L) — the P&L, move, and hit/miss all come from ``analytics/*``.
    """

    def __init__(self, market_data: OfflineMarketData, *, notional: float = FIXED_NOTIONAL):
        self.market_data = market_data
        self.notional = notional

    def settle(
        self,
        symbol: str,
        forecast: MethodForecast,
        entry_date: datetime,
        exit_date: datetime,
    ) -> TradeOutcome:
        """Settle one point: enter iff UP, price entry/exit from the real seam,
        score via the real math. Prices are REAL cached closes (the seam raises
        OfflineQuoteError on a missing/NaN/zero close — never a fabricated price).
        """
        # Long-only: only an UP forecast enters. DOWN/HOLD → don't-enter, P&L 0.
        if not forecast.eligible or forecast.direction != "UP":
            return TradeOutcome(
                symbol=symbol, entry_date=entry_date, exit_date=exit_date,
                entered=False, direction=forecast.direction,
                entry_price=None, exit_price=None, quantity=0.0, pnl=0.0,
                direction_hit=None, actual_move_pct=None,
            )

        entry_price = self.market_data.close_on(symbol, entry_date)
        exit_price = self.market_data.close_on(symbol, exit_date)
        # entry_price is guaranteed > 0 and finite by the seam guard.
        quantity = self.notional / entry_price

        # REAL math — the same functions the live PostMortem loop calls.
        pnl = realized_pnl(entry_price, exit_price, quantity)
        move = actual_move_fraction(entry_price, exit_price)
        hit = direction_correct(entry_price, exit_price)

        return TradeOutcome(
            symbol=symbol, entry_date=entry_date, exit_date=exit_date,
            entered=True, direction="UP",
            entry_price=entry_price, exit_price=exit_price, quantity=quantity,
            pnl=pnl, direction_hit=hit, actual_move_pct=move * 100.0,
        )


def horizon_exit_datetime(entry_date: datetime) -> datetime:
    """The horizon exit time for an entry, via the REAL settlement shape.

    Delegates to ``settlement.engine.horizon_exit_time`` (no arithmetic here). The
    harness resolves this wall-clock horizon to the nearest available cached
    trading day; over daily bars the horizon-matched exit is the next trading close.
    """
    return horizon_exit_time(entry_date, HORIZON_HOURS)


__all__ = [
    "FIXED_NOTIONAL",
    "Stage0Settlement",
    "TradeOutcome",
    "horizon_exit_datetime",
    "OfflineQuoteError",
]
