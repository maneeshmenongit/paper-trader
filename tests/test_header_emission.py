"""Cycle-header emission + freeze tests (Wave 3 Task 4, DT-4.2/4.4)."""

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
from paper_trader.graph.freeze import build_orchestrator_input
from paper_trader.graph.ids import new_cycle_id
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


def _build_supervisor(registry, store_a, tmp_path):
    clock = FrozenClock(now=NOW, market_open=True)
    bars = make_ohlcv([100.0] * 24 + [130.0])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    md = FakeMarketData(quotes={"AAPL": 130.0}, ohlcv={"AAPL": bars})
    news = FakeCompanyNews(news={"AAPL": []})
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s"})
    trading = FakeTradingClient()
    emitter = Emitter(store_a, application_id="paper-trader")
    return Supervisor(
        filter_agent=FilterAgent(_load(registry, "filter"), clock=clock,
                                 market_data=md, trading_client=trading),
        research_agent=ResearchAgent(_load(registry, "research"), clock=clock,
                                     market_data=md, company_news=news, llm_router=router),
        predict_agent=PredictAgent(_load(registry, "predict")),
        execute_agent=ExecuteAgent(_load(registry, "execute"), clock=clock, trading_client=trading),
        postmortem_agent=PostMortemAgent(_load(registry, "postmortem"),
                                         market_data=md, llm_router=router),
        emitter=emitter, clock=clock, skill_pins=_pins(),
        cycle_config=CYCLE_CONFIG, trigger_kind="schedule",
    ), emitter


def _state():
    return CycleState(
        cycle_id=new_cycle_id(FrozenClock(now=NOW)), started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1",
    )


# ─── header emitted once at terminus, with invocations flushed ───────────

async def test_header_emitted_once(registry, tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    sup, emitter = _build_supervisor(registry, store_a, tmp_path)
    await sup.run_cycle(_state())
    with store_a.connection() as conn:
        headers = conn.execute("SELECT * FROM cycle_headers").fetchall()
        invocations = conn.execute("SELECT * FROM agent_invocations").fetchall()
    assert len(headers) == 1
    assert headers[0]["decision_mode"] == "rule"          # DT-4.4
    assert headers[0]["status"] == "completed"
    assert headers[0]["trigger_kind"] == "schedule"
    # invocations flushed after the header (FK satisfied): filter/research/predict/execute
    assert len(invocations) >= 4
    assert emitter.failed_emissions == []


# ─── freeze content: MUST-freeze present, secrets/paths absent ───────────

async def test_frozen_input_has_must_freeze_and_no_secrets(registry, tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    sup, _ = _build_supervisor(registry, store_a, tmp_path)
    await sup.run_cycle(_state())
    with store_a.connection() as conn:
        raw = conn.execute("SELECT orchestrator_input FROM cycle_headers").fetchone()[0]
    frozen = json.loads(raw)
    # MUST-FREEZE
    assert frozen["calibration_version"] == "identity-v1"
    assert frozen["cycle_time_horizon_hours"] == 24
    assert frozen["cycle_token_budget"] == 15000
    assert frozen["research_semaphores"] == {"yfinance": 2, "finnhub_coingecko": 4}
    assert frozen["watchlist"][0]["symbol"] == "AAPL"
    # MUST-NOT-FREEZE: no secret or path anywhere in the serialized trace
    lowered = raw.lower()
    for forbidden in ("api_key", "sqlite", "store_a", "store_b", "checkpointer", "/data/"):
        assert forbidden not in lowered


def test_freeze_builder_drops_injected_secrets():
    state = CycleState(
        cycle_id="c", started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=1.0),
        watchlist=[], calibration_version="identity-v1",
    )
    frozen = build_orchestrator_input(
        state,
        cycle_config={"cycle_token_budget": 15000, "groq_api_key": "SECRET",
                      "store_a_path": "/data/store_a.sqlite"},
    )
    assert frozen["cycle_token_budget"] == 15000
    assert "groq_api_key" not in frozen
    assert "store_a_path" not in frozen


# ─── header non-blocking on failure ──────────────────────────────────────

async def test_header_failure_non_blocking(registry, tmp_path):
    class _BoomHeaderStore:
        def insert_cycle_header(self, **kw):
            raise RuntimeError("disk full")

        def insert_agent_invocation(self, **kw):
            return None

    store_a = StoreA(tmp_path / "store_a.sqlite")
    sup, emitter = _build_supervisor(registry, store_a, tmp_path)
    emitter.store_a = _BoomHeaderStore()  # header write will blow up
    state = await sup.run_cycle(_state())  # must NOT raise
    assert "execute" in state.completed_agents  # cycle completed
    assert any(f.startswith("header:") for f in emitter.failed_emissions)
