"""End-to-end cycle test (Wave 2.5 Task 9). All agents load from the registry;
a full cycle produces trade_decisions + paper_trades in the app db. Fakes only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from paper_trader.agents.execute import ExecuteAgent
from paper_trader.agents.filter import FilterAgent
from paper_trader.agents.postmortem import PostMortemAgent
from paper_trader.agents.predict import PredictAgent
from paper_trader.agents.research import ResearchAgent
from paper_trader.domain import Asset, PaperPortfolio
from paper_trader.graph.state import CycleState
from paper_trader.graph.supervisor import Supervisor
from paper_trader.persistence.cycle_writer import persist_cycle
from paper_trader.persistence.db import Database
from paper_trader.persistence.repository import Repository
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from tests.fixtures.fakes import (
    FakeCompanyNews,
    FakeLLMRouter,
    FakeMarketData,
    FakeTradingClient,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)  # Monday


@pytest.fixture
def registry(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    return reg


def _load(registry, agent):
    with registry.connection() as conn:
        return load_skill(conn, version_id_for(agent))


@pytest.fixture
def supervisor(registry):
    clock = FrozenClock(now=NOW, market_open=True)
    # a strong up-move so momentum yields a confident, actionable UP View.
    # last bar is 5 min old so Filter R4 (freshness) passes.
    bars = make_ohlcv([100.0] * 24 + [130.0])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    md = FakeMarketData(quotes={"AAPL": 130.0}, ohlcv={"AAPL": bars})
    news = FakeCompanyNews(news={"AAPL": []})
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "story"})
    trading = FakeTradingClient()  # ample liquidity by default

    return Supervisor(
        filter_agent=FilterAgent(
            _load(registry, "filter"), clock=clock, market_data=md, trading_client=trading
        ),
        research_agent=ResearchAgent(
            _load(registry, "research"), clock=clock, market_data=md,
            company_news=news, llm_router=router,
        ),
        predict_agent=PredictAgent(_load(registry, "predict")),
        execute_agent=ExecuteAgent(
            _load(registry, "execute"), clock=clock, trading_client=trading
        ),
        postmortem_agent=PostMortemAgent(
            _load(registry, "postmortem"), market_data=md, llm_router=router,
        ),
    )


def _state():
    return CycleState(
        cycle_id="cyc-e2e",
        started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1",
    )


# ─── a full cycle runs and produces trades ───────────────────────────────

async def test_full_cycle_produces_trade_in_app_db(supervisor, tmp_path):
    state = await supervisor.run_cycle(_state())

    # every agent that ran did so end-to-end
    assert "filter" in state.completed_agents
    assert "research" in state.completed_agents
    assert "predict" in state.completed_agents
    assert "execute" in state.completed_agents

    # an actionable UP View led to an executed trade in working memory
    assert state.trade_decisions["AAPL"].executed is True
    assert len(state.new_paper_trades) == 1

    # persist to the app db and assert rows landed
    repo = Repository(Database(tmp_path / "paper_trader.sqlite"))
    persist_cycle(repo, state)
    with repo.db.connection() as conn:
        preds = conn.execute("SELECT * FROM predictions").fetchall()
        decisions = conn.execute("SELECT * FROM trade_decisions WHERE executed=1").fetchall()
        trades = conn.execute("SELECT * FROM paper_trades").fetchall()
    assert len(preds) >= 1
    assert len(decisions) == 1
    assert len(trades) == 1
    assert trades[0]["symbol"] == "AAPL"
    # DT-8.3: the predictions row carries method-selector provenance
    assert preds[0]["method_selected"] == "momentum"
    assert preds[0]["selection_mode"] == "rule"


# ─── graceful early-exit: empty tradeable set ends at Decision C ─────────

async def test_empty_tradeable_ends_gracefully(registry):
    clock = FrozenClock(now=NOW, market_open=False)  # market closed -> all skip
    md = FakeMarketData(ohlcv={"AAPL": make_ohlcv([1.0])})
    trading = FakeTradingClient()
    sup = Supervisor(
        filter_agent=FilterAgent(_load(registry, "filter"), clock=clock,
                                 market_data=md, trading_client=trading),
        research_agent=ResearchAgent(_load(registry, "research"), clock=clock,
                                     market_data=md, company_news=FakeCompanyNews(),
                                     llm_router=FakeLLMRouter()),
        predict_agent=PredictAgent(_load(registry, "predict")),
        execute_agent=ExecuteAgent(_load(registry, "execute"), clock=clock,
                                   trading_client=trading),
        postmortem_agent=PostMortemAgent(_load(registry, "postmortem"),
                                         market_data=md, llm_router=FakeLLMRouter()),
    )
    state = await sup.run_cycle(_state())
    assert state.next_agent == "end"
    assert "research" not in state.completed_agents  # ended at Decision C
    assert state.new_paper_trades == []


# ─── NO Store A/B emission occurred (working memory + app db only) ───────

async def test_no_governance_emission(supervisor, tmp_path):
    state = await supervisor.run_cycle(_state())
    # the cycle carries no governance-store handles and wrote no ledger/trace
    assert not hasattr(state, "store_a")
    assert not hasattr(state, "store_b")
