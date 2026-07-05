"""Replay-sufficiency assertion (Wave 3 Task 6).

Without building replay, assert a completed cycle's Store A record contains
everything replay will need (reconcile §replay four-source join, Store A sources):
  (1) HEADER: frozen orchestrator_input + orchestrator_decision + decision_mode
      (rule|llm tag) + status + trigger + timing.
  (2) INVOCATIONS (one per agent that ran), each with: skill_version_id pin +
      frozen agent_input + agent_output + timing + status, ordered.
  (3) The skill CONTENT per pin is fetched from the registry BY the pin at replay
      time — so sufficiency here = the pin is present and resolvable.
Source (4) Store B is OUT OF SCOPE this wave (no ledger emission).
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
CID = "01REPLAYCYCLEID000000000AA"
CYCLE_CONFIG = {"cycle_time_horizon_hours": 24, "cycle_token_budget": 15000, "log_level": "INFO"}

HEADER_REQUIRED = [
    "cycle_id", "application_id", "started_at", "ended_at", "trigger_kind",
    "orchestrator_input", "orchestrator_decision", "decision_mode", "status",
]
INVOCATION_REQUIRED = [
    "invocation_id", "cycle_id", "application_id", "agent_name", "skill_version_id",
    "agent_input", "agent_output", "started_at", "ended_at", "status",
]


@pytest.fixture
def registry(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    return reg


def _load(registry, agent):
    with registry.connection() as conn:
        return load_skill(conn, version_id_for(agent))


@pytest.fixture
async def emitted(registry, tmp_path):
    """Run one full emission-ON cycle; return (store_a, registry)."""
    clock = FrozenClock(now=NOW, market_open=True)
    bars = make_ohlcv([100.0] * 24 + [130.0])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    md = FakeMarketData(quotes={"AAPL": 130.0}, ohlcv={"AAPL": bars})
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s"})
    trading = FakeTradingClient()
    store_a = StoreA(tmp_path / "store_a.sqlite")
    pins = {a: version_id_for(a) for a in
            ("filter", "research", "predict", "execute", "postmortem")}
    sup = Supervisor(
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
        clock=clock, skill_pins=pins, cycle_config=CYCLE_CONFIG,
    )
    await sup.run_cycle(
        CycleState(
            cycle_id=CID, started_at=NOW,
            portfolio=PaperPortfolio(cash_balance=10_000.0),
            watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
            calibration_version="identity-v1",
        )
    )
    return store_a, registry


# ─── source 1: header has every replay-required field, non-null ──────────

async def test_header_replay_fields_present(emitted):
    store_a, _ = emitted
    with store_a.connection() as conn:
        header = conn.execute("SELECT * FROM cycle_headers WHERE cycle_id=?", (CID,)).fetchone()
    assert header is not None
    for field in HEADER_REQUIRED:
        assert header[field] is not None, f"header missing replay field: {field}"
    # frozen input + decision are valid JSON (re-derivable by replay)
    assert json.loads(header["orchestrator_input"])
    assert json.loads(header["orchestrator_decision"])
    # decision_mode is the rule|llm tag (DT-4.4)
    assert header["decision_mode"] in ("rule", "llm")


# ─── source 2: one invocation per agent that ran, each replay-complete ───

async def test_invocations_replay_fields_present(emitted):
    store_a, _ = emitted
    with store_a.connection() as conn:
        invs = conn.execute(
            "SELECT * FROM agent_invocations WHERE cycle_id=? ORDER BY invocation_id", (CID,)
        ).fetchall()
    assert len(invs) >= 4  # filter, research, predict, execute all ran
    for inv in invs:
        for field in INVOCATION_REQUIRED:
            assert inv[field] is not None, f"invocation missing replay field: {field}"
        json.loads(inv["agent_input"])   # frozen, re-derivable
        json.loads(inv["agent_output"])  # "no output" is explicit, never null


# ─── source 3: every pin resolves to real skill content in the registry ──

async def test_every_pin_resolves_to_skill_content(emitted):
    store_a, registry = emitted
    with store_a.connection() as conn:
        pins = [r["skill_version_id"] for r in
                conn.execute("SELECT skill_version_id FROM agent_invocations "
                             "WHERE cycle_id=?", (CID,)).fetchall()]
    assert pins  # non-empty
    with registry.connection() as conn:
        for pin in pins:
            skill = load_skill(conn, pin)  # hash-verified load; raises if drifted
            assert "mandate" in skill      # real skill content resolved by the pin


# ─── the whole join is anchored on cycle_id ──────────────────────────────

async def test_join_anchored_on_cycle_id(emitted):
    store_a, _ = emitted
    with store_a.connection() as conn:
        h = conn.execute("SELECT cycle_id FROM cycle_headers").fetchone()["cycle_id"]
        inv_cids = {r["cycle_id"] for r in
                    conn.execute("SELECT cycle_id FROM agent_invocations").fetchall()}
    assert h == CID
    assert inv_cids == {CID}  # all invocations join to the one header
