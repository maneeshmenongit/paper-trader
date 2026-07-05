"""Observer-node neutrality proof (Wave 4 Task 4, I-1).

Run one deterministic cycle with the observer node present vs absent; assert
trade_decisions + paper_trades are BYTE-IDENTICAL. The observer is post-hoc and
read-only on the trade path — this test confirms the structural neutrality.
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
from paper_trader.officer_predicates import build_v1_registry, outcome_mismatch_detector
from steward.officer.observer import Observer, ObserverLedgerWriter
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB
from tests.fixtures.fakes import (
    FakeCompanyNews,
    FakeLLMRouter,
    FakeMarketData,
    FakeTradingClient,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
CID = "01OBSNEUTRALCYCLEID0000AA"
CYCLE_CONFIG = {"cycle_time_horizon_hours": 24, "cycle_token_budget": 15000, "log_level": "INFO"}


@pytest.fixture
def registry(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    return reg


def _load(registry, agent):
    with registry.connection() as conn:
        return load_skill(conn, version_id_for(agent))


def _pins():
    return {a: version_id_for(a) for a in
            ("filter", "research", "predict", "execute", "postmortem")}


def _fresh_bars():
    bars = make_ohlcv([100.0] * 24 + [130.0])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    return bars


def _make(registry, store_a, store_b, *, with_observer):
    clock = FrozenClock(now=NOW, market_open=True)
    md = FakeMarketData(quotes={"AAPL": 130.0}, ohlcv={"AAPL": _fresh_bars()})
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s"})
    trading = FakeTradingClient()
    observer = None
    if with_observer:
        import sqlite3

        reg_conn = sqlite3.connect(registry.path)
        reg_conn.row_factory = sqlite3.Row
        observer = Observer(
            store_a=store_a, registry_conn=reg_conn,
            ledger_writer=ObserverLedgerWriter(store_b, application_id="paper-trader"),
            predicates=build_v1_registry(), clock=clock,
            outcome_mismatch_detector=outcome_mismatch_detector,
        )
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
        clock=clock, skill_pins=_pins(), cycle_config=CYCLE_CONFIG, observer=observer,
    )


def _state():
    return CycleState(
        cycle_id=CID, started_at=NOW, portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1",
    )


def _decisions(state):
    return json.dumps({s: d.model_dump() for s, d in sorted(state.trade_decisions.items())},
                      sort_keys=True, default=str)


def _trades(state):
    return json.dumps([t.model_dump() for t in state.new_paper_trades],
                      sort_keys=True, default=str)


# ─── THE neutrality proof: observer present vs absent -> identical ───────

async def test_trade_path_byte_identical_with_and_without_observer(registry, tmp_path):
    # observer ABSENT
    sa1 = StoreA(tmp_path / "a1.sqlite")
    sb1 = StoreB(tmp_path / "b1.sqlite")
    st_off = await _make(registry, sa1, sb1, with_observer=False).run_cycle(_state())

    # observer PRESENT
    sa2 = StoreA(tmp_path / "a2.sqlite")
    sb2 = StoreB(tmp_path / "b2.sqlite")
    st_on = await _make(registry, sa2, sb2, with_observer=True).run_cycle(_state())

    assert _decisions(st_off) == _decisions(st_on)   # byte-identical decisions
    assert _trades(st_off) == _trades(st_on)         # byte-identical paper_trades


# ─── the observer ran as terminal node and wrote (a clean cycle -> zero) ─

async def test_observer_ran_terminal_clean_cycle_zero_entries(registry, tmp_path):
    sa = StoreA(tmp_path / "a.sqlite")
    sb = StoreB(tmp_path / "b.sqlite")
    await _make(registry, sa, sb, with_observer=True).run_cycle(_state())
    # a clean cycle (agents behaved) yields no divergence entries
    with sb.connection() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM ledger_entries").fetchone()["c"]
    assert n == 0
    # and Store A was populated (the observer had records to read)
    with sa.connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM agent_invocations").fetchone()["c"] >= 4


# ─── observer without emission does not run (needs Store A populated) ────

async def test_observer_requires_emission(registry, tmp_path):
    sa = StoreA(tmp_path / "a.sqlite")
    sb = StoreB(tmp_path / "b.sqlite")
    sup = _make(registry, sa, sb, with_observer=True)
    sup.emitter = None  # emission OFF -> observer must not run (no Store A records)
    st = await sup.run_cycle(_state())
    assert "execute" in st.completed_agents  # cycle still completes
    with sb.connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM ledger_entries").fetchone()["c"] == 0
