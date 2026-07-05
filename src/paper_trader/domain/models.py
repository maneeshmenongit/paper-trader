"""Domain models for the paper-trader cycle (Wave 2.5 Task 1).

APPLICATION layer (DC-1): domain types only. Shapes follow PAPER_TRADER_ARCH_002
§4, with the Predict output reconciled to the G6 View/NoView union (DT-6.1) —
NEVER the dead-thesis DirectionalPrediction (UP/DOWN/HOLD as the whole story).

The View still carries direction/magnitude/confidence as payload, but with the
method-selector provenance (method_selected, selection_mode) that G6 added. The
`direction` field is the forecast's directional call; the live thesis is which
*method* produced it, not that an LLM guessed a label.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AssetKind = Literal["stock", "crypto"]
ForecastMethod = Literal["momentum", "mean_reversion", "arima"]
SelectionMode = Literal["rule", "llm"]
# The forecast's directional call. This is payload on a View, NOT the agent's
# terminal thesis (that is method selection). HOLD = no directional edge.
ForecastDirection = Literal["UP", "DOWN", "HOLD"]


class Asset(BaseModel):
    symbol: str
    kind: AssetKind
    sector: str | None = None


class OHLCVBar(BaseModel):
    """One OHLCV bar (seam payload from MarketDataProvider)."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class NewsItem(BaseModel):
    """One news item (seam payload from news providers)."""

    headline: str
    url: str
    published_at: datetime
    source: str | None = None


class Position(BaseModel):
    symbol: str
    quantity: float
    entry_price: float
    notional_value: float


class PaperPortfolio(BaseModel):
    cash_balance: float
    open_positions: list[Position] = Field(default_factory=list)
    realized_pnl: float = 0.0


class PaperTrade(BaseModel):
    prediction_id: str
    symbol: str
    direction: Literal["LONG", "SHORT"] = "LONG"  # v1: LONG only
    entry_price: float
    quantity: float
    notional_value: float
    entry_time: datetime
    expected_exit_time: datetime
    exited: bool = False
    exit_price: float | None = None
    exit_time: datetime | None = None


class ResearchBundle(BaseModel):
    symbol: str
    ohlcv: list[dict[str, object]] = Field(default_factory=list)
    news: list[dict[str, object]] = Field(default_factory=list)
    indicators: dict[str, object] = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    narrative: str | None = None
    sentiment_only: bool = False  # honest degradation flag (Research C3)


# ─── Predict output — the G6 View/NoView union (DT-6.1) ──────────────────

class View(BaseModel):
    """An actionable forecast for a symbol (Appendix A.1 terminal_outputs)."""

    symbol: str
    method_selected: ForecastMethod
    selection_mode: SelectionMode
    selection_rationale: str | None = None  # required iff selection_mode == "llm"
    direction: ForecastDirection
    magnitude_pct: float
    horizon: int
    confidence: float
    method_inputs_summary: dict[str, object] = Field(default_factory=dict)
    is_baseline: bool = False  # the momentum shadow (Predict C4)


class NoView(BaseModel):
    """A valid terminal 'no forecast' answer (Appendix A.1). Never retried."""

    symbol: str
    reason: str
    methods_considered: list[ForecastMethod] = Field(default_factory=list)


# The working-memory prediction type is the union, per DT-4.5 (resolves the
# §4.1 [v2-FLAG] dict[str, DirectionalPrediction]).
Prediction = View | NoView


class TradeDecision(BaseModel):
    """Every View yields exactly one of these (Execute C2, symmetric logging)."""

    prediction_id: str
    symbol: str
    executed: bool
    risk_reason: str | None = None  # present when executed is False


class PostMortem(BaseModel):
    paper_trade_id: str
    direction_correct: bool
    predicted_magnitude_pct: float
    actual_magnitude_pct: float
    magnitude_error: float
    simulated_pnl: float
    baseline_pnl: float
    bias_tags: list[str] | None = None  # nullable (PostMortem C3)
