"""Filter agent (Wave 2.5 Task 3).

Born registry-loading: constructed with a loaded `filter@v1` skill and drives
R1–R4 + C1–C3 from that content. NO inline thresholds — the R2 liquidity floors
and R4 freshness window are parsed from the loaded skill (skill_params). Pure
rule-based; ZERO LLM calls (skill C3).

Validates each watchlist entry:
  R1: market open for the asset type (Clock seam).
  R2: liquidity ≥ the skill's per-asset-class floor (TradingClient seam).
  R3: symbol not already in an open paper position (portfolio).
  R4: last quote fresher than the skill's window (Clock + MarketData).
Survivors → tradeable_assets; rejects → skip_reasons with the failed criterion
(C1 completeness: every entry lands in exactly one bucket; C2: skip names the
criterion).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from paper_trader.agents.skill_params import (
    filter_liquidity_floors,
    filter_quote_freshness_minutes,
)
from paper_trader.data.interfaces import Clock, MarketDataProvider, TradingClient
from paper_trader.graph.state import CycleState


class FilterAgent:
    name = "filter"
    writes = ["tradeable_assets", "skip_reasons"]

    def __init__(
        self,
        skill: Any,
        *,
        clock: Clock,
        market_data: MarketDataProvider,
        trading_client: TradingClient,
    ):
        self.skill = skill
        self.clock = clock
        self.market_data = market_data
        self.trading_client = trading_client
        # Effective parameters come from the loaded skill, not from code.
        self.stock_floor, self.crypto_floor = filter_liquidity_floors(skill)
        self.freshness_minutes = filter_quote_freshness_minutes(skill)

    async def run(self, state: CycleState) -> CycleState:
        open_symbols = {p.symbol for p in state.portfolio.open_positions}
        tradeable = []
        skips = dict(state.skip_reasons)

        for asset in state.watchlist:
            reason = await self._first_failed_criterion(asset, open_symbols)
            if reason is None:
                tradeable.append(asset)
            else:
                skips[asset.symbol] = reason  # C2: the specific failed criterion

        state.tradeable_assets = tradeable
        state.skip_reasons = skips  # C1: every entry is now in exactly one bucket
        return state

    async def _first_failed_criterion(self, asset: Any, open_symbols: set[str]) -> str | None:
        # R1: market open for the asset type.
        if not self.clock.is_market_open(asset.kind):
            return "market_closed"

        # R2: liquidity ≥ the skill's floor for this asset class.
        floor = self.stock_floor if asset.kind == "stock" else self.crypto_floor
        liquidity = await self.trading_client.get_liquidity_metric(asset.symbol, asset.kind)
        if liquidity < floor:
            return "insufficient_liquidity"

        # R3: not already in an open paper position.
        if asset.symbol in open_symbols:
            return "already_in_position"

        # R4: last quote fresher than the skill's window.
        bars = await self.market_data.get_ohlcv(asset.symbol, period_days=1)
        if not bars:
            return "no_recent_quote"
        latest = max(b.timestamp for b in bars)
        if self.clock.now() - latest > timedelta(minutes=self.freshness_minutes):
            return "stale_quote"

        return None
