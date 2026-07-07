"""Execute agent tests (Wave 2.5 Task 5). Risk values from skill; zero LLM."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_trader.agents.execute import ExecuteAgent
from paper_trader.agents.skill_params import ExecuteParams
from paper_trader.domain import NoView, PaperPortfolio, Position, View
from paper_trader.graph.state import CycleState
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from tests.fixtures.fakes import FakeTradingClient, FrozenClock

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def execute_skill(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    with reg.connection() as conn:
        return load_skill(conn, version_id_for("execute"))


def _view(symbol="AAPL", direction="UP", confidence=0.8, magnitude=2.0, is_baseline=False):
    return View(
        symbol=symbol, method_selected="momentum", selection_mode="rule",
        direction=direction, magnitude_pct=magnitude, horizon=24,
        confidence=confidence, is_baseline=is_baseline,
        method_inputs_summary={"entry_price": 100.0},
    )


def _state(preds, portfolio=None):
    return CycleState(
        cycle_id="cyc-1", started_at=NOW,
        portfolio=portfolio or PaperPortfolio(cash_balance=10_000.0),
        watchlist=[], calibration_version="identity-v1",
        predictions=preds,
    )


def _agent(execute_skill, trading=None):
    return ExecuteAgent(
        execute_skill, clock=FrozenClock(now=NOW),
        trading_client=trading or FakeTradingClient(),
    )


# ─── risk values come FROM the skill ─────────────────────────────────────

def test_params_parsed_from_skill(execute_skill):
    p = ExecuteParams(execute_skill)
    assert p.kelly_fraction == 0.25
    assert p.max_position_pct == 0.05
    assert p.min_notional == 100.0
    assert p.max_total_exposure_pct == 0.60
    assert p.max_same_sector == 3
    assert p.max_open_positions == 10
    assert p.daily_loss_halt_pct == 0.05
    assert p.min_confidence == 0.55
    assert p.min_magnitude_pct == 0.005


# ─── happy path: actionable View -> executed trade ───────────────────────

async def test_executed_trade(execute_skill):
    trading = FakeTradingClient()
    agent = _agent(execute_skill, trading)
    state = await agent.run(_state({"AAPL": _view()}))
    d = state.trade_decisions["AAPL"]
    assert d.executed is True and d.risk_reason is None
    assert len(state.new_paper_trades) == 1
    assert state.new_paper_trades[0].direction == "LONG"
    assert len(trading.submitted) == 1  # went through the trading seam


# ─── symmetric logging (C2): every View -> exactly one decision ──────────

async def test_symmetric_logging(execute_skill):
    preds = {"AAPL": _view("AAPL"), "TSLA": _view("TSLA", direction="DOWN")}
    state = await _agent(execute_skill).run(_state(preds))
    assert set(state.trade_decisions) == {"AAPL", "TSLA"}
    assert state.trade_decisions["TSLA"].executed is False
    assert state.trade_decisions["TSLA"].risk_reason == "long_only_v1"


async def test_noview_gets_no_decision(execute_skill):
    preds = {"AAPL": _view("AAPL"), "TSLA": NoView(symbol="TSLA", reason="no_eligible_method")}
    state = await _agent(execute_skill).run(_state(preds))
    assert "TSLA" not in state.trade_decisions       # NoView is not a View
    assert "AAPL" in state.trade_decisions


async def test_baseline_shadow_not_traded(execute_skill):
    state = await _agent(execute_skill).run(_state({"AAPL": _view(is_baseline=True)}))
    assert state.trade_decisions == {}
    assert state.new_paper_trades == []


# ─── gates use the skill floors ──────────────────────────────────────────

async def test_below_confidence_floor_skips(execute_skill):
    state = await _agent(execute_skill).run(_state({"AAPL": _view(confidence=0.50)}))
    assert state.trade_decisions["AAPL"].risk_reason == "below_confidence_floor"


async def test_below_magnitude_floor_skips(execute_skill):
    state = await _agent(execute_skill).run(_state({"AAPL": _view(magnitude=0.2)}))
    assert state.trade_decisions["AAPL"].risk_reason == "below_magnitude_floor"


async def test_max_open_positions_cap(execute_skill):
    pf = PaperPortfolio(
        cash_balance=10_000.0,
        open_positions=[
            Position(symbol=f"S{i}", quantity=1, entry_price=1, notional_value=1)
            for i in range(10)  # already at the cap of 10
        ],
    )
    state = await _agent(execute_skill).run(_state({"AAPL": _view()}, portfolio=pf))
    assert state.trade_decisions["AAPL"].risk_reason == "max_open_positions"


async def test_daily_loss_halt(execute_skill):
    pf = PaperPortfolio(cash_balance=10_000.0, realized_pnl=-600.0)  # -6% > 5% halt
    state = await _agent(execute_skill).run(_state({"AAPL": _view()}, portfolio=pf))
    assert state.trade_decisions["AAPL"].risk_reason == "daily_loss_halt"


# ─── idempotency guard ───────────────────────────────────────────────────

async def test_idempotent_no_double_write(execute_skill):
    agent = _agent(execute_skill)
    state = _state({"AAPL": _view()})
    state = await agent.run(state)
    n_trades = len(state.new_paper_trades)
    # second pass: decision already present -> no new trade
    state = await agent.run(state)
    assert len(state.new_paper_trades) == n_trades


# ─── zero LLM (C3): no router dependency at all ──────────────────────────

def test_no_llm_dependency(execute_skill):
    agent = _agent(execute_skill)
    assert not any("llm" in a.lower() or "router" in a.lower() for a in vars(agent))


# ─── entry price from real momentum close (T6 regression) ────────────────

async def test_entry_price_uses_last_close_when_no_explicit_entry_price(execute_skill):
    # Predict records the real momentum price as last_close (not entry_price).
    # The live run showed every trade filling at the 100.0 fallback because
    # Execute read the wrong key; it must fall back to last_close.
    agent = _agent(execute_skill)
    view = _view()
    view.method_inputs_summary = {"n_closes": 30, "last_close": 312.66}  # real close
    state = await agent.run(_state({"AAPL": view}, PaperPortfolio(cash_balance=100_000.0)))
    trade = state.new_paper_trades[0]
    assert trade.entry_price == pytest.approx(312.66)  # real price, not 100.0
