# Live-Operation T6 — First Live Run Report (the milestone gate)

**Branch:** `postv1-t1-live-data-clients` (off `main`; NOT merged — for review)
**Run:** 2026-07-07, US market open (14:09 UTC / 10:09 ET, Tuesday)
**Command:**
```
PAPER_TRADER_LIVE_MODE=1 PAPER_TRADER_LLM_PROVIDER=ollama \
  scripts/run_live.py --cycles 3 --interval-seconds 0 --require-ollama \
  --run-dir ./data/runs/t6-first-live
```

**Verdict: the phase's definition of done is MET.** A live, governed,
open-source-LLM **momentum** paper-trader ran on real market data, executed real
paper trades at real prices, produced real governance records (Store A/B), and
replay reconstructed every live cycle with all skill pins hash-VERIFIED.

---

## What ran — real components, real data

| Element | Live? | Evidence |
|---|---|---|
| Market data | **Real yfinance** | 12 trades at real intraday prices; prices drift across cycles |
| LLM (Research) | **Real Ollama `llama3.1:8b`** | preflight REACHABLE; **48** local `/api/chat` calls |
| Clock | Real `LiveClock` (wall clock) | cycle headers timestamped 14:09–14:11 UTC |
| Governance | Real Emitter + Observer + Replay | 3 Store A headers, 12 invocations, 3 replays |

## Grounded totals (from the app db + replay artifacts, via `summarize_run`)

- **Cycles:** 3 · **Trades executed:** 12 (4/cycle) · **Symbols traded:** AMZN, GOOGL, JPM, MSFT
- **Store A:** 3 cycle headers, 12 agent invocations (all pinned) · **Store B findings:** 0
- **Baseline shadow rows:** 24 (the momentum measuring stick, persisted, never traded)
- **Replay:** 3 cycles reconstructed, **all pins hash-VERIFIED**
- **Settlements:** 0 — expected (back-to-back run; the 24h horizon has not elapsed)

**Real entry prices** (min–max across cycles, minutes apart — proving live tape):
AMZN 246.51–246.84 · GOOGL 371.19–371.47 · JPM 340.73–340.87 · MSFT 391.70–392.78.

**Momentum selection was real:** MSFT/GOOGL/AMZN/JPM forecast UP (confidence
0.64–0.78 from actual price moves) → traded LONG; NVDA/BTC/ETH forecast DOWN →
correctly NOT traded (LONG-only v1). Selection mode: `rule` (momentum-only, R3).

## No secrets in the frozen trace (DT-4.2 held on real data)

The frozen `orchestrator_input` contains only: calibration_version, cycle_kind,
horizon, token_budget, log_level, research_semaphores, watchlist. **No API key, no
Ollama endpoint, no `localhost`/`11434`** — verified against the actual `.env`
values. The MUST-NOT-FREEZE membrane held under a live run.

## Five real bugs the live run surfaced (each fixed + regression-tested)

Only real data could expose these — the fakes/fixtures used tz-aware, round-number,
fresh values that masked every one:

1. **tz-naive bar timestamps** — live yfinance bars are tz-naive; Filter R4 crashed
   subtracting them from the UTC clock. Fixed: normalize to UTC-aware.
2. **Daily bars can't satisfy R4 freshness (60 min)** — switched the client to
   intraday (1h) bars, fresh during market hours, WITHOUT touching the ratified
   skill rule.
3. **Provider factory imported the test tree** — a live run crashed on
   `tests.fixtures`. Fixed: in-package `data/offline.py`.
4. **Execute filled every trade at the 100.0 placeholder** — it read the wrong
   `method_inputs_summary` key; the real price was under `last_close`. Fixed.
5. **`persist_cycle` dropped post-mortems and baseline-shadow rows** — the T4
   scoring was computed then discarded. Fixed: both now persist with correct FKs.

## What this run does NOT claim (honest scope)

- **No settlement/scoring occurred** — the 24h horizon has not passed in a
  back-to-back run, so no trade closed. The settle→score→baseline-shadow path is
  proven by tests (`test_settlement.py`, `test_harness.py`) and will fire on the
  next run whose clock is past a trade's horizon. A follow-up run left for ~24h (or
  `--horizon-hours 0`) would demonstrate it live.
- **The LLM-as-method-selector thesis stays UNVALIDATED** — Predict is
  momentum-only; R4 (multiple-eligible → LLM selection) never fired. That is a
  separate, later phase (authority §6).
- **Zero observer findings** is correct: the agents behaved within their skills on
  this run, so the officer had nothing to file — meaningful silence, not a gap.

## Definition of done — checklist

- [x] Loop ran live on real market data across a bounded window (3 cycles)
- [x] Trades executed on real prices (12, at real intraday quotes)
- [x] Governance machinery produced real Store A/B records (3 headers, 12 invocations)
- [x] Replay reconstructs a live cycle cleanly, pins VERIFIED
- [x] Open-source self-hosted LLM served the run (Ollama, 48 calls)
- [x] No thesis claim made or implied
- [~] Trades settled + scored — deferred to a horizon-elapsed run (path test-proven)

**T6 PASSES.** The instrument is live, governed, open-source-LLM, and producing
real records — the definition of done for the live-operation phase.
