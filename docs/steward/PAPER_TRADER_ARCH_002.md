# Paper Trader — System Architecture (v2)

**Document ID:** `PAPER_TRADER_ARCH_002`
**Supersedes:** `PAPER_TRADER_ARCH_001` (v1, April 2026)
**Author:** Claude (Technical Architect role)
**Date:** June 2026
**Status:** Transitional — v1 domain/infra body retained verbatim; thesis and governance framing updated. NOT yet fully reconciled against Steward (that is Phase 3's section-by-section job).
**Depends on:** `STEWARD_FRAMEWORK_SPEC_001.md` (the governance framework this application now sits on), `PAPER_TRADER_HANDOFF_001.md` (original scope, validated patterns, zero-cost stack)
**Lineage:** Sibling of `ORACLE_AGENTS_ARCH_001`. Reuses validated infrastructure patterns from oracle-agents by direct file copy; the domain layer, data interfaces, supervisor routing decisions, and scoring math are new. **As of v2, paper-trader is the first application of the Steward framework, not a standalone "sandbox #2."**
**Successor:** `PAPER_TRADER_PRD_001` (Product Manager) → `PAPER_TRADER_STRATEGY_001` (Strategist) → `PAPER_TRADER_HANDOFF_001` build sequence

---

## 0. v2 Change Note — Read This First

This document is `ARCH_001` (April 2026) with **targeted corrections**, not a ground-up rewrite. The full reconciliation of paper-trader against the Steward framework is Phase 3 work, done section by section. This note records what changed in v2 and what is deliberately left for that reconciliation, so no reader mistakes the unchanged body for "already reconciled."

### 0.1 Why v2 exists
Two things made v1 stale:

1. **The Predict thesis died.** The T02–T04 thesis backtest returned a decisive **NO-GO** on the v1 Predict design (LLM-as-forecaster predicting next-day direction from price): **+0.1pp edge vs. the +3.0pp required**, and on the head-to-head subset the momentum baseline actually beat the LLM (47 vs. 36). The specific thesis v1 encodes — Predict emits UP/DOWN/HOLD with magnitude/confidence by asking the LLM to forecast — is **dead**, not wounded. See §6.2 (Predict) and ADR-PT-003, both updated.
2. **Governance moved into a framework.** Paper-trader is now the first application of **Steward** (`STEWARD_FRAMEWORK_SPEC_001.md`), a governance-aware multi-agent framework. v1 was written as "sandbox #2 for the World Agents framework," validating infrastructure patterns only. It was never designed against a governance thesis. Adding that thesis is what Phase 3 does.

### 0.2 The live Predict thesis (replaces the dead one)
**LLM-as-method-selector**, held explicitly as **UNVALIDATED**. The Predict agent no longer forecasts. It routes among its *own* forecasting tools (e.g. momentum, mean-reversion, ARIMA, gradient-boosted models), selecting by LLM judgment where no skill rule yet covers the case. It returns a view — including an honest "no view + explanation" — to whoever invoked it, and never invokes a sibling agent. Routing-uncertainty is a valid no-view, not a retry; only transient *infrastructure* failures get backoff+jitter+capped retries. Its routing rules accrete into skills through Steward's governed slow loop. It carries a **timestamped thesis-status flag** (`UNVALIDATED → VALIDATED/FAILED`, with date + evidence refs) that the slow loop flips only on evidence. Full design is pinned in the Steward Phase-2 work and is the template for §6 Predict — but note the template must be **rebuilt from this thesis**, not lifted from the v1 §6 text.

### 0.3 Reconciliation map (provisional — to be confirmed by Phase 3's line read)
How this document's parts map onto Steward. This is the starting map, not the finished reconciliation.

- **Survives essentially unchanged (domain reality, no governance content):** the data layer and seams (§7 — yfinance/Finnhub/CoinGecko protocols), persistence mechanics (§8 — two-DB separation), configuration (§9 — watchlist + risk gates), cost model (§11), analytics (§10 — Kelly, technicals, P&L, scoring). Steward is application-agnostic; it does not touch these.
- **Survives but remaps onto Steward components:**
  - The **Supervisor (§5)** → Steward's **orchestrator**, with a real tension to resolve in Phase 3: v1's "hybrid routing" downgrades **LLM→deterministic when token budget runs low** (line ~23, Decision D), whereas Steward's fallback escalates **rule→LLM when no rule covers the case**. Near-opposite triggers under the same "hybrid routing" label — must be reconciled, not assumed equivalent. Note also that v1 **already has one LLM-driven routing decision** (Decision B, post-settlement prompt adjustment) — that is the seed of Steward's LLM-fallback slot, not a counterexample to it.
  - The **CycleState schema (§4)** → Steward's **cycle header + agent-invocation records (Store A)**. Overlapping mechanism, different purpose: v1's CycleState exists for **crash recovery**; Steward's trace exists for **reconstructive replay** with FROZEN decision fields and `skill_version_id` pins. The schema gains version-pinning it does not currently have.
  - The **agent contracts (§6)** → Steward **agents reading pinned skill files**. The contracts are the *seed* of skill files but currently lack versioning, invocation-time pinning, and — critically — **explicitly declared constraints**. (In Steward the officer can only flag *divergence from what a skill states*, so a vague contract produces zero evidence. This pressures every contract toward explicit declared constraints.)
- **Net-new — no equivalent in this document at all:** the **correction officer**, the **ledger (Store B)**, the **slow loop** (proposer → human gate → version fork), **skill versioning + reconstructive replay**, and the **proposal lifecycle**. None of these exist in paper-trader today. Making paper-trader a Steward application is principally *adding this governance half.*

### 0.4 The PostMortem trap (hold this line)
**PostMortem is NOT the correction officer.** It is the closest-looking thing and it is a different job. PostMortem (§6.2, §8) is a **fast-loop domain agent** that scores prediction outcomes (hit/miss, P&L, magnitude error, bias tags) and writes to the **application database**. The officer is a **slow-loop-coupled observer** that watches for **skill-divergence** and writes **neutral evidence to a one-way ledger** that never drives automatic action. Outcome-scoring and governance-observation are categorically different; conflating them collapses Steward's membrane on day one. In Phase 3, **PostMortem survives as a domain agent and the officer is built alongside it** — they are not the same component and one does not replace the other.

### 0.5 What this v2 did and did NOT change
- **Changed:** §0 (this note, new), header block, §1 framing (sandbox → Steward application), §6.2 Predict (dead thesis → method-selector), ADR-PT-003 (annotated as superseded-at-thesis-level).
- **Deliberately NOT changed:** the entire infrastructure/domain body (§2–§5, §7–§13 except the Predict touches) is retained **verbatim from v1**, because Phase 3 reconciles it section by section against the frozen Steward spec. Treating any unchanged section as "already reconciled" would defeat the purpose. Where v1 text still encodes the dead thesis incidentally (e.g. the `direction IN ('UP','DOWN','HOLD')` prediction schema in §8, Decision E's "if no UP predictions" in §5.2, the contract table's Predict row in §6.1), those are **flagged inline with `[v2-FLAG]`** but not rewritten — their rewrite belongs to the Phase 3 pass that designs the method-selector's actual output shape.

---

## 1. High-Level Summary

Paper Trader is a multi-agent paper trading bot for real stocks and crypto, built on LangGraph, running entirely on free-tier infrastructure, executing simulated trades against real market prices fetched from yfinance, Finnhub, and CoinGecko. The "exchange" is a SQLite table — no broker, no exchange account, no real money. The system is structured as a **supervisor-routed agent graph** with five domain agents (Filter, Research, Predict, Execute, PostMortem) and a central Supervisor that dispatches work based on the current state of the trading cycle.

**This is the first application of the Steward framework.** *(v2: in v1 this read "sandbox #2 for the World Agents framework." The infrastructure-pattern lineage below is still accurate history, but paper-trader's governing identity is now Steward — see §0.)* Sandbox #1 (oracle-agents, prediction markets on Manifold) validated five infrastructure patterns: an LLM router with per-cycle token budget, seam-based interfaces, per-agent write authorization, two-database separation, and a LangGraph supervisor with hybrid deterministic/LLM routing. Paper Trader **reuses these patterns by direct file copy** from oracle-agents, not by depending on it as a library. Approximately 600 lines of pure-infrastructure code are deliberately duplicated; extraction into a shared `worldwise-core` package is a Phase 2+ task once both sandboxes are alive and the real shape of the abstraction is visible from a sample size of two.

The architecture is designed around the same three principles as oracle-agents — and they apply for the same reasons:

1. **Seams over plumbing.** Every external dependency (yfinance, Finnhub, CoinGecko, Groq, Gemini, the clock, the news feeds) is accessed through a `Protocol`, not a concrete class. Live implementations injected at boot; fakes used in tests; Phase 2 backtest implementations slot in without touching agent code.
2. **State is sacred.** Two separate state stores: LangGraph's `SqliteSaver` checkpointer holds in-cycle state for crash recovery; a separate SQLite application database holds cross-cycle history (predictions, paper trades, post-mortems, calibration). They never share a connection or a schema.
3. **Cost discipline is structural, not aspirational.** Free-tier LLM limits are baked into the architecture as a per-cycle token budget enforced by the supervisor. When budget runs low, the supervisor downgrades from LLM routing to deterministic routing automatically.

**Two new principles** earned by adapting from oracle-agents to a real-asset domain:

4. **Settle before scan.** Cross-cycle state changes (closing out trades whose horizon has elapsed) happen at the *start* of every cycle, before the Filter agent looks at the watchlist. This makes the "already in position" check accurate and frees up cash for sizing decisions made later in the same cycle.
5. **Symmetric prediction tracking, asymmetric execution.** The Execute agent acts on UP only in v1 (LONG-only with HOLD-as-no-trade); DOWN and HOLD predictions are recorded as `TradeDecision(executed=False)` so the post-mortem layer can score the prediction even though no money moved. SHORT support is deferred to Phase 2. **[v2-FLAG]** *The original sentence here — "The Predict agent emits UP/DOWN/HOLD with magnitude and confidence for every asset" — encodes the dead LLM-as-forecaster thesis. Under the live method-selector thesis (§0.2), Predict routes among forecasting tools and returns a view that may be "no view." The execution/tracking machinery described here is largely independent of how the view is produced, but the exact prediction output shape is a Phase 3 redesign, not settled by this v1 sentence.*

The v1 system is small — roughly 3,000 lines of Python across about 30 files, two SQLite databases, one cron entry that fires only during US market hours, one LangGraph definition. Same shape as oracle-agents, slightly larger because the domain is richer.

---

## 2. System Context

### 2.1 What sits where

```
                   ┌─────────────────────────────────────┐
                   │        External Services            │
                   │                                     │
                   │  yfinance        Groq API           │
                   │  Finnhub API     Gemini API         │
                   │  CoinGecko API   RSS feeds          │
                   │  Hacker News     Google News RSS    │
                   │                                     │
                   └─────────────────┬───────────────────┘
                                     │
                                     │ HTTPS
                                     │
                   ┌─────────────────▼───────────────────┐
                   │      paper-trader process           │
                   │                                     │
                   │  ┌─────────────────────────────┐    │
                   │  │   LangGraph supervisor      │    │
                   │  │   + 5 domain agents         │    │
                   │  └─────────────┬───────────────┘    │
                   │                │                    │
                   │  ┌─────────────▼───────────────┐    │
                   │  │   Data layer interfaces     │    │
                   │  │   (live or replay impl)     │    │
                   │  └─────────────┬───────────────┘    │
                   │                │                    │
                   │  ┌─────────────▼───────────────┐    │
                   │  │   paper_trader.sqlite       │    │
                   │  │   + checkpointer.sqlite     │    │
                   │  └─────────────────────────────┘    │
                   │                                     │
                   └─────────────────────────────────────┘
                                     ▲
                                     │
                              cron tick
                          every 30 min, market hours only
                          (30 9-16 * * 1-5 America/New_York)
```

The entire system runs as a single Python process triggered on a schedule. There is no web server, no message broker, no container orchestration. A cron job runs `python -m paper_trader.run_cycle` every 30 minutes during US market hours; the process boots, runs one full trading cycle, persists everything, and exits.

### 2.2 Cron timing

The default cron entry is:

```
30 9-16 * * 1-5  cd /opt/paper-trader && python -m paper_trader.run_cycle
```

This fires at 9:30, 10:30, ..., 16:30 Eastern, Monday through Friday. That's 8 cycles per market day, 40 cycles per week. The 9:30 cycle catches the open; the 16:30 cycle catches the close-adjacent activity. Settlement of trades whose horizon elapsed overnight happens on the 9:30 cycle.

**Crypto exception:** if the PM decides to include crypto in v1, crypto-only cycles can run on a separate cron entry (e.g., every 4 hours, 24/7) since crypto markets never close. The architecture supports this — the Filter agent's market-open check is per-asset, not global. **For v1, I assume stocks-only and a single cron entry; crypto support is wired but not scheduled until the PM enables it.**

### 2.3 What this is NOT

Same negative-space list as oracle-agents, plus a few paper-trading-specific exclusions:

- **Not a web service.** No FastAPI, no REST endpoints exposed.
- **Not a streaming system.** No WebSocket subscriptions to price feeds. Polling on a cron schedule is fine for 30-minute decision cycles.
- **Not a message-queue architecture.** No Celery, no Redis. Single-process, single-database, single-thread (mostly — async I/O for Research fan-out only).
- **Not multi-tenant.** One user (you), one simulated portfolio, one set of credentials.
- **Not a real broker integration.** No Alpaca, no IBKR, no Robinhood. The "exchange" is `paper_trades` table in SQLite. Real-broker integration is a separate, future project with its own architecture review.
- **Not multi-strategy.** One strategy (LLM-driven directional prediction with momentum baseline shadow). Strategy ensembling is out of scope.
- **Not options or futures.** Spot stocks and spot crypto only. Derivatives have different P&L mechanics that aren't worth the complexity in v1.

---

## 3. Repository Layout

The new repo is `paper-trader`, separate from `oracle-agents`. Files are tagged `[COPIED]` (verbatim from oracle-agents with import path changes only), `[ADAPTED]` (oracle-agents file modified for the stock/crypto domain), or `[NEW]` (no oracle-agents equivalent).

```
paper-trader/
├── README.md                                           [NEW]
├── pyproject.toml                                      [NEW]
├── .env.example                                        [NEW]
├── .gitignore                                          [NEW]
│
├── docs/
│   ├── PAPER_TRADER_ARCH_001.md                        [NEW]   (this document)
│   ├── PAPER_TRADER_PRD_001.md                         [NEW]   (PM role output)
│   ├── PAPER_TRADER_STRATEGY_001.md                    [NEW]   (Strategist output)
│   ├── PAPER_TRADER_HANDOFF_001.md                     [NEW]   (Build handoff)
│   └── decisions/
│       ├── ADR-PT-001-separate-repo.md                 [NEW]
│       ├── ADR-PT-002-yfinance-as-primary.md           [NEW]
│       ├── ADR-PT-003-long-only-v1.md                  [NEW]
│       ├── ADR-PT-004-bounded-async-research-only.md   [NEW]
│       └── ADR-PT-005-settle-before-scan.md            [NEW]
│
├── src/
│   └── paper_trader/
│       ├── __init__.py                                 [NEW]
│       ├── run_cycle.py                                [ADAPTED]   entry point
│       ├── config.py                                   [ADAPTED]
│       │
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── state.py                                [ADAPTED]   new CycleState shape
│       │   ├── builder.py                              [ADAPTED]   wires the new agents
│       │   └── supervisor.py                           [ADAPTED]   new routing decisions
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py                                 [COPIED]    enforce_writes decorator
│       │   ├── filter.py                               [NEW]       watchlist validator
│       │   ├── research.py                             [NEW]       async news + technicals
│       │   ├── predict.py                              [NEW]       directional + magnitude
│       │   ├── execute.py                              [NEW]       SQLite-only paper trade
│       │   └── postmortem.py                           [NEW]       horizon-based settlement
│       │
│       ├── data/
│       │   ├── __init__.py
│       │   ├── interfaces.py                           [NEW]       4 new Protocol classes
│       │   ├── yfinance_client.py                      [NEW]       price + OHLCV
│       │   ├── finnhub_client.py                       [NEW]       per-ticker news
│       │   ├── coingecko_client.py                     [NEW]       crypto market data
│       │   ├── news.py                                 [COPIED]    RSS + GNews + HN
│       │   └── clock.py                                [ADAPTED]   adds is_market_open()
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── interfaces.py                           [COPIED]    LLMClient protocol
│       │   ├── groq_client.py                          [COPIED]
│       │   ├── gemini_client.py                        [COPIED]
│       │   ├── router.py                               [COPIED]
│       │   └── budget.py                               [COPIED]
│       │
│       ├── persistence/
│       │   ├── __init__.py
│       │   ├── schema.sql                              [NEW]       new domain tables
│       │   ├── db.py                                   [COPIED]    connection helpers
│       │   ├── repositories.py                         [NEW]       per-entity repos
│       │   └── migrations/                             [NEW]       versioned migrations
│       │
│       ├── domain/                                     [NEW]       all new dataclasses
│       │   ├── __init__.py
│       │   ├── asset.py
│       │   ├── price_history.py
│       │   ├── research_bundle.py
│       │   ├── prediction.py
│       │   ├── trade_decision.py
│       │   ├── paper_trade.py
│       │   ├── post_mortem.py
│       │   └── portfolio.py
│       │
│       ├── analytics/
│       │   ├── __init__.py
│       │   ├── kelly.py                                [ADAPTED]   continuous outcomes
│       │   ├── technical_indicators.py                 [NEW]       RSI, SMA, vol trend
│       │   ├── pnl.py                                  [NEW]       LONG P&L computation
│       │   ├── direction_score.py                      [NEW]       hit/miss + magnitude err
│       │   └── sentiment.py                            [COPIED]    VADER wrapper
│       │
│       └── prompts/
│           ├── __init__.py
│           ├── predict_humble.py                       [NEW]       humble prompt template
│           ├── research_summary.py                     [ADAPTED]   stock/crypto framing
│           └── postmortem_bias.py                      [COPIED]    bias tagging prompt
│
├── scripts/
│   ├── run_once.py                                     [ADAPTED]   debug single cycle
│   ├── seed_db.py                                      [NEW]       initialize SQLite
│   ├── show_portfolio.py                               [NEW]       human-readable status
│   ├── show_predictions.py                             [NEW]       prediction history
│   ├── show_settlements.py                             [NEW]       post-mortem digest
│   ├── thesis_backtest.py                              [NEW]       Phase 0.5 validator
│   └── load_watchlist.py                               [NEW]       config validator
│
├── config/
│   ├── watchlist.example.toml                          [NEW]       PM populates
│   └── risk_gates.example.toml                         [NEW]       PM/Strategist populates
│
├── tests/
│   ├── unit/
│   │   ├── test_kelly_continuous.py                    [NEW]
│   │   ├── test_technical_indicators.py                [NEW]
│   │   ├── test_pnl.py                                 [NEW]
│   │   ├── test_direction_score.py                     [NEW]
│   │   ├── test_supervisor_routing.py                  [ADAPTED]
│   │   ├── test_budget.py                              [COPIED]
│   │   ├── test_market_hours.py                        [NEW]
│   │   └── test_repositories.py                        [NEW]
│   ├── integration/
│   │   ├── test_full_cycle_with_fakes.py               [ADAPTED]
│   │   ├── test_recovery_from_checkpoint.py            [COPIED]
│   │   └── test_settle_before_scan.py                  [NEW]
│   └── fixtures/
│       ├── fake_quotes.json                            [NEW]
│       ├── fake_company_news.json                      [NEW]
│       ├── fake_coingecko.json                         [NEW]
│       └── fake_llm_responses.json                     [ADAPTED]
│
└── data/                                               (gitignored)
    ├── paper_trader.sqlite                             app database
    ├── checkpointer.sqlite                             LangGraph in-cycle state
    └── backtest/                                       historical OHLCV cache
```

**On the `[COPIED]` files.** Each one carries a docstring header noting its provenance:

```python
# Provenance: copied verbatim from oracle-agents @ <commit-sha>
# on 2026-04-18. Do not edit independently — when oracle-agents
# updates this file, sync the change here. Eventual extraction
# to worldwise-core is tracked in ADR-PT-001.
```

This makes the duplication legible. When `worldwise-core` extraction happens later, finding the deliberately-shared files is `grep -r "Provenance: copied verbatim from oracle-agents"`.

**On the `[ADAPTED]` files.** These are oracle-agents files modified for the new domain — the supervisor's routing logic is the canonical example. The skeleton (state inspection, deterministic-then-LLM cascade, BudgetExhaustedError fallback) is copied; the specific routing decisions are rewritten. These files also carry a provenance header but with "adapted from" instead of "copied verbatim from."

**On the `[NEW]` files.** These have no oracle-agents equivalent. The domain layer, the data clients (yfinance/Finnhub/CoinGecko), the technical indicators, the directional scoring, and the thesis backtest are all new code. Test coverage matters most here.

---

## 4. The LangGraph State Schema

This is the single most important interface in the system. Every agent reads from it and writes to it; the supervisor inspects it to decide what to do next; the checkpointer serializes it for crash recovery.

### 4.1 The CycleState object

```python
# src/paper_trader/graph/state.py

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from paper_trader.domain import (
    Asset,
    ResearchBundle,
    DirectionalPrediction,
    TradeDecision,
    PaperTrade,
    PostMortem,
    PaperPortfolio,
)


class CycleState(BaseModel):
    """
    The state object that flows through the LangGraph for one trading cycle.

    A 'cycle' = one complete invocation of the graph from supervisor entry to
    final exit. Cycles are independent — state does not persist between cycles
    in this object. Cross-cycle state lives in paper_trader.sqlite and is
    loaded into `portfolio`, `pending_settlements`, and `recent_post_mortems`
    at cycle start by the supervisor.
    """

    # ─── Cycle identity ───────────────────────────────────────────────
    cycle_id: str                              # uuid4, generated at cycle start
    started_at: datetime                       # injected from clock interface, NOT datetime.now()
    cycle_kind: Literal["live", "backtest"] = "live"

    # ─── Inputs (loaded once at cycle start by supervisor) ────────────
    portfolio: PaperPortfolio                  # cash balance, open positions, P&L
    watchlist: list[Asset]                     # config-driven list of assets to consider
    pending_settlements: list[PaperTrade] = Field(default_factory=list)
    recent_post_mortems: list[PostMortem] = Field(default_factory=list)
    calibration_version: str                   # which calibration model the predict agent uses

    # ─── Working memory (populated by agents during cycle) ────────────
    tradeable_assets: list[Asset] = Field(default_factory=list)         # Filter output
    research_bundles: dict[str, ResearchBundle] = Field(default_factory=dict)  # keyed by symbol
    predictions: dict[str, DirectionalPrediction] = Field(default_factory=dict)
    baseline_predictions: dict[str, DirectionalPrediction] = Field(default_factory=dict)
    trade_decisions: dict[str, TradeDecision] = Field(default_factory=dict)
    new_paper_trades: list[PaperTrade] = Field(default_factory=list)
    new_post_mortems: list[PostMortem] = Field(default_factory=list)

    # ─── Routing / control ────────────────────────────────────────────
    next_agent: Literal["filter", "research", "predict", "execute", "postmortem", "end"] | None = None
    completed_agents: list[str] = Field(default_factory=list)
    skip_reasons: dict[str, str] = Field(default_factory=dict)  # symbol → reason

    # ─── Cost tracking ────────────────────────────────────────────────
    llm_calls_made: int = 0
    llm_tokens_consumed: int = 0
    budget_exhausted: bool = False

    # ─── Cycle outcomes (populated at end for cycle_runs row) ─────────
    errors: list[str] = Field(default_factory=list)
    ended_at: datetime | None = None
```

### 4.2 What's different from oracle-agents' state

Three meaningful differences:

| Field | Why it's different |
|---|---|
| `watchlist: list[Asset]` | Oracle-agents *discovered* candidate markets via Manifold's API at cycle start. Paper-trader's watchlist is **config-driven** — loaded from `config/watchlist.toml` and validated at cycle start. The Filter agent doesn't discover; it validates which watchlist entries are tradeable right now. |
| `pending_settlements: list[PaperTrade]` | Oracle-agents queried Manifold for resolved markets each cycle. Paper-trader has to do its own "is it time to settle" check by querying `paper_trades WHERE entry_time + horizon < now AND exited = 0`. The supervisor loads these at cycle start so PostMortem can act on them. |
| `baseline_predictions: dict[str, DirectionalPrediction]` | Oracle-agents tracked baseline as a single field on the Prediction object. Paper-trader's baseline (momentum: "predict whatever direction the price moved yesterday") is a parallel dict because it's computed independently from technical indicators with no LLM call — keeping it parallel makes the post-mortem comparison code symmetric. |

### 4.3 What's the same as oracle-agents

The cycle-identity fields, the routing/control fields, the cost-tracking fields, and the general "inputs / working memory / control / costs" structure are identical. If you've read `ORACLE_AGENTS_ARCH_001` §4, this should feel familiar.

---

## 5. The Supervisor

The supervisor is the central node in the LangGraph — every agent transition goes back to the supervisor, which inspects state and decides where to dispatch next. The skeleton is **copied from oracle-agents**; the specific routing decisions are **rewritten** for paper-trader's domain.

### 5.1 The full cycle, end-to-end

```
       START
         │
         ▼
   ┌──────────┐
   │ Supervisor│ ◀─── cycle entry: load portfolio, watchlist,
   │   start   │       pending_settlements, recent_post_mortems
   └────┬─────┘
        │
        │ (Decision A: deterministic)
        │ if pending_settlements not empty → postmortem
        │ else → filter
        │
        ├──────────────────────────┐
        ▼                          ▼
   ┌──────────┐              ┌──────────┐
   │ PostMortem│              │  Filter  │
   └────┬─────┘              └────┬─────┘
        │                          │
        ▼                          │
   ┌──────────┐                    │
   │ Supervisor│                    │
   └────┬─────┘                    │
        │                          │
        │ (Decision B: LLM-driven) │
        │ given settlements,       │
        │ proceed normally or      │
        │ adjust prompt for        │
        │ rest of cycle?           │
        │                          │
        └──────────────► filter ◀──┘
                          │
                          ▼
                     ┌──────────┐
                     │ Supervisor│
                     └────┬─────┘
                          │
                          │ (Decision C: deterministic)
                          │ if tradeable_assets empty → end
                          │ else → research
                          │
                          ▼
                     ┌──────────┐
                     │ Research │
                     └────┬─────┘
                          │
                          ▼
                     ┌──────────┐
                     │ Supervisor│
                     └────┬─────┘
                          │
                          │ (Decision D: deterministic)
                          │ if budget_exhausted → end
                          │ else → predict
                          │
                          ▼
                     ┌──────────┐
                     │ Predict  │
                     └────┬─────┘
                          │
                          ▼
                     ┌──────────┐
                     │ Supervisor│
                     └────┬─────┘
                          │
                          │ (Decision E: deterministic)
                          │ if no UP predictions → end
                          │ else → execute
                          │
                          ▼
                     ┌──────────┐
                     │ Execute  │
                     └────┬─────┘
                          │
                          ▼
                         END
```

### 5.2 The five routing decisions

Four deterministic, one LLM-driven. Same shape as oracle-agents — most routing is `if/elif`, with LLM judgment reserved for the place it actually adds value.

**Decision A — deterministic.** At cycle start, settle stale trades first, otherwise scan watchlist:

```python
def decide_after_start(state: CycleState) -> str:
    if state.pending_settlements:
        return "postmortem"
    return "filter"
```

This is the **settle-before-scan** principle. Cash flows back to the portfolio before any sizing decisions are made. The "already in position" check used by Filter and Execute is accurate. ADR-PT-005 documents the rationale.

**Decision B — LLM-driven.** After PostMortem completes, the supervisor asks Gemini whether the settlements suggest the rest of the cycle should run normally or with an adjusted predict prompt:

```python
def decide_after_postmortem(state: CycleState) -> str:
    if state.budget_exhausted:
        return "filter"  # fallback: deterministic, proceed normally

    # LLM call: given new_post_mortems, should we adjust predict prompt?
    # Gemini returns one of:
    #   - "normal": proceed to filter, use default predict prompt
    #   - "conservative": proceed to filter, use predict prompt with reduced confidence cap
    #   - "skip_cycle": settlements suggest the model is mis-calibrated, end cycle
    decision = llm_router.call(
        purpose="post_settlement_routing",
        prompt=POST_SETTLEMENT_PROMPT,
        context=state.new_post_mortems,
    )
    if decision == "skip_cycle":
        return "end"
    state.predict_prompt_mode = decision  # "normal" or "conservative"
    return "filter"
```

This is the only LLM-driven routing in the system. **Why this one?** Because the question "does today's settlement data suggest something is off with the model's calibration?" is exactly the kind of judgment call that benefits from LLM reasoning over a small structured input. A deterministic rule like "if accuracy < 50% over last 10 settlements, go conservative" would work, but it's brittle — the LLM can spot patterns like "we're consistently overestimating magnitude on tech stocks but fine on financials" that a simple threshold can't.

When the budget is exhausted, this collapses to "treat as normal cycle, proceed."

**Decisions C, D, E — deterministic.** Standard if/elif:

```python
def decide_after_filter(state: CycleState) -> str:
    return "research" if state.tradeable_assets else "end"

def decide_after_research(state: CycleState) -> str:
    return "end" if state.budget_exhausted else "predict"

def decide_after_predict(state: CycleState) -> str:
    has_up = any(p.direction == "UP" for p in state.predictions.values())
    return "execute" if has_up else "end"
    # [v2-FLAG] "p.direction == 'UP'" assumes the dead forecaster output shape.
    # Under the method-selector thesis (§0.2) the gate becomes "any actionable
    # view that maps to a tradeable signal?" — Phase 3 redefines this once the
    # method-selector's output dataclass is designed.
```

### 5.3 BudgetExhaustedError handling

Same pattern as oracle-agents. The LLM router raises `BudgetExhaustedError` when a call would exceed the per-cycle token cap. The supervisor catches this in Decision B and falls back to deterministic routing. Individual agents (Research, Predict) handle the same error per-asset — if Research runs out of budget mid-fan-out, the remaining assets get logged as `skip_reasons[symbol] = "budget exhausted"` and Predict only sees the assets that were successfully researched.

---

## 6. Agent Contracts

Each agent declares its readable and writable fields on the `CycleState`. The `enforce_writes` decorator (copied verbatim from oracle-agents `agents/base.py`) wraps each agent's `run()` method and raises `WriteAuthorizationError` if the agent modifies a field outside its declared write set.

### 6.1 The contract table

| Agent | Reads | Writes | LLM calls per asset |
|---|---|---|---|
| **Filter** | `watchlist`, `portfolio` | `tradeable_assets`, `skip_reasons` | 0 |
| **Research** | `tradeable_assets` | `research_bundles`, `skip_reasons`, `llm_calls_made`, `llm_tokens_consumed` | 1 Groq + 1 Gemini |
| **Predict** | `research_bundles` | `predictions`, `baseline_predictions`, `llm_calls_made`, `llm_tokens_consumed` | 1 Gemini |
| **Execute** | `predictions`, `portfolio` | `trade_decisions`, `new_paper_trades` | 0 |
| **PostMortem** | `pending_settlements` | `new_post_mortems`, `portfolio` (cash + open_positions update on close) | ~0.25 Groq (one bias-tag call per ~4 settlements, batched) |

### 6.2 Notes on each agent

**Filter.** Validates each watchlist entry against four criteria: market is currently open for this asset type, asset has sufficient daily volume, asset is not already in an open paper position, price data is fresh (last quote less than 60 minutes old). Pure rule-based. Writes the survivors to `tradeable_assets` and the rejects to `skip_reasons`.

**Research.** The only async agent. Fans out across `tradeable_assets` to fetch news (Finnhub for stocks, RSS+HN+GoogleNews for both stocks and crypto), recent OHLCV (yfinance for both stocks and crypto, CoinGecko as fallback for crypto), and computes technical indicators locally (RSI, SMA crossover, volume trend) using pure-python numpy code with no external calls. Then one Groq call per asset for keyword extraction from news, and one Gemini call per asset for narrative summary. The async fan-out is bounded by `asyncio.Semaphore(2)` for yfinance and `asyncio.Semaphore(4)` for Finnhub/CoinGecko. Wrapped in `asyncio.run()` at the agent boundary so the rest of the graph stays sync.

**Predict. [v2-REWRITTEN — see §0.2]** *The v1 text below is retained struck-through-in-spirit for provenance; the live design replaces it.*

**Live design (method-selector, UNVALIDATED):** For each asset with a research bundle, the Predict agent routes among its *own* forecasting tools (e.g. momentum, mean-reversion, ARIMA, gradient-boosted models). An LLM call selects which method fits the situation *only where no skill rule yet covers that case*; where a rule covers it, the rule routes and no LLM call is made. The selected method produces the view. If the agent cannot route confidently, it returns an honest **"no view + explanation"** rather than forcing a forecast — no-view is a valid terminal output, not a failure to drill through. Transient infrastructure failures (timeout, rate-limit, 5xx) get backoff+jitter+capped retries; routing-uncertainty is *not* retried. The agent returns its view to its invoker and never invokes a sibling agent. Its routing rules accrete into its skill file through Steward's governed slow loop, and it carries a timestamped `UNVALIDATED` thesis flag. **The exact output dataclass shape (what replaces `DirectionalPrediction`'s UP/DOWN/HOLD+magnitude+confidence) is a Phase 3 design task** — it must express "which method was chosen, what it predicted, and confidence/no-view," which is not the same shape as the v1 forecaster output.

> **v1 text (DEAD THESIS — do not build):** ~~For each asset with a research bundle, one Gemini call using the humble prompt template (`prompts/predict_humble.py`). Returns `DirectionalPrediction` with direction (UP/DOWN/HOLD), confidence (0-1), magnitude_pct (expected % move), time_horizon_hours, and reasoning.~~ The baseline prediction (momentum: "if yesterday's close was higher than two days ago's close, predict UP, else DOWN") survives as a comparison shadow and is computed with no LLM call.

**Execute.** For each asset where `predictions[symbol].direction == "UP"`, run the deterministic risk gates (max position per asset, max total exposure, max daily simulated loss, max correlated positions). Compute position size using fractional Kelly adapted for continuous outcomes (`analytics/kelly.py`). If approved, write a `PaperTrade` row to `new_paper_trades` and a `TradeDecision(executed=True)` to `trade_decisions`. If rejected, write only the `TradeDecision(executed=False, risk_reason=...)`. For DOWN and HOLD predictions, write `TradeDecision(executed=False, risk_reason="long_only_v1")` so the post-mortem can still score the prediction.

**PostMortem.** For each `PaperTrade` in `pending_settlements`: fetch the current price via yfinance (or CoinGecko for crypto), compute actual direction, actual magnitude, direction accuracy (hit/miss), simulated P&L (LONG only in v1: `quantity * (exit_price - entry_price)`), baseline P&L (what the momentum baseline would have earned), and magnitude error. Batch 4 settlements at a time into a single Groq call for bias tagging. Write `PostMortem` rows. Update `portfolio.cash_balance` to reflect the closed trades.

---

## 7. The Data Layer (the seam pattern)

Every external dependency is hidden behind a `Protocol` defined in `data/interfaces.py`. Live implementations are injected at boot in `run_cycle.py`. Fakes are used in tests. Phase 2 backtest implementations slot in next to the live ones.

### 7.1 The four new protocols

```python
# src/paper_trader/data/interfaces.py

from typing import Protocol
from datetime import datetime
from paper_trader.domain import Asset, OHLCVBar, NewsItem


class MarketDataProvider(Protocol):
    """Current quote and recent OHLCV for stocks AND crypto. yfinance covers both."""

    async def get_current_quote(self, symbol: str) -> float: ...

    async def get_ohlcv(
        self,
        symbol: str,
        period_days: int,
    ) -> list[OHLCVBar]: ...

    async def get_asset_metadata(self, symbol: str) -> Asset: ...


class CompanyNewsProvider(Protocol):
    """Per-ticker news. Finnhub for stocks. CoinGecko has news endpoints for crypto."""

    async def get_company_news(
        self,
        symbol: str,
        since: datetime,
    ) -> list[NewsItem]: ...


class CryptoDataProvider(Protocol):
    """Crypto-specific market data: market cap, volume, supply. CoinGecko."""

    async def get_market_data(self, symbol: str) -> dict: ...

    async def get_crypto_news(
        self,
        symbol: str,
        since: datetime,
    ) -> list[NewsItem]: ...


class Clock(Protocol):
    """Injectable clock. Live = wall clock. Frozen = test fixture."""

    def now(self) -> datetime: ...

    def is_market_open(self, asset_type: str) -> bool:
        """For 'stock', checks NYSE/NASDAQ hours. For 'crypto', always True."""
```

### 7.2 Live implementations

| Protocol | Live class | Notes |
|---|---|---|
| `MarketDataProvider` | `YFinanceClient` | Wraps the `yfinance` library. Adds retry-with-backoff (3 tries) and a 5-second timeout. Caches quotes in-memory for 60 seconds to avoid hammering Yahoo if multiple agents ask for the same symbol in one cycle. |
| `CompanyNewsProvider` | `FinnhubClient` | REST client over `requests` with Finnhub free-tier key. Respects 60 calls/min. Retry-with-backoff, 5-second timeout. |
| `CryptoDataProvider` | `CoinGeckoClient` | REST client, no auth needed. Respects 10-30 calls/min (use 10 to be safe). Retry-with-backoff. |
| `Clock` | `LiveClock` | Wraps `datetime.now(UTC)`. `is_market_open("stock")` checks NYSE hours via `pandas_market_calendars` or a hardcoded simple check (9:30am-4:00pm Eastern weekdays); `is_market_open("crypto")` returns True. |

### 7.3 Bounded concurrency in Research

The Research agent fans out across `tradeable_assets`. Without bounds, 20 simultaneous yfinance calls would trip Yahoo's rate limiting and 20 simultaneous Finnhub calls would burn through the 60/min quota in one cycle. The bounds:

```python
# src/paper_trader/agents/research.py

YFINANCE_SEMAPHORE = asyncio.Semaphore(2)   # ~2 req/sec to Yahoo
FINNHUB_SEMAPHORE = asyncio.Semaphore(4)    # 4 concurrent, well under 60/min
COINGECKO_SEMAPHORE = asyncio.Semaphore(4)  # 4 concurrent, conservative

async def research_one_asset(asset: Asset, ...) -> ResearchBundle:
    async with YFINANCE_SEMAPHORE:
        ohlcv = await market_data.get_ohlcv(asset.symbol, period_days=30)
    async with FINNHUB_SEMAPHORE:
        news = await company_news.get_company_news(asset.symbol, since=...)
    # ... compute technicals, sentiment, LLM calls (also semaphored separately)
```

For a 20-asset watchlist, this gives a Research pass in roughly 8–12 seconds instead of 30+. The complexity is contained to one file. ADR-PT-004 documents the decision to keep async confined to Research.

### 7.4 Fakes for testing

Each protocol has a fake implementation in `tests/fixtures/` that reads from JSON files. Tests construct `CycleState` with fakes injected and assert on the resulting state mutations. No network calls in tests. Same pattern as oracle-agents.

---

## 8. Persistence — SQLite Schema

Two SQLite databases, never co-mingled.

### 8.1 Application database (`paper_trader.sqlite`)

```sql
-- Watchlist snapshot at cycle start (for audit / replay)
CREATE TABLE assets (
    symbol TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('stock', 'crypto')),
    name TEXT NOT NULL,
    exchange TEXT NOT NULL,
    last_seen_price REAL,
    last_updated TIMESTAMP NOT NULL
);

-- Every prediction the Predict agent generated, including the baseline shadow
-- [v2-FLAG] This schema (direction IN UP/DOWN/HOLD, magnitude_pct, confidence)
-- encodes the dead forecaster thesis. Phase 3 redesigns it to record the
-- method-selector's output: which forecasting method was chosen, its prediction,
-- confidence-or-no-view, plus the skill_version_id pin Steward replay requires.
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_price REAL NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('UP', 'DOWN', 'HOLD')),
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    magnitude_pct REAL NOT NULL,
    time_horizon_hours INTEGER NOT NULL,
    reasoning TEXT NOT NULL,
    calibration_version TEXT NOT NULL,
    is_baseline BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (symbol) REFERENCES assets(symbol)
);
CREATE INDEX idx_predictions_symbol_created ON predictions(symbol, created_at);

-- Every Execute decision, executed or skipped — symmetric for post-mortem
CREATE TABLE trade_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    prediction_id INTEGER NOT NULL,
    executed BOOLEAN NOT NULL,
    risk_reason TEXT,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

-- Only when Execute approved a trade
CREATE TABLE paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    prediction_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('LONG', 'SHORT')),  -- v1: LONG only
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    notional_value REAL NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    expected_exit_time TIMESTAMP NOT NULL,
    exited BOOLEAN NOT NULL DEFAULT 0,
    exit_price REAL,
    exit_time TIMESTAMP,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id),
    FOREIGN KEY (symbol) REFERENCES assets(symbol)
);
CREATE INDEX idx_paper_trades_open ON paper_trades(exited, expected_exit_time);

-- Settlement results
CREATE TABLE post_mortems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id INTEGER NOT NULL,
    direction_correct BOOLEAN NOT NULL,
    predicted_magnitude_pct REAL NOT NULL,
    actual_magnitude_pct REAL NOT NULL,
    magnitude_error REAL NOT NULL,
    simulated_pnl REAL NOT NULL,
    baseline_pnl REAL NOT NULL,
    bias_flags TEXT,  -- JSON array
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (paper_trade_id) REFERENCES paper_trades(id)
);

-- One row per cycle: bookkeeping for ops + cost analysis
CREATE TABLE cycle_runs (
    cycle_id TEXT PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    cycle_kind TEXT NOT NULL CHECK(cycle_kind IN ('live', 'backtest')),
    llm_calls_made INTEGER NOT NULL DEFAULT 0,
    llm_tokens_consumed INTEGER NOT NULL DEFAULT 0,
    settlements_processed INTEGER NOT NULL DEFAULT 0,
    new_predictions INTEGER NOT NULL DEFAULT 0,
    new_trades INTEGER NOT NULL DEFAULT 0,
    errors TEXT  -- JSON array
);

-- Cache fetched news to avoid re-fetching in adjacent cycles
CREATE TABLE news_cache (
    url TEXT PRIMARY KEY,
    symbol TEXT,  -- NULL for general news, set for company-specific
    title TEXT NOT NULL,
    content TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP NOT NULL,
    sentiment_score REAL
);
CREATE INDEX idx_news_cache_symbol ON news_cache(symbol, fetched_at);

-- Calibration model versions (placeholder for Phase 2)
CREATE TABLE calibration_versions (
    version_id TEXT PRIMARY KEY,
    method TEXT NOT NULL,  -- 'identity' in v1; 'platt'/'isotonic' in Phase 2
    fitted_at TIMESTAMP NOT NULL,
    parameters TEXT,  -- JSON
    notes TEXT
);

-- Portfolio snapshot — one row per cycle, append-only
CREATE TABLE portfolio_snapshots (
    cycle_id TEXT PRIMARY KEY,
    cash_balance REAL NOT NULL,
    open_positions_value REAL NOT NULL,
    total_value REAL NOT NULL,
    daily_simulated_pnl REAL NOT NULL,
    total_simulated_pnl REAL NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    FOREIGN KEY (cycle_id) REFERENCES cycle_runs(cycle_id)
);
```

### 8.2 Checkpointer database (`checkpointer.sqlite`)

Managed entirely by LangGraph's `SqliteSaver`. Schema is whatever LangGraph creates — we don't touch it. Wired in `run_cycle.py`:

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string("data/checkpointer.sqlite")
graph = build_graph(checkpointer=checkpointer, ...)
```

The two databases use **separate connections** opened in separate code paths. They never share a `sqlite3.Connection` object. This was a specific lesson from oracle-agents — co-mingling them caused subtle locking issues in early development.

---

## 9. Configuration

### 9.1 Environment variables (`.env`)

```
# LLM providers (same as oracle-agents)
GROQ_API_KEY=...
GEMINI_API_KEY=...

# Market data
FINNHUB_API_KEY=...
# yfinance and CoinGecko need no auth

# Paths
PAPER_TRADER_DB_PATH=./data/paper_trader.sqlite
CHECKPOINTER_DB_PATH=./data/checkpointer.sqlite

# Cycle behavior
CYCLE_TIME_HORIZON_HOURS=24
CYCLE_TOKEN_BUDGET=15000
CYCLE_LOG_LEVEL=INFO
```

### 9.2 Watchlist (`config/watchlist.toml`)

```toml
# Populated by PM, validated by scripts/load_watchlist.py at boot

[[stocks]]
symbol = "AAPL"
name = "Apple Inc."
exchange = "NASDAQ"

[[stocks]]
symbol = "MSFT"
name = "Microsoft Corporation"
exchange = "NASDAQ"

# ... PM decides the full list

[[crypto]]
symbol = "BTC-USD"
name = "Bitcoin"
exchange = "crypto"

# ... if PM enables crypto in v1
```

### 9.3 Risk gates (`config/risk_gates.toml`)

```toml
# Populated by PM/Strategist, loaded by Execute agent

[position_sizing]
max_position_pct_of_portfolio = 0.05         # max 5% of portfolio in one position
kelly_fraction = 0.25                         # fractional Kelly (conservative)
min_position_notional = 100.0                 # don't bother with sub-$100 positions

[exposure_limits]
max_total_exposure_pct = 0.60                 # max 60% of portfolio in open positions
max_correlated_positions = 3                  # max 3 positions in same sector

[loss_limits]
max_daily_simulated_loss_pct = 0.05           # halt new trades if down >5% on day
max_open_positions = 10                       # hard cap on simultaneous positions

[execution]
require_min_confidence = 0.55                 # don't execute below this confidence
require_min_magnitude_pct = 0.5               # don't execute below this expected move
```

The architecture loads these from TOML at boot. The actual values are PM/Strategist territory; the architect's job is to ensure they're configurable, not pick them.

---

## 10. Error Handling

Three categories, same as oracle-agents:

**Retryable network errors** — yfinance 503, Finnhub timeout, Gemini rate limit. Handled inside the data layer with exponential backoff (max 3 tries, base delay 1s). After exhaustion, the data layer returns an empty result and the calling agent logs to `skip_reasons[symbol]` and continues with the next asset. The cycle does not abort.

**Cycle-fatal errors** — corrupt SQLite, invalid config, missing API key. The cycle aborts, the process exits non-zero, cron sees the failure, and an alert can be wired up later. These errors should be rare and indicate genuine misconfiguration.

**Per-asset errors** — one ticker's data is malformed, one Predict call returns invalid JSON, one risk gate calculation throws. Logged to `state.errors`, that asset is skipped this cycle, other assets continue. The cycle completes successfully and the error appears in the `cycle_runs.errors` JSON column for later debugging.

**The LangGraph checkpointer covers crash recovery.** If the process dies mid-cycle (OOM, OS-level kill, infrastructure failure), the next cron tick reloads the cycle from the checkpointer and resumes. Idempotency is the agents' responsibility — Execute, for instance, must not double-write a `paper_trade` if it ran twice. The pattern (check `new_paper_trades` for an entry with the same `prediction_id` before inserting) is copied from oracle-agents.

---

## 11. Cost Model

For a 20-asset stock-only watchlist running 8 cycles per market day (9:30, 10:30, ..., 16:30 Eastern, weekdays):

**Per cycle:**

| Agent | Groq calls | Gemini calls |
|---|---|---|
| Filter | 0 | 0 |
| Research | 20 (keyword extraction) | 20 (narrative summary) |
| Predict | 0 | 20 (humble prompt prediction) |
| Execute | 0 | 0 |
| PostMortem | ~5 (bias tagging, batched) | 0 |
| Supervisor | 0 | 1 (post-settlement routing) |
| **Per cycle total** | **~25** | **~41** |

**Per day** (8 cycles): ~200 Groq, ~328 Gemini.
**Per week** (40 cycles): ~1,000 Groq, ~1,640 Gemini.

**Free tier headroom:**

- Groq Llama 3.3 70B: 14,400 req/day. We use ~200/day. Headroom: 72×.
- Gemini 2.5 Flash: free tier is generous (exact limits change; was ~1,500 req/day at last check). We use ~328/day. Headroom: ~5×.

The Gemini headroom is what would bind first if the watchlist grows. At a 50-asset watchlist we'd be at ~820 Gemini/day, still within free tier but tighter. **The token budget per cycle (`CYCLE_TOKEN_BUDGET=15000`) is the hard cap that prevents any single cycle from blowing through the daily quota.**

---

## 12. Build Sequence Overview

The actual file-by-file build sequence is the Build Handoff role's output (role 4). High-level shape:

**Phase 0 — scaffolding (1 task)**
- T01: Create repo skeleton, copy infrastructure files from oracle-agents, set up pyproject.toml, write provenance headers, run `pytest --collect-only` to confirm imports work

**Phase 0.5 — thesis validation backtest (3 tasks)**
- T02: Historical OHLCV fetch script (yfinance, 2 years, 50 stocks, cache to `data/backtest/`)
- T03: Momentum baseline implementation + evaluation harness
- T04: Run backtest, ask Gemini to predict next-day direction across the dataset, compute hit rate vs baseline. **GO/NO-GO gate: if LLM doesn't beat baseline, stop before Phase 1.**

**Phase 1 — full system build (12 tasks)**
- T05: Domain models (all of `src/paper_trader/domain/`)
- T06: Persistence layer (schema, db connections, repositories)
- T07: Data interface protocols + fakes
- T08: yfinance + Finnhub + CoinGecko live clients with retry/timeout
- T09: News + clock + market hours
- T10: Filter agent
- T11: Research agent (with bounded async)
- T12: Predict agent (humble prompt template)
- T13: Execute agent (Kelly + risk gates)
- T14: PostMortem agent (settlement + bias tagging)
- T15: Supervisor + graph builder + run_cycle.py entry point
- T16: Full-cycle integration test with all fakes injected

Each task has its own gate report, branch, and human review before merge — same discipline as oracle-agents.

---

## 13. What's Out of Scope for v1

Explicitly:

- Real broker integration (Alpaca, IBKR, Robinhood). Future project.
- Options, futures, derivatives. Spot only.
- Intraday tick data or sub-minute pricing.
- Calibration refit (Platt, isotonic). v1 uses identity calibration; Phase 2 task.
- Multi-strategy ensembling. One LLM strategy + momentum baseline.
- SHORT positions. Phase 2.
- Portfolio optimization beyond per-asset Kelly + simple correlation cap.
- Sector/industry classification beyond what Finnhub returns.
- Dashboard UI. CLI scripts only (`scripts/show_*.py`).
- Tax lot tracking. P&L is FIFO.
- Slippage modeling. Entry and exit prices are whatever yfinance returns at the moment.
- Trading fees / commission modeling. Zero in v1.
- Multi-currency. Everything in simulated USD.
- Email/SMS alerts. Cron writes to logs; that's it.

---

## 14. Trade-offs and Alternatives Considered

Five short ADR-style notes. Each becomes a file in `docs/decisions/`.

### ADR-PT-001: Separate repo, deferred extraction

**Considered:** (a) sibling subpackage inside oracle-agents; (b) renamed `worldwise-sandbox` repo; (c) separate repo with copy-then-extract; (d) dependency on a published `worldwise-core` package built from oracle-agents.

**Picked:** (c). Separate repo `paper-trader`, infrastructure files copied verbatim with provenance headers, extraction to `worldwise-core` deferred until both sandboxes are alive.

**Why:** Oracle-agents is a live system with open positions. Coupling paper-trader development to it via a shared repo means every commit risks regressing the live cycle. Premature extraction (option d) would require designing a generic interface from a sample size of one. Copy-then-extract is the rule of three applied honestly — wait until paper-trader is alive, then extract from a sample size of two.

**Cost accepted:** ~600 lines of duplicated Python that you maintain in two places for a few months. When `worldwise-core` extraction happens, `grep -r "Provenance: copied verbatim from oracle-agents"` finds every duplication site.

### ADR-PT-002: yfinance as primary data source despite fragility

**Considered:** (a) yfinance only; (b) Alpha Vantage as primary; (c) Finnhub free tier as primary; (d) IEX Cloud free tier.

**Picked:** (a). yfinance for prices and OHLCV, Finnhub only for company news, CoinGecko for crypto-specific data.

**Why:** yfinance has zero auth, zero rate limit (in practice, ~2 req/sec), and covers stocks + crypto + global markets in one library. Alpha Vantage's free tier is now 25 req/day — unusable. Finnhub free tier is 60 req/min but its quote endpoint is delayed 15 minutes for free users; for paper trading the delay is acceptable but Finnhub doesn't cover all global tickers. IEX Cloud retired its free tier in 2024.

**Cost accepted:** yfinance is unofficial (it scrapes Yahoo Finance) and can break with no warning if Yahoo changes their internals. Mitigation: retry-with-backoff in the data layer; `skip_reasons` logging when an asset's data fetch fails; CoinGecko as fallback for crypto. The system degrades gracefully — a yfinance outage means we skip cycles, not that we corrupt state.

### ADR-PT-003: LONG + HOLD-as-no-trade in v1, defer SHORT to Phase 2

**[v2 STATUS: SUPERSEDED AT THE THESIS LEVEL.]** *This ADR assumes the Predict agent emits UP/DOWN/HOLD by forecasting — the thesis T02–T04 killed (§0.1). The LONG-only / HOLD-as-no-trade **execution** decision may still hold, but it must be re-derived against the method-selector's actual output shape (§0.2, §6.2), not inherited from "the LLM predicts a direction." Do not treat this ADR as live until Phase 3 redefines what Predict outputs. Retained verbatim below for provenance.*

**Considered:** (a) LONG only, ignore DOWN predictions entirely; (b) LONG + HOLD-as-no-trade, record DOWN predictions but don't execute them; (c) full LONG + SHORT.

**Picked:** (b). Predict agent emits UP/DOWN/HOLD; Execute acts on UP only; DOWN and HOLD become `TradeDecision(executed=False)` records.

**Why:** Option (a) discards half the signal — we'd lose the ability to score the LLM's DOWN calls in post-mortems. Option (c) adds complexity to the predict prompt (must reason symmetrically about upside and downside catalysts), the position sizing math (bounded vs unbounded loss), and the post-mortem attribution (LONG and SHORT P&L on the same asset). Option (b) preserves full prediction calibration data while keeping execution simple. Phase 2 turns SHORT on once we have evidence the LLM's DOWN calls are calibrated.

**Cost accepted:** Half our predictions don't move money in v1. The kill condition (50 settled trades) takes longer to hit because we only settle the LONG executions, not the no-trade decisions. Worth it — we can validate the prediction quality from the decision records even without trading them.

### ADR-PT-004: Bounded async only in Research, sync everywhere else

**Considered:** (a) fully sync graph; (b) sync graph with async I/O fan-out only in Research; (c) fully async graph with `AsyncSqliteSaver`.

**Picked:** (b). Sync graph and `SqliteSaver` checkpointer; async confined to Research's I/O fan-out, wrapped in `asyncio.run()` at the agent boundary.

**Why:** Option (a) would make a 20-asset Research pass take 30+ seconds. Option (c) requires the whole graph to be async, all agents to be async, and `AsyncSqliteSaver` which has fewer footguns documented. Option (b) is the smallest change that gives us the speedup where it matters (parallel API calls in Research) without infecting the rest of the codebase with async.

**Cost accepted:** A small impedance mismatch — Research's `run()` method internally calls `asyncio.run(...)` to manage the fan-out. Slightly less elegant than fully-async, but the boundary is contained to one file.

### ADR-PT-005: Settle before scan

**Considered:** (a) scan watchlist first, settle stale trades at end of cycle; (b) settle stale trades first, then scan watchlist; (c) settle on a separate cron entry, scan on the main cron.

**Picked:** (b). At cycle start, supervisor checks `pending_settlements`; if non-empty, dispatch to PostMortem before Filter.

**Why:** Settling first ensures cash flows back to the portfolio before sizing decisions are made later in the same cycle. The "already in position" check used by Filter is accurate (a position whose horizon just elapsed gets closed before Filter sees it). The post-mortem feedback is freshly available if Phase 2 wires it into the Predict prompt. Option (a) creates the awkward case where we open a new AAPL position while yesterday's AAPL position is still "open" in the database. Option (c) splits the system into two cron entries unnecessarily — one process can do both jobs in sequence.

**Cost accepted:** None significant. The supervisor's first-decision branch is one extra `if/elif`. The integration test (`test_settle_before_scan.py`) is one new test.

---

## 15. Open Questions for the PM

The architecture is locked. These belong to the next role (Product Manager):

1. **Stocks only, crypto only, or both in v1?** Architecture supports both via the per-asset `is_market_open()` check; PM decides the watchlist composition.
2. **Watchlist size and exact tickers.** Architecture sized for 10–20 assets (could go to 50 with cost margin). PM picks the actual list.
3. **Time horizon.** Architecture supports configurable horizon via `CYCLE_TIME_HORIZON_HOURS`. Default is 24h; PM may want shorter (4h, faster feedback) or longer (1 week, less noise).
4. **Risk gate parameters.** Architecture loads from `config/risk_gates.toml`. PM and Strategist together set the actual values (max position %, Kelly fraction, daily loss limit, etc.).
5. **Minimum confidence threshold for execution.** Architecture supports `require_min_confidence` in risk gates. PM decides whether to set it (and at what level) — too low and we trade noise, too high and we never trade.
6. **Cycle frequency during market hours.** Architecture defaults to every 30 minutes (8 cycles/day). PM may prefer hourly (less overhead, slower reaction) or every 15 minutes (more reaction, more cost).
7. **Phase 0.5 thesis backtest scope.** Architecture supports running the backtest via `scripts/thesis_backtest.py`. PM decides: how many stocks, what time period, what beat-baseline threshold counts as "passing"?

---

## 16. Next Steps

1. **Operator review of this document.** Push back on anything that feels wrong, especially the ADRs (PT-001 through PT-005) which lock in decisions that are expensive to reverse later.
2. **Hand off to Product Manager.** PM produces `PAPER_TRADER_PRD_001.md` covering MoSCoW scope, user stories per agent, success metrics with thresholds, watchlist composition, and the open questions in §15.
3. **Strategist phase.** Produces roadmap, kill conditions, decision gates, and the carryover plan back to World Agents.
4. **Build Handoff phase.** Produces the file-by-file, task-by-task build sequence (~16 tasks) for Claude Code to execute with human gates.
5. **Phase 0.5 thesis backtest.** Before any Phase 1 build work, run the historical backtest. If the LLM can't beat momentum baseline on 2 years of historical data across 50 stocks, **stop**. The cost discipline that worked for oracle-agents — kill conditions enforced before sunk cost grows — applies here too.

---

**End of `PAPER_TRADER_ARCH_001`.**
