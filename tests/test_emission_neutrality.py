"""Behavior-neutrality proof (Wave 3 Task 5) — the wave's core acceptance test.

The same deterministic cycle (same fakes, frozen Clock, frozen inputs) is run
emission-OFF and emission-ON; the resulting trade_decisions must be byte-identical.
Emission is additive: it reads frozen facts and writes Store A; it never alters a
trade decision.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from paper_trader.agents.execute import ExecuteAgent
from paper_trader.agents.filter import FilterAgent
from paper_trader.agents.postmortem import PostMortemAgent
from paper_trader.agents.predict import PredictAgent
from paper_trader.agents.research import ResearchAgent
from paper_trader.domain import Asset, PaperPortfolio
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
CYCLE_CONFIG = {"cycle_time_horizon_hours": 24, "cycle_token_budget": 15000, "log_level": "INFO"}
FIXED_CID = "01FIXEDCYCLEID0000000000AA"


@pytest.fixture
def registry(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    return reg


def _load(registry, agent):
    with registry.connection() as conn:
        return load_skill(conn, version_id_for(agent))


def _pins():
    agents = ("filter", "research", "predict", "execute", "postmortem")
    return {a: version_id_for(a) for a in agents}


def _fresh_bars():
    bars = make_ohlcv([100.0] * 24 + [130.0])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    return bars


def _make_supervisor(registry, *, emitter):
    clock = FrozenClock(now=NOW, market_open=True)
    md = FakeMarketData(quotes={"AAPL": 130.0}, ohlcv={"AAPL": _fresh_bars()})
    news = FakeCompanyNews(news={"AAPL": []})
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s"})
    trading = FakeTradingClient()
    return Supervisor(
        filter_agent=FilterAgent(_load(registry, "filter"), clock=clock,
                                 market_data=md, trading_client=trading),
        research_agent=ResearchAgent(_load(registry, "research"), clock=clock,
                                     market_data=md, company_news=news, llm_router=router),
        predict_agent=PredictAgent(_load(registry, "predict")),
        execute_agent=ExecuteAgent(_load(registry, "execute"), clock=clock, trading_client=trading),
        postmortem_agent=PostMortemAgent(_load(registry, "postmortem"),
                                         market_data=md, llm_router=router),
        emitter=emitter, clock=clock if emitter else None, skill_pins=_pins(),
        cycle_config=CYCLE_CONFIG,
    )


def _state():
    return CycleState(
        cycle_id=FIXED_CID, started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1",
    )


def _decisions_blob(state: CycleState) -> str:
    return json.dumps(
        {s: d.model_dump() for s, d in sorted(state.trade_decisions.items())},
        sort_keys=True, default=str,
    )


# ─── THE core acceptance test: OFF vs ON -> byte-identical decisions ─────

async def test_trade_decisions_byte_identical_off_vs_on(registry, tmp_path):
    # emission OFF
    sup_off = _make_supervisor(registry, emitter=None)
    state_off = await sup_off.run_cycle(_state())

    # emission ON
    store_a = StoreA(tmp_path / "store_a.sqlite")
    sup_on = _make_supervisor(registry, emitter=Emitter(store_a, application_id="paper-trader"))
    state_on = await sup_on.run_cycle(_state())

    assert _decisions_blob(state_off) == _decisions_blob(state_on)   # byte-identical
    # and emission ON actually produced trades + a trace
    assert len(state_on.new_paper_trades) == len(state_off.new_paper_trades) == 1
    with store_a.connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM cycle_headers").fetchone()["c"] == 1
        assert conn.execute("SELECT COUNT(*) c FROM agent_invocations").fetchone()["c"] >= 4


async def test_paper_trades_identical_off_vs_on(registry, tmp_path):
    state_off = await _make_supervisor(registry, emitter=None).run_cycle(_state())
    store_a = StoreA(tmp_path / "store_a.sqlite")
    state_on = await _make_supervisor(
        registry, emitter=Emitter(store_a, application_id="paper-trader")
    ).run_cycle(_state())

    def blob(s):
        return json.dumps([t.model_dump() for t in s.new_paper_trades],
                          sort_keys=True, default=str)

    assert blob(state_off) == blob(state_on)


# ─── emission rows are insert-only (never updated/deleted) ───────────────

async def test_emitted_rows_are_insert_only(registry, tmp_path):
    import sqlite3

    store_a = StoreA(tmp_path / "store_a.sqlite")
    await _make_supervisor(
        registry, emitter=Emitter(store_a, application_id="paper-trader")
    ).run_cycle(_state())

    # Store A no-mutation triggers reject any UPDATE/DELETE on either table.
    with store_a.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE cycle_headers SET status='hacked'")
    with store_a.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM agent_invocations")


# ─── header emitted exactly once even across a full cycle ────────────────

async def test_header_emitted_exactly_once(registry, tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    await _make_supervisor(
        registry, emitter=Emitter(store_a, application_id="paper-trader")
    ).run_cycle(_state())
    with store_a.connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM cycle_headers").fetchone()["c"] == 1
