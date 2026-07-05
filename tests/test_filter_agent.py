"""Filter agent tests (Wave 2.5 Task 3). Registry-loading; zero LLM; no network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from paper_trader.agents.enforce import run_with_write_enforcement
from paper_trader.agents.filter import FilterAgent
from paper_trader.agents.skill_params import filter_liquidity_floors
from paper_trader.domain import Asset, PaperPortfolio, Position
from paper_trader.graph.state import CycleState
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from tests.fixtures.fakes import (
    FakeMarketData,
    FakeTradingClient,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)  # a Monday


@pytest.fixture
def filter_skill(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    with reg.connection() as conn:
        return load_skill(conn, version_id_for("filter"))


def _state(assets, portfolio=None):
    return CycleState(
        cycle_id="cyc-1",
        started_at=NOW,
        portfolio=portfolio or PaperPortfolio(cash_balance=10_000.0),
        watchlist=assets,
        calibration_version="identity-v1",
    )


def _fresh_ohlcv():
    # one bar timestamped 5 minutes before NOW -> passes R4
    return {"AAPL": make_ohlcv([100.0], start=NOW - timedelta(minutes=5))}


def _make_agent(filter_skill, *, clock=None, market_data=None, trading=None):
    return FilterAgent(
        filter_skill,
        clock=clock or FrozenClock(now=NOW, market_open=True),
        market_data=market_data or FakeMarketData(ohlcv=_fresh_ohlcv()),
        trading_client=trading or FakeTradingClient(),
    )


# ─── born registry-loading; reads floors FROM the skill ──────────────────

def test_floors_come_from_skill(filter_skill):
    agent = _make_agent(filter_skill)
    stock, crypto = filter_liquidity_floors(filter_skill)
    assert (agent.stock_floor, agent.crypto_floor) == (10_000_000.0, 50_000_000.0)
    assert stock == 10_000_000.0 and crypto == 50_000_000.0


# ─── happy path ──────────────────────────────────────────────────────────

async def test_tradeable_when_all_pass(filter_skill):
    agent = _make_agent(filter_skill)
    state = await agent.run(_state([Asset(symbol="AAPL", kind="stock")]))
    assert [a.symbol for a in state.tradeable_assets] == ["AAPL"]
    assert state.skip_reasons == {}


# ─── each rule rejects with its criterion (C2) ───────────────────────────

async def test_r1_market_closed(filter_skill):
    agent = _make_agent(filter_skill, clock=FrozenClock(now=NOW, market_open=False))
    state = await agent.run(_state([Asset(symbol="AAPL", kind="stock")]))
    assert state.tradeable_assets == []
    assert state.skip_reasons["AAPL"] == "market_closed"


async def test_r2_insufficient_liquidity_uses_skill_floor(filter_skill):
    # below the $10M stock floor from the skill
    trading = FakeTradingClient(liquidity={"AAPL": 9_000_000.0})
    agent = _make_agent(filter_skill, trading=trading)
    state = await agent.run(_state([Asset(symbol="AAPL", kind="stock")]))
    assert state.skip_reasons["AAPL"] == "insufficient_liquidity"


async def test_r2_crypto_floor(filter_skill):
    # $40M < $50M crypto floor -> reject; crypto market always open
    trading = FakeTradingClient(liquidity={"BTC": 40_000_000.0})
    agent = _make_agent(filter_skill, trading=trading)
    state = await agent.run(_state([Asset(symbol="BTC", kind="crypto")]))
    assert state.skip_reasons["BTC"] == "insufficient_liquidity"


async def test_r3_already_in_position(filter_skill):
    pf = PaperPortfolio(
        cash_balance=10_000.0,
        open_positions=[Position(symbol="AAPL", quantity=1, entry_price=100, notional_value=100)],
    )
    agent = _make_agent(filter_skill)
    state = await agent.run(_state([Asset(symbol="AAPL", kind="stock")], portfolio=pf))
    assert state.skip_reasons["AAPL"] == "already_in_position"


async def test_r4_stale_quote(filter_skill):
    stale = {"AAPL": make_ohlcv([100.0], start=NOW - timedelta(minutes=120))}
    agent = _make_agent(filter_skill, market_data=FakeMarketData(ohlcv=stale))
    state = await agent.run(_state([Asset(symbol="AAPL", kind="stock")]))
    assert state.skip_reasons["AAPL"] == "stale_quote"


# ─── C1 completeness: every entry lands in exactly one bucket ────────────

async def test_completeness_every_entry_bucketed(filter_skill):
    trading = FakeTradingClient(liquidity={"THIN": 1.0})  # THIN fails R2
    md = FakeMarketData(ohlcv={
        "AAPL": make_ohlcv([100.0], start=NOW - timedelta(minutes=5)),
        "THIN": make_ohlcv([1.0], start=NOW - timedelta(minutes=5)),
    })
    agent = _make_agent(filter_skill, market_data=md, trading=trading)
    watchlist = [Asset(symbol="AAPL", kind="stock"), Asset(symbol="THIN", kind="stock")]
    state = await agent.run(_state(watchlist))
    bucketed = {a.symbol for a in state.tradeable_assets} | set(state.skip_reasons)
    assert bucketed == {"AAPL", "THIN"}
    # exactly one bucket each
    assert not ({a.symbol for a in state.tradeable_assets} & set(state.skip_reasons))


# ─── C3 zero LLM calls: the agent takes no router at all ─────────────────

def test_agent_has_no_llm_dependency(filter_skill):
    agent = _make_agent(filter_skill)
    # no router / llm attribute exists on the Filter agent
    assert not any("llm" in a.lower() or "router" in a.lower() for a in vars(agent))


# ─── write-enforcement holds ─────────────────────────────────────────────

async def test_write_enforcement_allows_declared_and_marks_complete(filter_skill):
    agent = _make_agent(filter_skill)
    state = await run_with_write_enforcement(agent, _state([Asset(symbol="AAPL", kind="stock")]))
    assert "filter" in state.completed_agents
    assert [a.symbol for a in state.tradeable_assets] == ["AAPL"]
