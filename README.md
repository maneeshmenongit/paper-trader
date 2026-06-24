# Paper Trader

A multi-agent paper trading bot for real stocks and crypto, built on LangGraph and
running entirely on free-tier infrastructure. It executes *simulated* trades against
real market prices fetched from yfinance, Finnhub, and CoinGecko — the "exchange" is a
SQLite table, so there is no broker, no exchange account, and no real money at risk.
The system is structured as a supervisor-routed agent graph with five domain agents
(Filter, Research, Predict, Execute, PostMortem).

This is **sandbox #2 for the World Agents framework**. Sandbox #1 (oracle-agents)
validated the core infrastructure patterns — an LLM router with a per-cycle token
budget, seam-based interfaces, per-agent write authorization, two-database separation,
and a LangGraph supervisor — which paper-trader reuses by direct file copy (see the
`# ─── PROVENANCE ───` headers). The full design lives in
[docs/PAPER_TRADER_ARCH_001.md](docs/PAPER_TRADER_ARCH_001.md).
