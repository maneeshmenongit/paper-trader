"""Scheduled run harness (Live-Operation T5).

A local runner that triggers cycles on a schedule (``trigger_kind='schedule'``),
settles due trades BETWEEN cycles, persists domain history, and writes per-cycle
observability. Local-first: it runs on the operator's machine; no VPS.

Bounded + injectable for tests: ``max_cycles`` caps the run, ``sleep`` is
injected so a test drives many cycles with zero real delay and no network. The
portfolio is carried in memory across cycles (updated by settlement's realized
P&L via PostMortem); rehydrating full portfolio state from the app db on restart
is a later refinement (see gate report), out of scope for the harness itself.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paper_trader.domain import Asset, PaperPortfolio, Position
from paper_trader.graph.ids import new_cycle_id
from paper_trader.graph.state import CycleState
from paper_trader.harness.assembly import build_governed_cycle
from paper_trader.harness.observability import write_cycle_artifacts
from paper_trader.persistence.cycle_writer import persist_cycle
from paper_trader.persistence.repository import Repository
from paper_trader.settlement.engine import settle_due_trades

logger = logging.getLogger("paper_trader.harness")


@dataclass
class CycleRunRecord:
    cycle_id: str
    settlements: int
    trades_executed: int
    findings: int
    all_pins_verified: bool


@dataclass
class RunResult:
    cycles: list[CycleRunRecord] = field(default_factory=list)
    final_portfolio: PaperPortfolio | None = None

    @property
    def count(self) -> int:
        return len(self.cycles)


class ScheduledRunner:
    """Drives the settle→cycle→persist→observe loop on a schedule, locally."""

    def __init__(
        self,
        *,
        config: Any,
        providers: Any,
        registry: Any,
        llm_router: Any,
        store_a: Any,
        store_b: Any,
        repo: Repository,
        clock: Any,
        run_dir: Path,
        store_a_path: Path,
        store_b_path: Path,
        registry_path: Path,
        watchlist: list[Asset],
        horizon_hours: int = 24,
        token_budget: int = 15000,
        starting_cash: float = 100_000.0,
        interval_seconds: float = 3600.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.config = config
        self.providers = providers
        self.registry = registry
        self.llm_router = llm_router
        self.store_a = store_a
        self.store_b = store_b
        self.repo = repo
        self.clock = clock
        self.run_dir = run_dir
        self.store_a_path = store_a_path
        self.store_b_path = store_b_path
        self.registry_path = registry_path
        self.watchlist = watchlist
        self.horizon_hours = horizon_hours
        self.token_budget = token_budget
        self.interval_seconds = interval_seconds
        self._sleep = sleep
        # Portfolio carried across cycles (settlement + scoring mutate it).
        self.portfolio = PaperPortfolio(cash_balance=starting_cash)

    async def run(self, *, max_cycles: int) -> RunResult:
        """Run up to ``max_cycles`` cycles, sleeping ``interval`` between them."""
        result = RunResult()
        for i in range(max_cycles):
            record = await self._run_one_cycle()
            result.cycles.append(record)
            logger.info(
                "cycle %s done: settlements=%d trades=%d findings=%d pins_ok=%s",
                record.cycle_id, record.settlements, record.trades_executed,
                record.findings, record.all_pins_verified,
            )
            if i < max_cycles - 1:
                await self._sleep(self.interval_seconds)
        result.final_portfolio = self.portfolio
        return result

    async def _run_one_cycle(self) -> CycleRunRecord:
        # 1) Settle due trades FIRST (between-cycle work), scoring their outcomes.
        settlement = await settle_due_trades(
            repo=self.repo, market_data=self.providers.market_data, clock=self.clock
        )
        # Close settled positions out of the carried portfolio.
        self._apply_settlements(settlement.settled_trades)

        # 2) Build a governed cycle at the CURRENT skill pins, threading the
        #    settlement contexts so PostMortem scores hit/miss + baseline shadow.
        cycle = build_governed_cycle(
            providers=self.providers, registry=self.registry,
            llm_router=self.llm_router, store_a=self.store_a, store_b=self.store_b,
            clock=self.clock, horizon_hours=self.horizon_hours,
            token_budget=self.token_budget,
            settlement_contexts=settlement.contexts,
        )

        state = self._fresh_state(settlement.settled_trades)
        state = await cycle.supervisor.run_cycle(state)

        # 3) Persist domain history (app db only), then carry portfolio forward.
        #    Settlement contexts resolve each post-mortem's trade-row FK.
        persist_cycle(self.repo, state, settlement_contexts=settlement.contexts)
        self._apply_new_trades(state)
        self.portfolio = state.portfolio

        # 4) Observability: replay markdown + observer findings for the cycle.
        obs = write_cycle_artifacts(
            cycle_id=state.cycle_id, run_dir=self.run_dir,
            store_a_path=self.store_a_path, store_b_path=self.store_b_path,
            registry_path=self.registry_path,
        )
        return CycleRunRecord(
            cycle_id=state.cycle_id,
            settlements=settlement.count,
            trades_executed=sum(1 for d in state.trade_decisions.values() if d.executed),
            findings=obs.finding_count,
            all_pins_verified=obs.all_pins_verified,
        )

    def _fresh_state(self, settled: list[Any]) -> CycleState:
        return CycleState(
            cycle_id=new_cycle_id(self.clock),
            started_at=self.clock.now(),
            portfolio=self.portfolio,
            watchlist=list(self.watchlist),
            calibration_version="identity-v1",
            pending_settlements=list(settled),
        )

    def _apply_settlements(self, settled: list[Any]) -> None:
        """Remove settled positions from the carried portfolio (realized already
        booked by PostMortem into cash/realized_pnl during the cycle)."""
        if not settled:
            return
        settled_symbols = {t.symbol for t in settled}
        self.portfolio = self.portfolio.model_copy(
            update={
                "open_positions": [
                    p for p in self.portfolio.open_positions
                    if p.symbol not in settled_symbols
                ]
            }
        )

    def _apply_new_trades(self, state: CycleState) -> None:
        """Add this cycle's executed trades to the carried open positions."""
        additions = [
            Position(
                symbol=t.symbol, quantity=t.quantity,
                entry_price=t.entry_price, notional_value=t.notional_value,
            )
            for t in state.new_paper_trades
        ]
        if not additions:
            return
        self.portfolio = self.portfolio.model_copy(
            update={"open_positions": [*self.portfolio.open_positions, *additions]}
        )
