"""PostMortem agent (Wave 2.5 Task 6).

Born registry-loading (postmortem@v1). Scores settled trades and updates the
portfolio. It MEASURES OUTCOMES; it NEVER REACTS to them — behavioral
consequences flow exclusively through the ledger-and-gate path (ARCH_002 §0.4;
skill mandate). This is the "hold this line" agent: it is NOT the correction
officer. Structurally, it has NO Store B / ledger seam — it cannot write there,
by construction (C4: write-set is the app db only, never Store B).

  R1: per settlement — score hit/miss vs the View's direction; compute P&L + magnitude error.
  R2: update portfolio (cash + open positions) on close.
  R3: bias tags via a batched Groq call (~1 per 4 settlements).
  C1: every settled trade gets a post-mortem row.
  C2: required fields always present (hit/miss, P&L, magnitude error).
  C3: bias_tags nullable — a failed tagging call yields null; an invented tag is a divergence.
"""

from __future__ import annotations

from typing import Any

from paper_trader.domain import PaperTrade, PostMortem
from paper_trader.graph.state import CycleState

BIAS_BATCH_SIZE = 4  # R3: ~1 Groq call per 4 settlements


class PostMortemAgent:
    name = "postmortem"
    writes = ["new_post_mortems", "portfolio"]

    def __init__(self, skill: Any, *, market_data: Any, llm_router: Any):
        self.skill = skill
        self.market_data = market_data
        self.llm_router = llm_router  # ONLY for bias tagging; no Store B anywhere

    async def run(self, state: CycleState) -> CycleState:
        settled = state.pending_settlements
        if not settled:
            return state  # empty is valid — nothing settled this cycle

        post_mortems = list(state.new_post_mortems)
        realized_delta = 0.0

        scored: list[PostMortem] = []
        for trade in settled:
            pm = await self._score(trade)
            scored.append(pm)
            realized_delta += pm.simulated_pnl

        # R3 / C3: bias tags in batches; a failed call yields null, never invented.
        self._apply_bias_tags(scored, state)

        post_mortems.extend(scored)
        state.new_post_mortems = post_mortems

        # R2: update portfolio on close (app db only; membrane untouched).
        state.portfolio = state.portfolio.model_copy(
            update={
                "cash_balance": state.portfolio.cash_balance + realized_delta,
                "realized_pnl": state.portfolio.realized_pnl + realized_delta,
            }
        )
        return state

    async def _score(self, trade: PaperTrade) -> PostMortem:
        exit_price = await self.market_data.get_current_quote(trade.symbol)
        actual_move = (exit_price - trade.entry_price) / trade.entry_price
        # v1 LONG-only: gain if price rose.
        direction_correct = exit_price >= trade.entry_price
        simulated_pnl = trade.quantity * (exit_price - trade.entry_price)
        # baseline shadow P&L: momentum baseline (placeholder parity in this wave).
        baseline_pnl = simulated_pnl
        predicted_mag = 0.0  # filled from the View when available (parity for now)
        actual_mag = actual_move * 100.0
        return PostMortem(
            paper_trade_id=trade.prediction_id,
            direction_correct=direction_correct,
            predicted_magnitude_pct=predicted_mag,
            actual_magnitude_pct=actual_mag,
            magnitude_error=abs(actual_mag - predicted_mag),
            simulated_pnl=simulated_pnl,
            baseline_pnl=baseline_pnl,
            bias_tags=None,
        )

    def _apply_bias_tags(self, scored: list[PostMortem], state: CycleState) -> None:
        for start in range(0, len(scored), BIAS_BATCH_SIZE):
            batch = scored[start : start + BIAS_BATCH_SIZE]
            try:
                text, tokens = self.llm_router.call(
                    "bias_tagging", "tag biases", str([pm.paper_trade_id for pm in batch])
                )
                state.llm_calls_made += 1
                state.llm_tokens_used += tokens
                tags = [t.strip() for t in text.split(",") if t.strip()]
                # C3: assign only what the model returned; never invent.
                for pm in batch:
                    pm.bias_tags = tags or None
            except Exception:
                # C3: a failed tagging call yields null (compliant).
                for pm in batch:
                    pm.bias_tags = None
