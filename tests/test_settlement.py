"""Settlement + baseline-scoring tests (Live-Operation T4).

App-db only (no Store A/B ever touched here). Trades close at horizon, get scored
for hit/miss, and carry the momentum baseline shadow. Fakes only, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from paper_trader.agents.execute import ExecuteAgent
from paper_trader.agents.postmortem import PostMortemAgent
from paper_trader.domain import Asset, PaperPortfolio, PaperTrade, View
from paper_trader.graph.state import CycleState
from paper_trader.persistence.db import Database
from paper_trader.persistence.repository import Repository
from paper_trader.settlement import settle_due_trades
from paper_trader.settlement.engine import SettlementContext, horizon_exit_time
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from tests.fixtures.fakes import FakeLLMRouter, FakeMarketData, FakeTradingClient, FrozenClock

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path):
    return Repository(Database(tmp_path / "app.sqlite"))


def _skill(tmp_path, name):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    with reg.connection() as conn:
        return load_skill(conn, version_id_for(name))


def _seed_trade(repo, *, symbol="AAPL", entry=100.0, qty=10.0, exit_hours_ago=1,
                predicted_mag=2.0, baseline_dir="UP", baseline_mag=1.0):
    """Insert an asset, a View prediction (+ baseline shadow), and an open trade."""
    repo.upsert_asset(Asset(symbol=symbol, kind="stock"))
    pid = repo.insert_prediction(
        cycle_id="cyc-1", symbol=symbol, entry_price=entry, method_selected="momentum",
        selection_mode="rule", selection_rationale=None, direction="UP", confidence=0.7,
        magnitude_pct=predicted_mag, time_horizon_hours=24,
        calibration_version="identity-v1", is_baseline=False, created_at=NOW.isoformat(),
    )
    repo.insert_prediction(
        cycle_id="cyc-1", symbol=symbol, entry_price=entry, method_selected="momentum",
        selection_mode="rule", selection_rationale=None, direction=baseline_dir,
        confidence=0.7, magnitude_pct=baseline_mag, time_horizon_hours=24,
        calibration_version="identity-v1", is_baseline=True, created_at=NOW.isoformat(),
    )
    trade = PaperTrade(
        prediction_id=symbol, symbol=symbol, entry_price=entry, quantity=qty,
        notional_value=entry * qty, entry_time=NOW - timedelta(hours=25),
        expected_exit_time=NOW - timedelta(hours=exit_hours_ago),
    )
    tid = repo.insert_paper_trade(cycle_id="cyc-1", prediction_id=pid, trade=trade)
    return pid, tid


# ─── horizon exit time ─────────────────────────────────────────────────────

def test_horizon_exit_time():
    assert horizon_exit_time(NOW, 24) == NOW + timedelta(hours=24)


# ─── settlement engine ─────────────────────────────────────────────────────

async def test_settles_only_due_trades(repo):
    _seed_trade(repo, symbol="DUE", exit_hours_ago=1)      # past horizon
    _seed_trade(repo, symbol="FUTURE", exit_hours_ago=-5)  # 5h in the future
    md = FakeMarketData(quotes={"DUE": 110.0, "FUTURE": 110.0})
    result = await settle_due_trades(repo=repo, market_data=md, clock=FrozenClock(NOW))
    symbols = {t.symbol for t in result.settled_trades}
    assert symbols == {"DUE"}


async def test_settlement_marks_trade_exited_in_db(repo):
    _pid, tid = _seed_trade(repo, symbol="AAPL", entry=100.0)
    md = FakeMarketData(quotes={"AAPL": 108.0})
    await settle_due_trades(repo=repo, market_data=md, clock=FrozenClock(NOW))
    with repo.db.connection() as conn:
        row = conn.execute("SELECT exited, exit_price, exit_time FROM paper_trades WHERE id=?",
                           (tid,)).fetchone()
    assert row["exited"] == 1
    assert row["exit_price"] == pytest.approx(108.0)
    assert row["exit_time"] is not None


async def test_settlement_no_longer_due_on_second_pass(repo):
    _seed_trade(repo, symbol="AAPL")
    md = FakeMarketData(quotes={"AAPL": 108.0})
    first = await settle_due_trades(repo=repo, market_data=md, clock=FrozenClock(NOW))
    second = await settle_due_trades(repo=repo, market_data=md, clock=FrozenClock(NOW))
    assert first.count == 1
    assert second.count == 0  # already exited; idempotent


async def test_settlement_builds_context(repo):
    pid, _ = _seed_trade(repo, symbol="AAPL", predicted_mag=2.5, baseline_mag=1.0)
    md = FakeMarketData(quotes={"AAPL": 108.0})
    result = await settle_due_trades(repo=repo, market_data=md, clock=FrozenClock(NOW))
    ctx = result.contexts[str(pid)]
    assert ctx.predicted_magnitude_pct == pytest.approx(2.5)
    assert ctx.baseline_magnitude_pct == pytest.approx(1.0)  # UP baseline → positive


async def test_settlement_baseline_down_is_signed_negative(repo):
    pid, _ = _seed_trade(repo, symbol="AAPL", baseline_dir="DOWN", baseline_mag=1.5)
    md = FakeMarketData(quotes={"AAPL": 108.0})
    result = await settle_due_trades(repo=repo, market_data=md, clock=FrozenClock(NOW))
    assert result.contexts[str(pid)].baseline_magnitude_pct == pytest.approx(-1.5)


async def test_settlement_pricing_failure_leaves_trade_open(repo):
    _pid, tid = _seed_trade(repo, symbol="AAPL")

    class BoomMarket:
        async def get_current_quote(self, s): raise RuntimeError("no quote")
        async def get_ohlcv(self, s, period_days): return []
        async def get_asset_metadata(self, s): return Asset(symbol=s, kind="stock")

    result = await settle_due_trades(repo=repo, market_data=BoomMarket(), clock=FrozenClock(NOW))
    assert result.count == 0
    with repo.db.connection() as conn:
        row = conn.execute("SELECT exited FROM paper_trades WHERE id=?", (tid,)).fetchone()
    assert row["exited"] == 0  # left open to retry


# ─── Execute sets a real horizon exit time ─────────────────────────────────

async def test_execute_sets_horizon_exit_time(tmp_path):
    skill = _skill(tmp_path, "execute")
    agent = ExecuteAgent(
        skill, clock=FrozenClock(NOW), trading_client=FakeTradingClient(), horizon_hours=24
    )
    view = View(symbol="AAPL", method_selected="momentum", selection_mode="rule",
                direction="UP", magnitude_pct=5.0, horizon=24, confidence=0.9,
                method_inputs_summary={"entry_price": 100.0})
    state = CycleState(cycle_id="c", started_at=NOW,
                       portfolio=PaperPortfolio(cash_balance=100_000.0),
                       watchlist=[], calibration_version="identity-v1",
                       predictions={"AAPL": view})
    out = await agent.run(state)
    trade = out.new_paper_trades[0]
    assert trade.expected_exit_time == trade.entry_time + timedelta(hours=24)


# ─── PostMortem scores hit/miss + baseline shadow via context ──────────────

async def test_postmortem_scores_baseline_shadow(tmp_path):
    skill = _skill(tmp_path, "postmortem")
    # settled trade: entry 100, exit 110, qty 10 → simulated_pnl = 100.
    trade = PaperTrade(
        prediction_id="AAPL", symbol="AAPL", entry_price=100.0, quantity=10.0,
        notional_value=1000.0, entry_time=NOW, expected_exit_time=NOW,
        exited=True, exit_price=110.0, exit_time=NOW,
    )
    ctx = {"AAPL": SettlementContext(prediction_id="AAPL",
                                     predicted_magnitude_pct=3.0,
                                     baseline_magnitude_pct=1.0)}
    agent = PostMortemAgent(
        skill, market_data=FakeMarketData(),
        llm_router=FakeLLMRouter(responses={"bias_tagging": "overconfidence"}),
        settlement_contexts=ctx,
    )
    state = CycleState(cycle_id="c", started_at=NOW,
                       portfolio=PaperPortfolio(cash_balance=10_000.0),
                       watchlist=[], calibration_version="identity-v1",
                       pending_settlements=[trade])
    out = await agent.run(state)
    pm = out.new_post_mortems[0]
    assert pm.simulated_pnl == pytest.approx(100.0)   # traded forecast P&L
    assert pm.baseline_pnl == pytest.approx(10.0)     # 1000 notional * 1.0%
    assert pm.predicted_magnitude_pct == pytest.approx(3.0)  # from the View
    assert pm.actual_magnitude_pct == pytest.approx(10.0)    # (110-100)/100
    assert pm.magnitude_error == pytest.approx(7.0)   # |10 - 3|


async def test_postmortem_uses_settled_exit_price_not_live_quote(tmp_path):
    skill = _skill(tmp_path, "postmortem")
    trade = PaperTrade(
        prediction_id="AAPL", symbol="AAPL", entry_price=100.0, quantity=10.0,
        notional_value=1000.0, entry_time=NOW, expected_exit_time=NOW,
        exited=True, exit_price=105.0, exit_time=NOW,
    )
    # A DIFFERENT live quote must be ignored in favor of the frozen settlement price.
    agent = PostMortemAgent(
        skill, market_data=FakeMarketData(quotes={"AAPL": 999.0}),
        llm_router=FakeLLMRouter(responses={"bias_tagging": "x"}),
    )
    state = CycleState(cycle_id="c", started_at=NOW,
                       portfolio=PaperPortfolio(cash_balance=10_000.0),
                       watchlist=[], calibration_version="identity-v1",
                       pending_settlements=[trade])
    out = await agent.run(state)
    assert out.new_post_mortems[0].simulated_pnl == pytest.approx(50.0)  # 10*(105-100)
