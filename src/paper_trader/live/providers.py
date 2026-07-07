"""Provider factories — the fakes→live swap (Live-Operation T3).

The single place where ``LiveConfig.live_mode`` chooses implementations. Agents
never see this: they are handed protocol-typed objects. In live mode these are the
T1 data clients + a ``LiveTradingClient`` + ``LiveClock`` and the T2
``ConfigurableLLMRouter``; otherwise the Wave 2.5 fakes (so an unconfigured run /
CI stays fully offline).

The LLM router routes Research (classification + summarization) and PostMortem
(bias_tagging) to the chosen open-source provider, with Groq/Gemini as the
ordered fallback — exactly the authority's §3 T2 routing. Predict is not routed
(no Predict LLM path exists).
"""

from __future__ import annotations

from dataclasses import dataclass

from paper_trader.data.clock import LiveClock
from paper_trader.data.interfaces import (
    Clock,
    CompanyNewsProvider,
    CryptoDataProvider,
    MarketDataProvider,
    TradingClient,
)
from paper_trader.live.config import LiveConfig
from paper_trader.live.trading import LiveTradingClient
from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.configurable_router import ConfigurableLLMRouter
from paper_trader.llm.interfaces import LLMClient, LLMPurpose


@dataclass
class DataProviders:
    """The protocol-typed seam bundle a cycle is assembled from."""

    clock: Clock
    market_data: MarketDataProvider
    company_news: CompanyNewsProvider
    crypto_data: CryptoDataProvider
    trading_client: TradingClient


def build_data_providers(config: LiveConfig) -> DataProviders:
    """Live clients when ``config.live_mode`` is on; the Wave 2.5 fakes otherwise."""
    if not config.live_mode:
        return _fake_providers()

    from paper_trader.data.live import (
        CoinGeckoCryptoData,
        FinnhubCompanyNews,
        YFinanceMarketData,
    )
    from paper_trader.data.offline import OfflineCompanyNews

    market_data = YFinanceMarketData()
    crypto_data = CoinGeckoCryptoData()
    # Company news is OPTIONAL: the momentum path is OHLCV-only, and Research
    # R1/R2 already degrade a missing news source to an empty bundle (never a
    # cycle abort). Without a Finnhub key we run live prices with empty news
    # rather than blocking the run — yfinance (no key) is the authority's start.
    company_news = (
        FinnhubCompanyNews(api_key=config.finnhub_api_key)
        if config.finnhub_api_key
        else OfflineCompanyNews()
    )
    return DataProviders(
        clock=LiveClock(),
        market_data=market_data,
        company_news=company_news,
        crypto_data=crypto_data,
        trading_client=LiveTradingClient(market_data=market_data, crypto_data=crypto_data),
    )


def _fake_providers() -> DataProviders:
    # In-package offline seams (paper_trader.data.offline) — the sanctioned
    # offline default. Application-owned, so a live-mode-off run assembles without
    # importing the test tree (which is absent outside pytest).
    from paper_trader.data.offline import (
        OfflineClock,
        OfflineCompanyNews,
        OfflineCryptoData,
        OfflineMarketData,
        OfflineTradingClient,
    )

    return DataProviders(
        clock=OfflineClock(),
        market_data=OfflineMarketData(),
        company_news=OfflineCompanyNews(),
        crypto_data=OfflineCryptoData(),
        trading_client=OfflineTradingClient(),
    )


def build_llm_router(config: LiveConfig, budget: TokenBudget) -> ConfigurableLLMRouter:
    """Assemble the config-selectable router.

    Open-source primary (Ollama or OpenRouter per ``config.llm_provider``) serves
    Research + PostMortem purposes; Groq/Gemini form the ordered fallback when
    their keys are present. In non-live mode this still returns a real router over
    whatever clients are configured — callers under test typically inject a
    ``FakeLLMRouter`` instead and never call this.
    """
    primary = _build_open_source_client(config)
    fallback = _build_hosted_fallback(config)

    # The purposes agents actually issue: Research (classification, summarization),
    # PostMortem (bias_tagging). Each routes to primary → fallback chain.
    open_source_purposes: list[LLMPurpose] = [
        "classification",
        "summarization",
        "bias_tagging",
    ]
    chain = [primary, *fallback]
    routes: dict[LLMPurpose, list[LLMClient]] = {p: chain for p in open_source_purposes}
    default = chain if fallback else [primary]
    return ConfigurableLLMRouter(routes, default=default, budget=budget)


def _build_open_source_client(config: LiveConfig) -> LLMClient:
    if config.llm_provider == "openrouter":
        from paper_trader.llm.openrouter_client import OpenRouterClient

        if not config.openrouter_api_key:
            raise ValueError("llm_provider=openrouter requires OPENROUTER_API_KEY")
        return OpenRouterClient(
            api_key=config.openrouter_api_key, model=config.openrouter_model
        )

    # Default: self-hosted Ollama (no key).
    from paper_trader.llm.ollama_client import OllamaClient

    return OllamaClient(model=config.ollama_model, endpoint=config.ollama_endpoint)


def _build_hosted_fallback(config: LiveConfig) -> list[LLMClient]:
    """Groq/Gemini as the ordered fallback, only when their keys are present."""
    fallback: list[LLMClient] = []
    if config.groq_api_key:
        from paper_trader.llm.groq_client import GroqClient

        fallback.append(GroqClient(api_key=config.groq_api_key))
    if config.gemini_api_key:
        from paper_trader.llm.gemini_client import GeminiClient

        fallback.append(GeminiClient(api_key=config.gemini_api_key))
    return fallback
