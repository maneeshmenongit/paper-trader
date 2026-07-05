"""Seams + fakes + registry-config tests (Wave 2.5 Task 2). No network calls."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_trader.config import open_skill_registry, skill_registry_path
from paper_trader.data.clock import LiveClock
from paper_trader.data.interfaces import (
    Clock,
    CompanyNewsProvider,
    CryptoDataProvider,
    MarketDataProvider,
    TradingClient,
)
from paper_trader.domain import Asset, PaperTrade, TradeDecision
from paper_trader.persistence.db import Database
from paper_trader.persistence.repository import Repository
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from tests.fixtures.fakes import (
    FakeCompanyNews,
    FakeCryptoData,
    FakeLLMRouter,
    FakeMarketData,
    FakeTradingClient,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 5, tzinfo=UTC)


# ─── fakes satisfy their protocols ───────────────────────────────────────

def test_fakes_are_protocol_instances():
    assert isinstance(FakeMarketData(), MarketDataProvider)
    assert isinstance(FakeCompanyNews(), CompanyNewsProvider)
    assert isinstance(FakeCryptoData(), CryptoDataProvider)
    assert isinstance(FakeTradingClient(), TradingClient)
    assert isinstance(FrozenClock(), Clock)
    assert isinstance(LiveClock(), Clock)


async def test_fake_market_data_returns_injected():
    md = FakeMarketData(quotes={"AAPL": 190.0}, ohlcv={"AAPL": make_ohlcv([1, 2, 3])})
    assert await md.get_current_quote("AAPL") == 190.0
    assert len(await md.get_ohlcv("AAPL", 30)) == 3
    meta = await md.get_asset_metadata("AAPL")
    assert meta.symbol == "AAPL"


def test_frozen_clock_market_open_control():
    assert FrozenClock(market_open=False).is_market_open("stock") is False
    assert FrozenClock(market_open=False).is_market_open("crypto") is True


def test_fake_llm_router_counts_and_scripts():
    r = FakeLLMRouter(responses={"summarization": "hello"}, tokens_per_call=7)
    text, tokens = r.call("summarization", "sys", "user")
    assert text == "hello" and tokens == 7
    assert r.calls == ["summarization"]
    with pytest.raises(RuntimeError):
        FakeLLMRouter(fail_purposes={"reasoning"}).call("reasoning", "s", "u")


# ─── registry config: read-only skill access ────────────────────────────

def test_skill_registry_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_REGISTRY_DB_PATH", str(tmp_path / "skills.sqlite"))
    assert skill_registry_path() == tmp_path / "skills.sqlite"


def test_open_registry_and_load_seeded_skill(tmp_path):
    reg = open_skill_registry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    with reg.connection() as conn:
        skill = load_skill(conn, version_id_for("filter"))
    assert "rules" in skill  # loaded read-only through the framework loader


def test_store_b_wired_for_observer(tmp_path):
    # Wave 4: Store B is wired so the observer half can write the ledger. The
    # fast-loop AGENTS still never touch it — only the observer does.
    from paper_trader.config import open_store_b, store_b_path

    assert store_b_path().name == "store_b.sqlite"
    store = open_store_b(tmp_path / "store_b.sqlite")
    assert store.path.exists()  # framework StoreB DDL applied on open


# ─── app-db repository round-trip ────────────────────────────────────────

@pytest.fixture
def repo(tmp_path):
    return Repository(Database(tmp_path / "paper_trader.sqlite"))


def test_repository_prediction_and_decision_roundtrip(repo):
    repo.upsert_asset(Asset(symbol="AAPL", kind="stock", sector="tech"))
    pid = repo.insert_prediction(
        cycle_id="cyc-1", symbol="AAPL", entry_price=100.0,
        method_selected="momentum", selection_mode="rule", selection_rationale=None,
        direction="UP", confidence=0.7, magnitude_pct=1.0, time_horizon_hours=24,
        calibration_version="identity-v1", is_baseline=False, created_at="2026-07-05T00:00:00Z",
    )
    assert pid > 0
    repo.insert_trade_decision(
        cycle_id="cyc-1", prediction_id=pid,
        decision=TradeDecision(prediction_id="AAPL", symbol="AAPL", executed=True),
        created_at="2026-07-05T00:00:00Z",
    )
    assert repo.count_trade_decisions_for_prediction(pid) == 1


def test_repository_paper_trade_roundtrip(repo):
    repo.upsert_asset(Asset(symbol="AAPL", kind="stock"))
    pid = repo.insert_prediction(
        cycle_id="cyc-1", symbol="AAPL", entry_price=100.0,
        method_selected="momentum", selection_mode="rule", selection_rationale=None,
        direction="UP", confidence=0.7, magnitude_pct=1.0, time_horizon_hours=24,
        calibration_version="identity-v1", is_baseline=False, created_at="2026-07-05T00:00:00Z",
    )
    tid = repo.insert_paper_trade(
        cycle_id="cyc-1", prediction_id=pid,
        trade=PaperTrade(
            prediction_id=str(pid), symbol="AAPL", entry_price=100.0, quantity=5,
            notional_value=500.0, entry_time=NOW, expected_exit_time=NOW,
        ),
    )
    assert tid > 0
