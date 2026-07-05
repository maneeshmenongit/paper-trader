"""Research agent tests (Wave 2.5 Task 4). Registry-loading; fakes only; no network."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_trader.agents.research import ResearchAgent
from paper_trader.domain import Asset, NewsItem, PaperPortfolio
from paper_trader.graph.state import CycleState
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from tests.fixtures.fakes import (
    FakeCompanyNews,
    FakeLLMRouter,
    FakeMarketData,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def research_skill(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    with reg.connection() as conn:
        return load_skill(conn, version_id_for("research"))


def _state(symbols, **kw):
    return CycleState(
        cycle_id="cyc-1",
        started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[],
        tradeable_assets=[Asset(symbol=s, kind="stock") for s in symbols],
        calibration_version="identity-v1",
        **kw,
    )


def _agent(research_skill, *, news=None, router=None, market_data=None):
    return ResearchAgent(
        research_skill,
        clock=FrozenClock(now=NOW),
        market_data=market_data or FakeMarketData(ohlcv={"AAPL": make_ohlcv([1.0] * 25)}),
        company_news=news or FakeCompanyNews(news={"AAPL": [
            NewsItem(headline="h", url="u", published_at=NOW)
        ]}),
        llm_router=router or FakeLLMRouter(
            responses={"classification": "ai, chips", "summarization": "a narrative"}
        ),
    )


# ─── happy path: 1 Groq + 1 Gemini, full bundle ──────────────────────────

async def test_full_bundle(research_skill):
    router = FakeLLMRouter(responses={"classification": "ai, chips", "summarization": "story"})
    agent = _agent(research_skill, router=router)
    state = await agent.run(_state(["AAPL"]))
    b = state.research_bundles["AAPL"]
    assert b.keywords == ["ai", "chips"]
    assert b.narrative == "story"
    assert b.sentiment_only is False
    assert "rsi_14" in b.indicators
    # C1: exactly 1 Groq (classification) + 1 Gemini (summarization) for one asset
    assert router.calls == ["classification", "summarization"]


# ─── R4/C3 honest degradation: failed narrative → sentiment-only ─────────

async def test_failed_narrative_degrades_sentiment_only(research_skill):
    router = FakeLLMRouter(
        responses={"classification": "ai"}, fail_purposes={"summarization"}
    )
    agent = _agent(research_skill, router=router)
    state = await agent.run(_state(["AAPL"]))
    b = state.research_bundles["AAPL"]
    assert b.narrative is None          # never fabricated
    assert b.sentiment_only is True     # C3
    assert b.keywords == ["ai"]         # keyword call still succeeded


# ─── R2: per-asset failure → skip_reason, never abort ────────────────────

async def test_source_failure_skips_asset_not_cycle(research_skill):
    agent = _agent(research_skill, news=FakeCompanyNews(fail=True))
    state = await agent.run(_state(["AAPL"]))
    assert "AAPL" not in state.research_bundles
    assert "research_failed" in state.skip_reasons["AAPL"]


# ─── R3: budget exhaustion mid-fan-out → remaining skipped ───────────────

async def test_budget_exhaustion_mid_fanout(research_skill):
    # allow 2 calls (asset #1's Groq+Gemini), then exhaust for asset #2
    router = FakeLLMRouter(
        responses={"classification": "ai", "summarization": "s"},
        budget_exhausted_after=2,
    )
    md = FakeMarketData(ohlcv={
        "AAPL": make_ohlcv([1.0] * 25), "MSFT": make_ohlcv([1.0] * 25),
    })
    news = FakeCompanyNews(news={
        "AAPL": [NewsItem(headline="h", url="u", published_at=NOW)],
        "MSFT": [NewsItem(headline="h", url="u", published_at=NOW)],
    })
    agent = _agent(research_skill, router=router, news=news, market_data=md)
    state = await agent.run(_state(["AAPL", "MSFT"]))
    assert "AAPL" in state.research_bundles          # first asset completed
    assert state.skip_reasons["MSFT"] == "budget exhausted"
    assert state.budget_exhausted is True


# ─── C2 completeness: every tradeable asset -> bundle or skip ────────────

async def test_completeness(research_skill):
    md = FakeMarketData(ohlcv={"AAPL": make_ohlcv([1.0] * 25)})  # MSFT has no data path
    news = FakeCompanyNews(news={"AAPL": [NewsItem(headline="h", url="u", published_at=NOW)]},
                           fail=False)
    agent = _agent(research_skill, market_data=md, news=news)
    state = await agent.run(_state(["AAPL", "MSFT"]))
    covered = set(state.research_bundles) | set(state.skip_reasons)
    assert covered == {"AAPL", "MSFT"}


# ─── C1 counter: at most 1 Groq + 1 Gemini per asset ─────────────────────

async def test_call_budget_one_each_per_asset(research_skill):
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s"})
    md = FakeMarketData(ohlcv={
        "AAPL": make_ohlcv([1.0] * 25), "MSFT": make_ohlcv([1.0] * 25),
    })
    news = FakeCompanyNews(news={
        "AAPL": [NewsItem(headline="h", url="u", published_at=NOW)],
        "MSFT": [NewsItem(headline="h", url="u", published_at=NOW)],
    })
    agent = _agent(research_skill, router=router, news=news, market_data=md)
    await agent.run(_state(["AAPL", "MSFT"]))
    # 2 assets × (1 classification + 1 summarization) = 4 calls, no more
    assert router.calls.count("classification") == 2
    assert router.calls.count("summarization") == 2
    assert len(router.calls) == 4
