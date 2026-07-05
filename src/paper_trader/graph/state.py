"""CycleState — the LangGraph working memory for one trading cycle.

APPLICATION layer. Shape from PAPER_TRADER_ARCH_002 §4.1, with the dead-thesis
[v2-FLAG] fields reconciled: `predictions`/`baseline_predictions` are typed as the
G6 View/NoView union (DT-4.5), NOT dict[str, DirectionalPrediction].

Cycles are independent — this object does not persist between cycles. Cross-cycle
state (portfolio, pending_settlements, recent_post_mortems) is loaded from the app
db at cycle start by the supervisor. `started_at` is injected from the Clock seam,
never datetime.now().
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from paper_trader.domain import (
    Asset,
    PaperPortfolio,
    PaperTrade,
    PostMortem,
    Prediction,
    ResearchBundle,
    TradeDecision,
)


class CycleState(BaseModel):
    # ─── identity / timing ───────────────────────────────────────────────
    cycle_id: str                              # uuid4, generated at cycle start
    started_at: datetime                       # injected from Clock, NOT datetime.now()
    cycle_kind: Literal["live", "backtest"] = "live"

    # ─── cross-cycle inputs (loaded at cycle start) ──────────────────────
    portfolio: PaperPortfolio
    watchlist: list[Asset]
    pending_settlements: list[PaperTrade] = Field(default_factory=list)
    recent_post_mortems: list[PostMortem] = Field(default_factory=list)
    calibration_version: str

    # ─── in-cycle working memory ─────────────────────────────────────────
    tradeable_assets: list[Asset] = Field(default_factory=list)          # Filter output
    research_bundles: dict[str, ResearchBundle] = Field(default_factory=dict)
    predictions: dict[str, Prediction] = Field(default_factory=dict)      # View | NoView (DT-4.5)
    baseline_predictions: dict[str, Prediction] = Field(default_factory=dict)
    trade_decisions: dict[str, TradeDecision] = Field(default_factory=dict)
    new_paper_trades: list[PaperTrade] = Field(default_factory=list)
    new_post_mortems: list[PostMortem] = Field(default_factory=list)

    # ─── routing / control ───────────────────────────────────────────────
    next_agent: (
        Literal["filter", "research", "predict", "execute", "postmortem", "end"] | None
    ) = None
    completed_agents: list[str] = Field(default_factory=list)
    skip_reasons: dict[str, str] = Field(default_factory=dict)            # symbol → reason

    # ─── budget / bookkeeping ────────────────────────────────────────────
    llm_calls_made: int = 0
    llm_tokens_used: int = 0
    budget_exhausted: bool = False

    errors: list[str] = Field(default_factory=list)
    ended_at: datetime | None = None
