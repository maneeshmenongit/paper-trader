# Live-Operation Phase — Completion Report (T1–T6)

**Branch:** `postv1-t1-live-data-clients` (off merged `main`; NOT merged — for review)
**Scope:** Take the momentum skeleton LIVE on real market data with a self-hosted
open-source LLM and accumulate REAL governance records. Authority:
`STEWARD_PAPER_TRADER_LIVE_OPERATION_001`. NOT the LLM-selector thesis (Predict
stays momentum-only; the thesis stays UNVALIDATED).
**Status:** All six tasks (T1–T6) complete. **The definition of done is MET** — a
live, governed, open-source-LLM momentum paper-trader ran on real prices and
produced real records (see `T6_LIVE_RUN_REPORT.md`).

---

## What was built, task by task

- **T1 — Live data clients.** `data/live/`: `YFinanceMarketData`,
  `FinnhubCompanyNews`, `CoinGeckoCryptoData`, each implementing an existing
  `data/interfaces` protocol verbatim; plus the `retry_with_backoff` seam. Sync
  SDKs wrapped in `to_thread`; concurrency politeness stays owned by the Research
  agent's semaphores. Agents unchanged.
- **T2 — Open-source LLM.** `OllamaClient` + `OpenRouterClient` (raw httpx, no new
  SDK) behind a NEW `ConfigurableLLMRouter` that sits ALONGSIDE the frozen
  oracle-provenance router: per-purpose provider selection + ordered fallback
  (Ollama primary → Groq/Gemini). Predict not routed.
- **T3 — Live config + watchlist.** `live/`: `LiveConfig` (env, secrets masked),
  the fakes↔live provider swap, `LiveTradingClient` (real R2 liquidity derivation),
  a TOML watchlist. Secrets never enter the trace.
- **T4 — Settlement + baseline scoring.** `settlement/engine.py`: close trades at
  horizon, score hit/miss + the momentum baseline shadow via `SettlementContext`.
  Execute's `expected_exit_time` fixed to `entry + horizon`. App-db only.
- **T5 — Scheduled run harness.** `harness/`: `build_governed_cycle` (the one
  production graph-assembly site, emitter + observer on), `ScheduledRunner`
  (settle→cycle→persist→observe), per-cycle replay markdown + findings,
  `scripts/run_live.py` CLI, `data/offline.py`.
- **T6 — First live run.** Ran live on real yfinance + real Ollama; 3 cycles, 12
  real trades, replay clean, pins VERIFIED. Run report:
  `T6_LIVE_RUN_REPORT.md`.

## Aggregate tests

**444 passed, 0 failed** (was 357 at the end of Wave 6; **+87**). ruff clean.
Every changed file mypy-clean (pre-existing backtest/frozen-client mypy debt in
untouched files remains, as on `main`). DC-1 boundary green (steward never imports
paper_trader). Emission/observer neutrality green after every agent-touching change.

## Real bugs the live run surfaced (fixed + regression-tested)

The live run was the first exposure to real data, and it earned its keep — five
integration bugs the fakes/fixtures had masked (tz-naive timestamps, daily-bar
staleness vs R4, test-tree import, 100.0 entry-price fallback, dropped
post-mortem + baseline persistence). Each is fixed with a regression test. Details
in `T6_LIVE_RUN_REPORT.md`.

## Discipline held throughout

- **DC-1:** all live code lives in `paper_trader/`; `steward/` untouched.
- **Frozen files** (oracle-provenance `llm/*.py`, `persistence/db.py`, the router,
  Store A/B DDL) never edited in place — new capability added alongside.
- **Governance membrane intact:** observer is the only Store B writer (terminal
  node); settlement/observability/replay are read-only or app-db-only; no fork
  reachable outside the gate. Verified no secret entered the frozen trace on a
  real run.
- **Behavior-neutral where required; recorded corrections where not.** Agent
  changes (Execute horizon/entry-price, PostMortem scoring, Predict baseline
  price) are backward-compatible and re-proven by the neutrality suite.

## What remains deferred (do NOT do until opened)

- **A settlement-elapsed live run** — the back-to-back T6 run did not cross a 24h
  horizon, so no trade settled/scored live (the path is test-proven). A run left
  running ~24h (or `--horizon-hours` short) demonstrates it.
- **The LLM-as-method-selector thesis** — full Predict roster (mean_reversion,
  arima) + LLM selection so R4 fires; `IN_WINDOW → verdict`. Separate phase (§6).
- **Finnhub live news** — optional; unset in this run (momentum is OHLCV-only).
- **Portfolio rehydration on restart** — the runner carries portfolio in memory;
  cold-start reconstruction from the app db is a later refinement.
- **VPS deployment** — local-first was the ruling; VPS is a later option.

## Live-operation phase — complete

The momentum instrument is live on real data, governed end-to-end, served by a
self-hosted open-source LLM, and producing real Store A/B records that replay
reconstructs cleanly. The definition of done is met. Branch left for human review
+ merge.
