"""Live config + watchlist + provider-swap tests (Live-Operation T3).

No network: live-mode factories are asserted to CONSTRUCT the right client types
(the clients' own network calls are never invoked here). Non-live mode returns the
Wave 2.5 fakes. Secrets never appear in a redacted view or the frozen trace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_trader.data.interfaces import (
    CompanyNewsProvider,
    CryptoDataProvider,
    MarketDataProvider,
    TradingClient,
)
from paper_trader.domain import Asset, OHLCVBar
from paper_trader.live.config import load_live_config
from paper_trader.live.providers import build_data_providers, build_llm_router
from paper_trader.live.trading import LiveTradingClient
from paper_trader.live.watchlist import parse_watchlist
from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.configurable_router import ConfigurableLLMRouter

# ─── config ──────────────────────────────────────────────────────────────

def test_defaults_are_offline_and_safe():
    cfg = load_live_config(env={})
    assert cfg.live_mode is False
    assert cfg.llm_provider == "ollama"
    assert cfg.ollama_endpoint == "http://localhost:11434"
    assert cfg.finnhub_api_key == ""


def test_live_mode_flag_parsed():
    assert load_live_config(env={"PAPER_TRADER_LIVE_MODE": "true"}).live_mode is True
    assert load_live_config(env={"PAPER_TRADER_LIVE_MODE": "1"}).live_mode is True
    assert load_live_config(env={"PAPER_TRADER_LIVE_MODE": "no"}).live_mode is False


def test_config_reads_secrets_and_models():
    cfg = load_live_config(
        env={
            "PAPER_TRADER_LIVE_MODE": "1",
            "FINNHUB_API_KEY": "fk",
            "OPENROUTER_API_KEY": "ok",
            "PAPER_TRADER_LLM_PROVIDER": "openrouter",
            "OLLAMA_MODEL": "llama3.1:70b",
        }
    )
    assert cfg.finnhub_api_key == "fk"
    assert cfg.llm_provider == "openrouter"
    assert cfg.ollama_model == "llama3.1:70b"


def test_redacted_masks_secrets():
    cfg = load_live_config(env={"FINNHUB_API_KEY": "supersecret", "GROQ_API_KEY": ""})
    red = cfg.redacted()
    assert "supersecret" not in str(red)
    assert red["finnhub_api_key"] == "set"
    assert red["groq_api_key"] == "unset"


# ─── watchlist ─────────────────────────────────────────────────────────────

def test_watchlist_parses_stocks_and_crypto():
    assets = parse_watchlist(
        {
            "asset": [
                {"symbol": "AAPL", "kind": "stock", "sector": "Technology"},
                {"symbol": "BTC", "kind": "crypto"},
            ]
        }
    )
    assert assets == [
        Asset(symbol="AAPL", kind="stock", sector="Technology"),
        Asset(symbol="BTC", kind="crypto", sector=None),
    ]


def test_watchlist_rejects_unknown_kind():
    with pytest.raises(ValueError, match="kind must be one of"):
        parse_watchlist({"asset": [{"symbol": "X", "kind": "bond"}]})


def test_watchlist_rejects_missing_symbol():
    with pytest.raises(ValueError, match="missing a symbol"):
        parse_watchlist({"asset": [{"kind": "stock"}]})


def test_watchlist_rejects_duplicates():
    with pytest.raises(ValueError, match="duplicate"):
        parse_watchlist(
            {"asset": [{"symbol": "AAPL", "kind": "stock"}, {"symbol": "AAPL", "kind": "stock"}]}
        )


def test_watchlist_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        parse_watchlist({"asset": []})


def test_shipped_watchlist_file_loads():
    from paper_trader.live.watchlist import load_watchlist

    assets = load_watchlist(Path("config/watchlist.toml"))
    assert len(assets) >= 1
    assert any(a.kind == "crypto" for a in assets)
    assert any(a.kind == "stock" for a in assets)


# ─── provider swap ─────────────────────────────────────────────────────────

def test_non_live_mode_returns_offline_defaults():
    from paper_trader.data.offline import OfflineClock, OfflineMarketData

    providers = build_data_providers(load_live_config(env={}))
    assert isinstance(providers.clock, OfflineClock)
    assert isinstance(providers.market_data, OfflineMarketData)
    # still protocol-conformant
    assert isinstance(providers.market_data, MarketDataProvider)
    assert isinstance(providers.company_news, CompanyNewsProvider)
    assert isinstance(providers.crypto_data, CryptoDataProvider)
    assert isinstance(providers.trading_client, TradingClient)


def test_live_mode_constructs_live_clients():
    from paper_trader.data.clock import LiveClock
    from paper_trader.data.live import (
        CoinGeckoCryptoData,
        FinnhubCompanyNews,
        YFinanceMarketData,
    )

    cfg = load_live_config(env={"PAPER_TRADER_LIVE_MODE": "1", "FINNHUB_API_KEY": "fk"})
    providers = build_data_providers(cfg)
    assert isinstance(providers.clock, LiveClock)
    assert isinstance(providers.market_data, YFinanceMarketData)
    assert isinstance(providers.company_news, FinnhubCompanyNews)
    assert isinstance(providers.crypto_data, CoinGeckoCryptoData)
    assert isinstance(providers.trading_client, LiveTradingClient)


def test_live_mode_without_finnhub_key_degrades_to_empty_news():
    # Finnhub is optional: the momentum path is OHLCV-only and Research degrades a
    # missing news source to empty. Live mode still assembles (yfinance needs no key).
    from paper_trader.data.live import YFinanceMarketData
    from paper_trader.data.offline import OfflineCompanyNews

    cfg = load_live_config(env={"PAPER_TRADER_LIVE_MODE": "1"})  # no finnhub key
    providers = build_data_providers(cfg)
    assert isinstance(providers.market_data, YFinanceMarketData)
    assert isinstance(providers.company_news, OfflineCompanyNews)  # empty news, no abort


# ─── LLM router assembly ───────────────────────────────────────────────────

def test_router_routes_open_source_purposes():
    cfg = load_live_config(env={"PAPER_TRADER_LLM_PROVIDER": "ollama"})
    router = build_llm_router(cfg, TokenBudget(per_cycle_limit=1000))
    assert isinstance(router, ConfigurableLLMRouter)
    # Research + PostMortem purposes route to the ollama primary.
    for purpose in ("classification", "summarization", "bias_tagging"):
        chain = router.routes[purpose]
        assert chain[0].name == "ollama"


def test_router_openrouter_primary_with_groq_fallback():
    cfg = load_live_config(
        env={
            "PAPER_TRADER_LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "ok",
            "GROQ_API_KEY": "gk",
        }
    )
    router = build_llm_router(cfg, TokenBudget(per_cycle_limit=1000))
    chain = router.routes["bias_tagging"]
    assert chain[0].name == "openrouter"
    assert "groq" in [c.name for c in chain]  # fallback present


def test_router_openrouter_requires_key():
    cfg = load_live_config(env={"PAPER_TRADER_LLM_PROVIDER": "openrouter"})
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        build_llm_router(cfg, TokenBudget(per_cycle_limit=1000))


# ─── LiveTradingClient liquidity ───────────────────────────────────────────

async def test_live_trading_stock_liquidity_is_avg_dollar_volume():
    from datetime import UTC, datetime

    class MD:
        async def get_ohlcv(self, symbol, period_days):
            return [
                OHLCVBar(
                    timestamp=datetime(2026, 6, i + 1, tzinfo=UTC),
                    open=10, high=10, low=10, close=10.0, volume=1_000_000,
                )
                for i in range(3)
            ]

        async def get_current_quote(self, s): return 10.0
        async def get_asset_metadata(self, s): return Asset(symbol=s, kind="stock")

    client = LiveTradingClient(market_data=MD(), crypto_data=_NullCrypto())
    liq = await client.get_liquidity_metric("AAPL", "stock")
    assert liq == pytest.approx(10_000_000.0)  # 10 * 1,000,000


async def test_live_trading_crypto_liquidity_is_24h_volume():
    class Crypto:
        async def get_market_data(self, symbol):
            return {"volume_24h": 55_000_000_000.0}

        async def get_crypto_news(self, s, since): return []

    client = LiveTradingClient(market_data=_NullMarket(), crypto_data=Crypto())
    assert await client.get_liquidity_metric("BTC", "crypto") == pytest.approx(55_000_000_000.0)


async def test_live_trading_missing_data_returns_zero():
    client = LiveTradingClient(market_data=_NullMarket(), crypto_data=_NullCrypto())
    assert await client.get_liquidity_metric("AAPL", "stock") == 0.0


async def test_live_trading_fill_at_quoted_price():
    client = LiveTradingClient(market_data=_NullMarket(), crypto_data=_NullCrypto())
    assert await client.submit_paper_trade("AAPL", 10, 123.45) == pytest.approx(123.45)


class _NullMarket:
    async def get_current_quote(self, s): return 0.0
    async def get_ohlcv(self, s, period_days): return []
    async def get_asset_metadata(self, s): return Asset(symbol=s, kind="stock")


class _NullCrypto:
    async def get_market_data(self, s): return {}
    async def get_crypto_news(self, s, since): return []
