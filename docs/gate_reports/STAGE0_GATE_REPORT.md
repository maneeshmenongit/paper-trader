# Stage 0 — Feasibility Backtest · Gate Report

**Deterministic, no LLM.** A NO-GO is a *successful* test (the thesis is
falsified cheaply). Inputs were NOT tuned to force a GO.

## 1. Dollar table

- Seed bankroll: **$100,000**
- Universe: **30 symbols**, **14340 points**

| Measuring stick | Realized P&L |
|---|---:|
| Floor (always-momentum) | $2,110.90 |
| Oracle-best-method (hindsight-perfect pick) | $88,443.33 |
| Ceiling (perfect foresight, horizon-matched) | $116,808.97 |

### Per-method

| Method | P&L | Entered | Hit-rate |
|---|---:|---:|---:|
| momentum | $2,110.90 | 7443 | 51.3% |
| mean_reversion | $5,186.36 | 6605 | 52.4% |
| arima | $5,771.21 | 7164 | 52.4% |

## 2. Headroom

- **Headroom (oracle − floor): $86,332.43**
- Edge ratio (headroom / seed): **86.332%**
- Trade count (points scored): **14340** (so a small-sample edge cannot masquerade as signal)

## 3. Sanity checks (§4)

- **ALL PASSED** — #1 ceiling-bound, #2 floor cross-check, #3 entry-price realism, #4 no-look-ahead, #5 non-zero settlement.
- The run halts on any violation, so reaching a verdict means all held.

## 4. Threshold & verdict (Gap C)

- Edge threshold **E = 3.00%** of seed bankroll (return-on-bankroll edge; +3pp used only as a reference magnitude).
- Edge ratio 86.332% ≥ E 3.00%.
- **VERDICT: GO** — real headroom exists; open Stage 1 (LLM-selector backtest).

## 4b. How to read this headroom (honesty notes)

- **Oracle definition (conservative).** Oracle-best-method = per point, pick the ELIGIBLE method that turned out right and **trade it** (must-trade — a losing best-of-a-bad-lot point still costs). It gets perfect *method choice* but NOT free abstention or timing. An earlier draft floored each point at 0 (free abstention), inflating the oracle to ~$103k; that conflates selection skill with timing skill Stage 1's selector won't have, so it was removed. The reported oracle is the smaller, honest bound.
- **Market regime.** The 2024–2026 window is a rising market (ceiling $116,809 of available upside). The floor (always-momentum) captured only $2,111 of it — momentum barely participates. The headroom is real, but Stage 1 must show the LLM captures it as *skill*, not just by riding the tape (that is exactly the floor/ceiling band's job).
- **What GO means precisely.** A *perfect* method-picker clears the floor by 86.3% of bankroll over 14,340 points. So there IS headroom for a selector to fight for — the necessary precondition for Stage 1. It does NOT mean the LLM will capture it; that is Stage 1's question.

## 5. Universe spread (§3 discharge)

- Sector spread: comm_media: 4, consumer: 6, financials: 6, high_beta: 4, payments_semis_sw: 4, tech: 6.
- Deliberately de-correlated and tech-capped (not the predecessor's tech-heavy 50-name set), so the result is not a false NO-GO from homogeneity.
- **Gap:** no crypto in the cached data — the harness supports crypto symbols, but none were fetched. Recorded, not silently dropped.

## 6. Real-math + real-seam constraint (§1)

- **Imported (not re-coded):** `analytics.pnl` (realized_pnl, actual_move_fraction), `analytics.direction_score` (direction_correct), and `settlement.engine.horizon_exit_time`.
- The Stage-0 adapter contains **no P&L or horizon arithmetic of its own** — it drives the real functions over cached data via the fixed `OfflineMarketData` seam (real cached closes, never a fabricated price).
- This is why sanity check #2 is load-bearing: the momentum method and the momentum floor flow through the *same* real math, so their equality is a real invariant.

## 7. ⚠ Stage-3 precondition — H3 (live hourly-bar default)

- The live `YFinanceMarketData` defaults to `interval="1h"`. Stage 0 ran on **daily** cached bars (correct semantics), but the live R4 run in Stage 3 must be reconciled to daily semantics **or it will disagree with this backtest** — the momentum/liquidity signals were designed for daily closes. This is a **hard precondition for Stage 3**, tracked in `docs/CODE_REVIEW_IMPROVEMENTS_001.md` (finding H3).
