"""PostMortem agent tests (Wave 2.5 Task 6). Measures never reacts; app db only."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from paper_trader.agents.postmortem import PostMortemAgent
from paper_trader.domain import PaperPortfolio, PaperTrade
from paper_trader.graph.state import CycleState
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from tests.fixtures.fakes import FakeLLMRouter, FakeMarketData

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def pm_skill(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    with reg.connection() as conn:
        return load_skill(conn, version_id_for("postmortem"))


def _trade(symbol="AAPL", entry=100.0, qty=10.0):
    return PaperTrade(
        prediction_id=symbol, symbol=symbol, entry_price=entry, quantity=qty,
        notional_value=entry * qty, entry_time=NOW, expected_exit_time=NOW,
    )


def _state(settlements, portfolio=None):
    return CycleState(
        cycle_id="cyc-1", started_at=NOW,
        portfolio=portfolio or PaperPortfolio(cash_balance=10_000.0),
        watchlist=[], calibration_version="identity-v1",
        pending_settlements=settlements,
    )


def _agent(pm_skill, *, quotes=None, router=None):
    return PostMortemAgent(
        pm_skill,
        market_data=FakeMarketData(quotes=quotes or {"AAPL": 110.0}),
        llm_router=router or FakeLLMRouter(responses={"bias_tagging": "overconfidence"}),
    )


# ─── scoring: C2 required fields + hit/miss + P&L ────────────────────────

async def test_scores_settlement_fields(pm_skill):
    state = await _agent(pm_skill).run(_state([_trade(entry=100.0, qty=10.0)]))
    pm = state.new_post_mortems[0]
    assert pm.direction_correct is True          # 110 > 100
    assert pm.simulated_pnl == pytest.approx(100.0)  # 10 * (110-100)
    assert pm.actual_magnitude_pct == pytest.approx(10.0)
    assert pm.magnitude_error is not None        # C2: always present


async def test_miss_when_price_fell(pm_skill):
    state = await _agent(pm_skill, quotes={"AAPL": 90.0}).run(_state([_trade()]))
    pm = state.new_post_mortems[0]
    assert pm.direction_correct is False
    assert pm.simulated_pnl == pytest.approx(-100.0)


# ─── C1 completeness: every settlement -> a row ──────────────────────────

async def test_completeness_every_settlement_scored(pm_skill):
    trades = [_trade("AAPL"), _trade("MSFT")]
    agent = _agent(pm_skill, quotes={"AAPL": 110.0, "MSFT": 95.0})
    state = await agent.run(_state(trades))
    assert len(state.new_post_mortems) == 2
    assert {pm.paper_trade_id for pm in state.new_post_mortems} == {"AAPL", "MSFT"}


# ─── R2: portfolio updated on close ──────────────────────────────────────

async def test_portfolio_updated(pm_skill):
    state = await _agent(pm_skill).run(_state([_trade(entry=100.0, qty=10.0)]))
    assert state.portfolio.cash_balance == pytest.approx(10_100.0)  # +100 P&L
    assert state.portfolio.realized_pnl == pytest.approx(100.0)


# ─── empty settlements is valid ──────────────────────────────────────────

async def test_empty_settlements_valid(pm_skill):
    state = await _agent(pm_skill).run(_state([]))
    assert state.new_post_mortems == []


# ─── R3: bias tags batched ~1 call per 4 settlements ─────────────────────

async def test_bias_tags_batched(pm_skill):
    router = FakeLLMRouter(responses={"bias_tagging": "recency"})
    trades = [_trade(f"S{i}") for i in range(9)]  # 9 settlements -> ceil(9/4)=3 calls
    agent = _agent(pm_skill, quotes={f"S{i}": 105.0 for i in range(9)}, router=router)
    await agent.run(_state(trades))
    assert router.calls.count("bias_tagging") == 3


# ─── C3: failed tagging -> null, never invented ──────────────────────────

async def test_bias_tags_null_on_failure(pm_skill):
    router = FakeLLMRouter(fail_purposes={"bias_tagging"})
    state = await _agent(pm_skill, router=router).run(_state([_trade()]))
    assert state.new_post_mortems[0].bias_tags is None


async def test_bias_tags_assigned_on_success(pm_skill):
    router = FakeLLMRouter(responses={"bias_tagging": "overconfidence, recency"})
    state = await _agent(pm_skill, router=router).run(_state([_trade()]))
    assert state.new_post_mortems[0].bias_tags == ["overconfidence", "recency"]


# ─── C4 / §0.4: NEVER Store B — no ledger seam exists on the agent ───────

def test_no_store_b_dependency(pm_skill):
    agent = _agent(pm_skill)
    # structurally: the agent holds no ledger / Store B handle of any kind
    for attr in vars(agent):
        assert "ledger" not in attr.lower()
        assert "store_b" not in attr.lower()
    src = inspect.getsource(PostMortemAgent)
    assert "StoreB" not in src and "ledger" not in src.lower()
    # writes declaration is app-db state only, never a governance store
    assert set(agent.writes) == {"new_post_mortems", "portfolio"}


# ─── bias-tag parsing robustness (T6 regression: 8B model rambled) ───────

async def test_bias_tags_reject_essay_output(pm_skill):
    # The first live run stored Ollama essays ("It seems like you're referring
    # to tag biases in ML...") as bias_tags. Essay-length fragments must be dropped.
    essay = ("It seems like you're referring to the concept of tag biases in "
             "machine learning, which can occur when there's an imbalance")
    agent = _agent(pm_skill, router=FakeLLMRouter(responses={"bias_tagging": essay}))
    state = await agent.run(_state([_trade()]))
    # No fragment is <=3 words, so nothing survives -> null (C3), never an essay.
    assert state.new_post_mortems[0].bias_tags is None


async def test_bias_tags_none_response_yields_null(pm_skill):
    agent = _agent(pm_skill, router=FakeLLMRouter(responses={"bias_tagging": "NONE"}))
    state = await agent.run(_state([_trade()]))
    assert state.new_post_mortems[0].bias_tags is None


async def test_bias_tags_parse_terse_list(pm_skill):
    agent = _agent(pm_skill, router=FakeLLMRouter(
        responses={"bias_tagging": "overconfidence, recency, anchoring"}))
    state = await agent.run(_state([_trade()]))
    assert state.new_post_mortems[0].bias_tags == ["overconfidence", "recency", "anchoring"]
