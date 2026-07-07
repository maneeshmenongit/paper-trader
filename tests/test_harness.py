"""Scheduled run harness tests (Live-Operation T5).

Drives the real settle→cycle→persist→observe loop with REAL Store A/B/registry
(governance on) but FAKE data/LLM seams — no network. Asserts cycles run, trades
land in the app db, replay markdown + observer findings are written per cycle, and
the runner is bounded and interval-driven.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from paper_trader.domain import Asset
from paper_trader.harness.assembly import build_governed_cycle, resolve_skill_pins
from paper_trader.harness.observability import write_cycle_artifacts
from paper_trader.harness.runner import ScheduledRunner
from paper_trader.live.config import load_live_config
from paper_trader.live.providers import DataProviders
from paper_trader.persistence.db import Database
from paper_trader.persistence.repository import Repository
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB
from tests.fixtures.fakes import (
    FakeCompanyNews,
    FakeCryptoData,
    FakeLLMRouter,
    FakeMarketData,
    FakeTradingClient,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)  # Monday, market open


def _fresh_bars(close_last=130.0):
    bars = make_ohlcv([100.0] * 24 + [close_last])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    return bars


def _providers():
    md = FakeMarketData(quotes={"AAPL": 130.0}, ohlcv={"AAPL": _fresh_bars()})
    return DataProviders(
        clock=FrozenClock(now=NOW, market_open=True),
        market_data=md,
        company_news=FakeCompanyNews(news={"AAPL": []}),
        crypto_data=FakeCryptoData(),
        trading_client=FakeTradingClient(),
    )


def _registry(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    return reg


def _no_sleep():
    async def _sleep(_seconds: float) -> None:
        return None

    return _sleep


def _make_runner(tmp_path, *, max_watchlist=None):
    reg = _registry(tmp_path)
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    repo = Repository(Database(tmp_path / "app.sqlite"))
    providers = _providers()
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s",
                                      "bias_tagging": "overconfidence"})
    watchlist = max_watchlist or [Asset(symbol="AAPL", kind="stock", sector="tech")]
    return ScheduledRunner(
        config=load_live_config(env={}),
        providers=providers, registry=reg, llm_router=router,
        store_a=store_a, store_b=store_b, repo=repo,
        clock=FrozenClock(now=NOW, market_open=True),
        run_dir=tmp_path / "run",
        store_a_path=tmp_path / "store_a.sqlite",
        store_b_path=tmp_path / "store_b.sqlite",
        registry_path=reg.path,
        watchlist=watchlist,
        interval_seconds=3600.0,
        sleep=_no_sleep(),
    )


# ─── assembly ──────────────────────────────────────────────────────────────

def test_resolve_skill_pins_uses_seeded_v1_when_no_current(tmp_path):
    pins = resolve_skill_pins(_registry(tmp_path))
    assert pins["predict"] == version_id_for("predict")
    assert set(pins) == {"filter", "research", "predict", "execute", "postmortem"}


async def test_governed_cycle_runs_and_emits(tmp_path):
    from paper_trader.domain import PaperPortfolio
    from paper_trader.graph.state import CycleState

    reg = _registry(tmp_path)
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    cycle = build_governed_cycle(
        providers=_providers(), registry=reg,
        llm_router=FakeLLMRouter(responses={"classification": "ai", "summarization": "s"}),
        store_a=store_a, store_b=store_b, clock=FrozenClock(now=NOW, market_open=True),
    )
    state = CycleState(
        cycle_id="cyc-gov", started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=100_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1",
    )
    out = await cycle.supervisor.run_cycle(state)
    assert out.trade_decisions["AAPL"].executed is True
    # Store A got a cycle header (emission on).
    with store_a.connection() as conn:
        headers = conn.execute("SELECT * FROM cycle_headers WHERE cycle_id=?",
                               ("cyc-gov",)).fetchall()
    assert len(headers) == 1
    assert headers[0]["trigger_kind"] == "schedule"


# ─── runner ────────────────────────────────────────────────────────────────

async def test_runner_runs_bounded_cycles(tmp_path):
    runner = _make_runner(tmp_path)
    result = await runner.run(max_cycles=3)
    assert result.count == 3
    # each cycle produced a distinct ULID cycle_id
    assert len({c.cycle_id for c in result.cycles}) == 3


async def test_runner_executes_trades_into_app_db(tmp_path):
    runner = _make_runner(tmp_path)
    await runner.run(max_cycles=1)
    with runner.repo.db.connection() as conn:
        trades = conn.execute("SELECT * FROM paper_trades").fetchall()
    assert len(trades) >= 1
    assert trades[0]["symbol"] == "AAPL"


async def test_runner_writes_observability_artifacts(tmp_path):
    runner = _make_runner(tmp_path)
    result = await runner.run(max_cycles=1)
    cid = result.cycles[0].cycle_id
    run_dir = tmp_path / "run"
    assert (run_dir / f"{cid}.replay.md").exists()
    assert (run_dir / f"{cid}.findings.json").exists()
    # replay markdown reconstructs the live cycle
    md = (run_dir / f"{cid}.replay.md").read_text()
    assert cid in md
    assert result.cycles[0].all_pins_verified is True


async def test_runner_settles_across_cycles(tmp_path):
    # First cycle opens a trade (expected_exit = entry + 24h). A later cycle whose
    # clock is past the horizon must settle it.
    runner = _make_runner(tmp_path)
    await runner.run(max_cycles=1)
    with runner.repo.db.connection() as conn:
        open_before = conn.execute("SELECT COUNT(*) c FROM paper_trades WHERE exited=0").fetchone()
    assert open_before["c"] >= 1

    # advance the clock past the horizon and run again
    runner.clock = FrozenClock(now=NOW + timedelta(hours=25), market_open=True)
    result = await runner.run(max_cycles=1)
    assert result.cycles[0].settlements >= 1
    with runner.repo.db.connection() as conn:
        settled = conn.execute("SELECT COUNT(*) c FROM paper_trades WHERE exited=1").fetchone()
    assert settled["c"] >= 1


async def test_observability_standalone(tmp_path):
    # write_cycle_artifacts works on a cycle emitted by a governed run.
    runner = _make_runner(tmp_path)
    result = await runner.run(max_cycles=1)
    cid = result.cycles[0].cycle_id
    obs = write_cycle_artifacts(
        cycle_id=cid, run_dir=tmp_path / "obs2",
        store_a_path=Path(tmp_path / "store_a.sqlite"),
        store_b_path=Path(tmp_path / "store_b.sqlite"),
        registry_path=runner.registry.path,
    )
    assert obs.replay_path.exists()
    assert obs.all_pins_verified is True


async def test_run_summary_grounded_in_records(tmp_path):
    from paper_trader.harness.summary import summarize_run

    runner = _make_runner(tmp_path)
    # cycle 1 opens a trade; advance past horizon so cycle 2 settles + scores it.
    await runner.run(max_cycles=1)
    runner.clock = FrozenClock(now=NOW + timedelta(hours=25), market_open=True)
    await runner.run(max_cycles=1)

    summary = summarize_run(app_db_path=tmp_path / "app.sqlite", run_dir=tmp_path / "run")
    assert summary.trades_executed >= 1
    assert summary.trades_settled >= 1
    assert summary.post_mortems >= 1
    assert "AAPL" in summary.symbols_traded
    assert summary.replay_cycles >= 2
    assert summary.all_pins_verified is True
    # baseline shadow is scored alongside the trade P&L (both present).
    assert isinstance(summary.baseline_pnl, float)
