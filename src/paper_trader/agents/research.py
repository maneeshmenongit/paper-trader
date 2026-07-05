"""Research agent (Wave 2.5 Task 4).

Born registry-loading (research@v1). Async per-asset fan-out building a
ResearchBundle: OHLCV + news + locally computed indicators (RSI, SMA crossover,
volume trend — no LLM), one Groq keyword-extraction call and one Gemini
narrative-summary call via the LLM router seam.

Skill behavior:
  R1: per-asset fan-out; a single source failure contributes nothing, others continue.
  R2: any per-asset failure → empty bundle + skip_reason; never a cycle abort.
  R3: budget exhaustion mid-fan-out → remaining assets skipped "budget exhausted".
  R4/C3: failed narrative summary → degrade to sentiment-only bundle; never fabricate.
  C1: ≤ 1 Groq + 1 Gemini call per asset (checkable against the router's counters).
  C2: every tradeable asset ends with a bundle OR a skip_reason.
"""

from __future__ import annotations

import asyncio
from typing import Any

from paper_trader.data.interfaces import (
    Clock,
    CompanyNewsProvider,
    MarketDataProvider,
)
from paper_trader.domain import Asset, OHLCVBar, ResearchBundle
from paper_trader.graph.state import CycleState
from paper_trader.llm.errors import BudgetExhaustedError

# Semaphore bounds are config/politeness limits (ARCH_002 §7.3; Research "config,
# not skill"), not decision rules — so they live here, not in the skill.
YFINANCE_LIMIT = 2
FINNHUB_LIMIT = 4


class ResearchAgent:
    name = "research"
    writes = ["research_bundles", "skip_reasons"]

    def __init__(
        self,
        skill: Any,
        *,
        clock: Clock,
        market_data: MarketDataProvider,
        company_news: CompanyNewsProvider,
        llm_router: Any,
    ):
        self.skill = skill
        self.clock = clock
        self.market_data = market_data
        self.company_news = company_news
        self.llm_router = llm_router
        self._md_sem = asyncio.Semaphore(YFINANCE_LIMIT)
        self._news_sem = asyncio.Semaphore(FINNHUB_LIMIT)

    async def run(self, state: CycleState) -> CycleState:
        bundles = dict(state.research_bundles)
        skips = dict(state.skip_reasons)

        for asset in state.tradeable_assets:
            # R3: budget exhaustion mid-fan-out → skip the remainder, don't abort.
            if state.budget_exhausted:
                skips[asset.symbol] = "budget exhausted"
                continue
            try:
                bundle = await self._research_one(asset, state)
                bundles[asset.symbol] = bundle
            except BudgetExhaustedError:
                # ran out partway through this asset → skip it and the rest (R3)
                state.budget_exhausted = True
                skips[asset.symbol] = "budget exhausted"
            except Exception as exc:  # R2: per-asset failure, never a cycle abort
                skips[asset.symbol] = f"research_failed: {exc}"

        state.research_bundles = bundles
        state.skip_reasons = skips
        return state

    async def _research_one(self, asset: Asset, state: CycleState) -> ResearchBundle:
        # OHLCV + news (R1: gather what we can; a source failure raises to R2).
        async with self._md_sem:
            ohlcv = await self.market_data.get_ohlcv(asset.symbol, period_days=30)
        async with self._news_sem:
            news = await self.company_news.get_company_news(asset.symbol, since=self.clock.now())

        indicators = _compute_indicators(ohlcv)  # local, no LLM

        # 1 Groq keyword-extraction call (C1). Budget errors propagate to R3.
        kw_text, kw_tokens = self.llm_router.call(
            "classification", "extract keywords", str(news)
        )
        state.llm_calls_made += 1
        state.llm_tokens_used += kw_tokens
        keywords = [k.strip() for k in kw_text.split(",") if k.strip()]

        # 1 Gemini narrative-summary call (C1). R4/C3: on failure, degrade to
        # sentiment-only — NEVER fabricate a narrative.
        narrative: str | None = None
        sentiment_only = False
        try:
            narrative, narr_tokens = self.llm_router.call(
                "summarization", "summarize narrative", str(news)
            )
            state.llm_calls_made += 1
            state.llm_tokens_used += narr_tokens
            if not narrative:
                narrative, sentiment_only = None, True
        except BudgetExhaustedError:
            raise  # budget is R3's concern, not honest degradation
        except Exception:
            narrative, sentiment_only = None, True  # R4/C3 honest degradation

        return ResearchBundle(
            symbol=asset.symbol,
            ohlcv=[b.model_dump() for b in ohlcv],
            news=[n.model_dump() for n in news],
            indicators=indicators,
            keywords=keywords,
            narrative=narrative,
            sentiment_only=sentiment_only,
        )


def _compute_indicators(ohlcv: list[OHLCVBar]) -> dict[str, object]:
    """Locally computed indicators (RSI, SMA crossover, volume trend). No LLM."""
    closes = [b.close for b in ohlcv]
    volumes = [b.volume for b in ohlcv]
    return {
        "rsi_14": _rsi(closes, period=14),
        "sma_cross": _sma_cross(closes, short=5, long=20),
        "volume_trend": _volume_trend(volumes),
    }


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    gains, losses = 0.0, 0.0
    for prev, cur in zip(closes[-period - 1 :], closes[-period:], strict=False):
        delta = cur - prev
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def _sma_cross(closes: list[float], short: int, long: int) -> str | None:
    if len(closes) < long:
        return None
    sma_s = sum(closes[-short:]) / short
    sma_l = sum(closes[-long:]) / long
    return "bullish" if sma_s > sma_l else "bearish"


def _volume_trend(volumes: list[float]) -> str | None:
    if len(volumes) < 4:
        return None
    half = len(volumes) // 2
    return "rising" if sum(volumes[half:]) > sum(volumes[:half]) else "falling"
