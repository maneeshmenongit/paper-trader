"""Execute agent (Wave 2.5 Task 5).

Born registry-loading (execute@v1). The dissolved risk_gates.toml is SKILL
CONTENT — Kelly fraction, position/exposure caps, loss halt, the confidence ≥
0.55 floor (with its annotation), magnitude ≥ 0.5%, and the idempotency guard are
all parsed from the loaded skill (ExecuteParams), NEVER hardcoded. ZERO LLM calls
(C3). Symmetric logging (C2): every View yields exactly one TradeDecision; skips
carry a risk_reason.

v1 is LONG-only: an actionable View has direction == 'UP'. DOWN/HOLD Views are
recorded as TradeDecision(executed=False, risk_reason='long_only_v1') so the
post-mortem can still score them.
"""

from __future__ import annotations

from typing import Any

from paper_trader.agents.skill_params import ExecuteParams
from paper_trader.domain import PaperTrade, TradeDecision, View
from paper_trader.graph.state import CycleState
from paper_trader.settlement.engine import horizon_exit_time


class ExecuteAgent:
    name = "execute"
    writes = ["trade_decisions", "new_paper_trades", "portfolio"]

    def __init__(
        self,
        skill: Any,
        *,
        clock: Any,
        trading_client: Any,
        horizon_hours: int = 24,
    ):
        self.skill = skill
        self.clock = clock
        self.trading_client = trading_client
        self.params = ExecuteParams(skill)  # all risk values from the skill
        # Settlement horizon (CYCLE_TIME_HORIZON_HOURS), injected as config — the
        # v1 stub set expected_exit_time = now (never settled). This is a recorded
        # exit deadline, NOT a trade-decision input: it does not gate any trade.
        self.horizon_hours = horizon_hours
        # Portfolio equity in effect at Execute time — recorded for the frozen
        # trace (Wave 5 Task 1). Inert: it does not affect any trade decision.
        self._frozen_equity: float | None = None

    def frozen_facts(self) -> dict[str, Any]:
        """Extra frozen facts for this invocation's Store A input (DT-4.2).

        Freezes the equity the cap check was measured against so the observer can
        recompute notional <= max_position_pct * equity without re-deriving it.
        Equity is domain state, not a secret (freeze checklist).
        """
        if self._frozen_equity is None:
            return {}
        return {"frozen_equity": self._frozen_equity}

    async def run(self, state: CycleState) -> CycleState:
        decisions = dict(state.trade_decisions)
        new_trades = list(state.new_paper_trades)
        open_count = len(state.portfolio.open_positions)
        # Freeze the equity in effect NOW (before any of this cycle's trades).
        self._frozen_equity = self._equity(state)

        # Loss halt is a cycle-level gate: if breached, no new trades this cycle.
        loss_halted = self._daily_loss_breached(state)

        for symbol, pred in state.predictions.items():
            if not isinstance(pred, View):
                continue  # NoView never becomes a trade_decision (C2 scoping)
            if pred.is_baseline:
                continue  # the momentum shadow is a measuring stick, never traded

            # Idempotency guard: one decision per prediction (crash double-write).
            if symbol in decisions:
                continue

            reason = self._reject_reason(pred, state, open_count, loss_halted)
            if reason is not None:
                decisions[symbol] = TradeDecision(
                    prediction_id=symbol, symbol=symbol, executed=False, risk_reason=reason
                )
                continue

            trade = await self._size_and_fill(pred, state)
            decisions[symbol] = TradeDecision(
                prediction_id=symbol, symbol=symbol, executed=True
            )
            new_trades.append(trade)
            open_count += 1

        state.trade_decisions = decisions
        state.new_paper_trades = new_trades
        return state

    def _reject_reason(
        self, view: View, state: CycleState, open_count: int, loss_halted: bool
    ) -> str | None:
        if loss_halted:
            return "daily_loss_halt"
        if view.confidence < self.params.min_confidence:
            return "below_confidence_floor"
        if abs(view.magnitude_pct) < self.params.min_magnitude_pct * 100:
            # magnitude_pct is expressed in percent (e.g. 0.5 == 0.5%)
            return "below_magnitude_floor"
        if view.direction != "UP":
            return "long_only_v1"       # DOWN/HOLD recorded but not traded
        if open_count >= self.params.max_open_positions:
            return "max_open_positions"
        if self._exposure_after(state, view) > self.params.max_total_exposure_pct:
            return "max_total_exposure"
        return None

    async def _size_and_fill(self, view: View, state: CycleState) -> PaperTrade:
        equity = self._equity(state)
        entry_price = self._entry_price(view, state)

        # Fractional Kelly on the view's edge, capped by max position size.
        edge = max(view.confidence - 0.5, 0.0)  # simple edge proxy in [0, 0.5]
        kelly_notional = equity * self.params.kelly_fraction * (edge * 2)
        cap_notional = equity * self.params.max_position_pct
        notional = max(min(kelly_notional, cap_notional), self.params.min_notional)

        fill = await self.trading_client.submit_paper_trade(
            view.symbol, notional / entry_price, entry_price
        )
        quantity = notional / fill
        entry_time = self.clock.now()
        return PaperTrade(
            prediction_id=view.symbol,
            symbol=view.symbol,
            direction="LONG",
            entry_price=fill,
            quantity=quantity,
            notional_value=notional,
            entry_time=entry_time,
            # Horizon-based exit deadline so settlement can close the position at
            # or past this time (T4). Uses the injected config horizon.
            expected_exit_time=horizon_exit_time(entry_time, self.horizon_hours),
        )

    # ─── helpers ─────────────────────────────────────────────────────────

    def _equity(self, state: CycleState) -> float:
        positions = sum(p.notional_value for p in state.portfolio.open_positions)
        return state.portfolio.cash_balance + positions

    def _exposure_after(self, state: CycleState, view: View) -> float:
        equity = self._equity(state) or 1.0
        current = sum(p.notional_value for p in state.portfolio.open_positions)
        add = equity * self.params.max_position_pct
        return (current + add) / equity

    def _daily_loss_breached(self, state: CycleState) -> bool:
        equity = self._equity(state) or 1.0
        loss = -min(state.portfolio.realized_pnl, 0.0)
        return (loss / equity) > self.params.daily_loss_halt_pct

    def _entry_price(self, view: View, state: CycleState) -> float:
        summary = view.method_inputs_summary or {}
        price = summary.get("entry_price")
        if isinstance(price, (int, float)):
            return float(price)
        return 100.0
