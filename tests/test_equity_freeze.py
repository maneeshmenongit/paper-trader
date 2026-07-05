"""Equity-freeze amendment tests (Wave 5 Task 1). Execute freezes its equity."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from paper_trader.agents.execute import ExecuteAgent
from paper_trader.agents.filter import FilterAgent
from paper_trader.agents.postmortem import PostMortemAgent
from paper_trader.agents.predict import PredictAgent
from paper_trader.agents.research import ResearchAgent
from paper_trader.domain import Asset, PaperPortfolio, Position
from paper_trader.emission import Emitter
from paper_trader.graph.state import CycleState
from paper_trader.graph.supervisor import Supervisor
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from tests.fixtures.fakes import (
    FakeCompanyNews,
    FakeLLMRouter,
    FakeMarketData,
    FakeTradingClient,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
CID = "01EQUITYFREEZECYCLE0000AA"
CFG = {"cycle_time_horizon_hours": 24, "cycle_token_budget": 15000, "log_level": "INFO"}


@pytest.fixture
def registry(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    return reg


def _load(registry, agent):
    with registry.connection() as conn:
        return load_skill(conn, version_id_for(agent))


def _fresh_bars():
    bars = make_ohlcv([100.0] * 24 + [130.0])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    return bars


def _supervisor(registry, store_a, portfolio):
    clock = FrozenClock(now=NOW, market_open=True)
    md = FakeMarketData(quotes={"AAPL": 130.0}, ohlcv={"AAPL": _fresh_bars()})
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s"})
    trading = FakeTradingClient()
    pins = {a: version_id_for(a) for a in
            ("filter", "research", "predict", "execute", "postmortem")}
    return Supervisor(
        filter_agent=FilterAgent(_load(registry, "filter"), clock=clock,
                                 market_data=md, trading_client=trading),
        research_agent=ResearchAgent(
            _load(registry, "research"), clock=clock, market_data=md,
            company_news=FakeCompanyNews(news={"AAPL": []}), llm_router=router),
        predict_agent=PredictAgent(_load(registry, "predict")),
        execute_agent=ExecuteAgent(_load(registry, "execute"), clock=clock, trading_client=trading),
        postmortem_agent=PostMortemAgent(_load(registry, "postmortem"),
                                         market_data=md, llm_router=router),
        emitter=Emitter(store_a, application_id="paper-trader"),
        clock=clock, skill_pins=pins, cycle_config=CFG,
    )


def _state(portfolio):
    return CycleState(
        cycle_id=CID, started_at=NOW, portfolio=portfolio,
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1",
    )


async def test_execute_input_carries_frozen_equity(registry, tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    # cash 8000 + one position worth 2000 -> equity 10000
    pf = PaperPortfolio(
        cash_balance=8000.0,
        open_positions=[Position(symbol="MSFT", quantity=1, entry_price=2000,
                                 notional_value=2000.0)],
    )
    await _supervisor(registry, store_a, pf).run_cycle(_state(pf))
    with store_a.connection() as conn:
        row = conn.execute(
            "SELECT agent_input FROM agent_invocations WHERE agent_name='execute'"
        ).fetchone()
    frozen = json.loads(row["agent_input"])
    assert frozen["frozen_equity"] == pytest.approx(10000.0)


async def test_frozen_facts_empty_before_run(registry):
    agent = ExecuteAgent(_load(registry, "execute"),
                         clock=FrozenClock(now=NOW), trading_client=FakeTradingClient())
    assert agent.frozen_facts() == {}  # nothing frozen until run


async def test_non_execute_agents_have_no_frozen_equity(registry, tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    pf = PaperPortfolio(cash_balance=10000.0)
    await _supervisor(registry, store_a, pf).run_cycle(_state(pf))
    with store_a.connection() as conn:
        rows = conn.execute(
            "SELECT agent_name, agent_input FROM agent_invocations WHERE agent_name!='execute'"
        ).fetchall()
    for r in rows:
        assert "frozen_equity" not in json.loads(r["agent_input"])
