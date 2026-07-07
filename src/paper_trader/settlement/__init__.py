"""Trade settlement (Live-Operation T4).

At or past a prediction's horizon (``expected_exit_time``), close the position at
the then-current price, compute realized P&L, and hand the settling trades to
PostMortem so it scores hit/miss AND the momentum baseline shadow. Without this,
trades never close and there is no "result" to see.

Neutrality (authority §3 T4): settlement is DOMAIN scoring — app-db only, NEVER
Store B. The paper_trades table is a mutable domain table; marking a trade settled
is an ordinary UPDATE, not a governance-ledger write.
"""

from __future__ import annotations

from paper_trader.settlement.engine import (
    SettlementContext,
    SettlementResult,
    settle_due_trades,
)

__all__ = ["SettlementContext", "SettlementResult", "settle_due_trades"]
