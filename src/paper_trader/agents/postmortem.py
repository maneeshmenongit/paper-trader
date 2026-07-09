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

from paper_trader.analytics.direction_score import direction_correct as _direction_correct
from paper_trader.analytics.pnl import (
    actual_move_fraction,
    baseline_shadow_pnl,
    realized_pnl,
)
from paper_trader.domain import PaperTrade, PostMortem
from paper_trader.graph.state import CycleState
from paper_trader.settlement.engine import SettlementContext

BIAS_BATCH_SIZE = 4  # R3: ~1 Groq call per 4 settlements


class PostMortemAgent:
    name = "postmortem"
    writes = ["new_post_mortems", "portfolio"]

    def __init__(
        self,
        skill: Any,
        *,
        market_data: Any,
        llm_router: Any,
        settlement_contexts: dict[str, SettlementContext] | None = None,
    ):
        self.skill = skill
        self.market_data = market_data
        self.llm_router = llm_router  # ONLY for bias tagging; no Store B anywhere
        # T4: per-settlement context (the traded View's predicted magnitude + the
        # momentum baseline shadow's magnitude), keyed by prediction_id. Threaded
        # in by the settlement pass. Absent → fall back to v1 parity behavior.
        self.settlement_contexts = settlement_contexts or {}

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
        # A settled trade already carries its exit price (T4 settlement); fall back
        # to a live quote for legacy/unsettled inputs (pre-T4 behavior).
        if trade.exited and trade.exit_price is not None:
            exit_price = trade.exit_price
        else:
            exit_price = await self.market_data.get_current_quote(trade.symbol)
        # Real math (analytics/*): the ONE path shared with the Stage-0 backtest.
        actual_move = actual_move_fraction(trade.entry_price, exit_price)
        # v1 LONG-only: gain if price rose.
        direction_correct = _direction_correct(trade.entry_price, exit_price)
        simulated_pnl = realized_pnl(trade.entry_price, exit_price, trade.quantity)

        ctx = self.settlement_contexts.get(trade.prediction_id)
        actual_mag = actual_move * 100.0
        # T4: the traded View's own predicted magnitude (magnitude_error is real
        # when known); parity fallback (0.0) preserves pre-T4 behavior.
        predicted_mag = (
            ctx.predicted_magnitude_pct
            if ctx is not None and ctx.predicted_magnitude_pct is not None
            else 0.0
        )
        # T4: the momentum baseline SHADOW P&L — what the same-symbol baseline
        # forecast would have earned on this position's notional. The selector's
        # independent measuring stick. Absent baseline → parity with the trade.
        baseline_pnl = self._baseline_pnl(trade, simulated_pnl, actual_move, ctx)
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

    def _baseline_pnl(
        self,
        trade: PaperTrade,
        simulated_pnl: float,
        actual_move: float,
        ctx: SettlementContext | None,
    ) -> float:
        """Momentum baseline shadow P&L: what the BASELINE call earned on this
        position, measured by the REALIZED move (not the predicted magnitude).

        The baseline forecast a direction; its shadow P&L is the actual price move
        applied to the notional, signed +1 for a LONG (UP) baseline call and -1
        for a DOWN call. In momentum-only v1 the baseline direction equals the
        traded direction, so this equals the trade's own P&L (correct: momentum IS
        the baseline now). It diverges only once a DIFFERENT method is selected —
        the thesis phase — which is exactly when the stick must be measured against
        the outcome, not the forecast. Absent a baseline row → parity with the trade.

        (Earlier T4 code multiplied notional by the PREDICTED magnitude, which
        inflated the shadow ~15x on the first live settlement — a real-data bug the
        settlement-elapsed run caught.)
        """
        if ctx is None or ctx.baseline_magnitude_pct is None:
            return simulated_pnl
        # sign of the baseline's directional call (magnitude carries the sign).
        direction_sign = 1.0 if ctx.baseline_magnitude_pct >= 0 else -1.0
        return baseline_shadow_pnl(trade.notional_value, actual_move, direction_sign)

    def _apply_bias_tags(self, scored: list[PostMortem], state: CycleState) -> None:
        for start in range(0, len(scored), BIAS_BATCH_SIZE):
            batch = scored[start : start + BIAS_BATCH_SIZE]
            try:
                text, tokens = self.llm_router.call(
                    "bias_tagging", _BIAS_SYSTEM_PROMPT, _bias_user_prompt(batch)
                )
                state.llm_calls_made += 1
                state.llm_tokens_used += tokens
                tags = _parse_bias_tags(text)
                # C3: assign only what the model returned; never invent.
                for pm in batch:
                    pm.bias_tags = tags or None
            except Exception:
                # C3: a failed tagging call yields null (compliant).
                for pm in batch:
                    pm.bias_tags = None


# Small local models (Llama 3.1 8B) ramble without a strict instruction; the
# first live run stored essays as "bias tags". Constrain the task and the format.
_BIAS_SYSTEM_PROMPT = (
    "You label cognitive biases in trading outcomes. Reply with ONLY a short "
    "comma-separated list of 0-3 lowercase bias labels (e.g. overconfidence, "
    "recency, anchoring). No sentences, no explanation. If none apply, reply NONE."
)
# A tag is a short label, not prose — reject anything that looks like an essay.
_MAX_TAG_WORDS = 3
_MAX_TAGS = 3


def _bias_user_prompt(batch: list[PostMortem]) -> str:
    lines = [
        f"trade {pm.paper_trade_id}: "
        f"{'correct' if pm.direction_correct else 'wrong'} direction, "
        f"predicted {pm.predicted_magnitude_pct:.2f}% vs actual "
        f"{pm.actual_magnitude_pct:.2f}%, pnl {pm.simulated_pnl:.2f}"
        for pm in batch
    ]
    return "Outcomes:\n" + "\n".join(lines)


def _parse_bias_tags(text: str) -> list[str]:
    """Parse a terse tag list; drop essay-like or empty output (C3 honesty)."""
    cleaned = text.strip()
    if not cleaned or cleaned.upper().startswith("NONE"):
        return []
    tags: list[str] = []
    for raw in cleaned.split(","):
        tag = raw.strip().strip(".").lower()
        # A real tag is 1-3 words; anything longer is model rambling, not a label.
        if tag and len(tag.split()) <= _MAX_TAG_WORDS:
            tags.append(tag)
    return tags[:_MAX_TAGS]
