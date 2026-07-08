# T6b — Settlement-Elapsed Live Run Report

**Branch:** `postv1-t6b-settlement` (off merged `main`; not merged — for review)
**Date:** 2026-07-08 (live, US market open)
**Purpose:** Close the live-operation phase's last open checkbox — prove the LIVE
runner triggers settle → score → baseline-shadow → persist on REAL data. This is a
run-and-verify task; the settlement path was already built (T4).
**LLM:** self-hosted Ollama `qwen3:latest` (reachable, served Research + bias-tags).
**Data:** real yfinance quotes throughout (entry AND exit prices are live quotes).

---

## Command(s)

1. Organic settlement attempt (3 cycles, horizon 0, real Ollama + yfinance):
   ```
   PAPER_TRADER_LIVE_MODE=1 PAPER_TRADER_LLM_PROVIDER=ollama OLLAMA_MODEL=qwen3:latest \
     scripts/run_live.py --cycles 3 --horizon-hours 0 --require-ollama
   ```
2. Seeded settlement (one real open trade → one harness cycle settles it):
   seed a paper_trade at the live AAPL quote with `expected_exit_time` in the past,
   then `run_live.py --cycles 1 --horizon-hours 0 --require-ollama`.

## Headline result

**The settlement path is proven on real data.** But it required a seeded open
trade, because **the organic run produced ZERO trades** — see below.

## Why the organic run settled nothing (not a bug)

Across 3 live cycles: **43 predictions, 19 actionable Views, every one direction
`DOWN`.** v1 Execute is LONG-only, so all 19 were correctly declined
(`risk_reason=long_only_v1`) → 0 trades opened → nothing to settle. Today's real
momentum was uniformly bearish across the (large-cap tech + majors) watchlist, and
a long-only momentum trader correctly sits out a down market. `pins_ok=True` every
cycle; `final realized_pnl=0.00`. This is faithful behavior, recorded — not a
failure. (Restricting factors + solution levers: §"Restricting factors" below.)

## Seeded settlement — verified on real records

One open trade was seeded at the **live** AAPL quote ($307.32), `expected_exit`
in the past, then one real harness cycle ran. Verified against the app db +
Store A artifacts:

- **Settled:** `paper_trades` row `exited=1`, exit_price `$307.32` (real live quote
  at settlement), exit_time stamped. ✓
- **Scored + persisted:** one `post_mortems` row, FK chain intact
  (post_mortem → paper_trade → prediction). `direction_correct=1` (hit),
  `predicted_magnitude_pct=1.5`, `actual_magnitude_pct≈0`, `magnitude_error=1.50`,
  real `simulated_pnl`. The T4 dropped-persistence bug stays fixed. ✓
- **Baseline shadow:** `baseline_pnl` computed + persisted (parity with the trade
  in momentum-only v1, as designed — the measuring stick the thesis will later
  score against). ✓
- **Bias tags:** real Ollama qwen3 returned a clean terse tag `["overconfidence"]`
  (the first-round essay-parsing fix holds — no essay stored). ✓
- **Replay:** the settle cycle reconstructs with **all skill pins hash-VERIFIED**. ✓
- **No secret in the frozen trace:** scanned all Store A frozen input/output
  (206 KB); the only "token" hit is `cycle_token_budget: 15000` (a legit frozen
  config number). No API key, no Ollama endpoint, no localhost, no key value. ✓
- **Observer findings:** `[]` (silence — agents behaved; the seeded trade was a hit
  so no outcome-mismatch). ✓

## Real-data bugs found this run

**None.** The settlement/scoring/persistence path ran clean on real prices; the
first-round fixes (bias-tag parsing, baseline math, persistence FKs) all held.

## Definition of done

The `[~]` settle+score checkbox is now exercised on real data end-to-end:
a real trade opened, crossed its horizon, settled at a real quote, was scored
(hit/miss + P&L + baseline shadow), persisted with correct FKs, replayed with pins
VERIFIED, and leaked no secret. Marked `[x]`.

## Restricting factors (why the organic loop trades so rarely) — for solutioning

1. **Long-only (the dominant limiter).** v1 Execute cannot short. On a down day
   every DOWN View is declined → 0 trades. THE reason today was flat. Enabling
   shorts is a real feature build + a **gated skill change**, not a config tweak.
2. **Momentum-only Predict.** Only "did it rise recently?"; no mean-reversion,
   ARIMA, or LLM method-selection. One signal, easily unanimous. (The deferred
   thesis phase.)
3. **Small, correlated watchlist.** 8 large-cap tech + majors move together, so 8
   symbols ≈ 1 independent signal on a broad move. Cheapest lever: add diverse /
   counter-cyclical symbols in `config/watchlist.toml` (plain config).

The biggest single lever is #1: even momentum-only on a tiny watchlist would trade
on a down day IF it could short.

## Discipline held

DC-1 intact (no `steward/` edits); settlement logic unchanged (no bug surfaced);
app-db-only writes; observer the only Store B writer; no secret in the trace.
Full test suite green (448 passed) before the run. The seed is a throwaway
scratchpad script (not committed to `src/`); only this report is a deliverable.
