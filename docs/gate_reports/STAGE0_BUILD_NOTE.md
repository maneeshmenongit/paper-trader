# Stage 0 — Feasibility Backtest · Build Note (explain-before-code)

**Document ID:** `STAGE0_BUILD_NOTE`
**Date:** 2026-07-08
**Authority:** `STEWARD_PAPER_TRADER_THESIS_STAGES_001` §5 (Stage 0), §2 (Gaps A/C), §4 (sanity checks), §3 (fences).
**Status:** proposal for the human gate. **No code written yet.** This note explains
what Stage 0 builds, how it tests, which review findings fold in, and which defer —
per the doc's own "explain before code" discipline.

---

## 1. What Stage 0 must answer

> Could a *perfect* method-picker even beat always-momentum, in fake dollars, on a
> fixed diversified universe over real history? Is there headroom worth an LLM chasing?

Deterministic. No LLM. No verdict logic. Cheapest possible falsifier — if a perfect
picker can't beat the floor, no LLM can, and the phase stops here (weeks saved).

**Gate outcome:** `oracle_best_method_pnl − floor_pnl ≥ Gap-C threshold` → **GO** (open
Stage 1). Otherwise → **NO-GO (thesis dead)**, which is a *successful* test.

---

## 2. What already exists vs. what's new

| Piece | Status | Note |
|---|---|---|
| `backtest/universe.py` (50-symbol fixed universe) | **reuse** | Fixed up front → no survivorship bias, as §5 requires. May widen sectors/crypto per §3, but fixed before the run. |
| `backtest/historical_fetch.py` (**daily** Parquet cache) | **reuse** | Already daily OHLCV — see §6 below, this is why Stage 0 sidesteps the hourly-bars bug. |
| `backtest/sample.py` / `baseline.py` / `evaluation.py` | **NOT reused for scoring** | These score **hit-rate in percentage points** (the T02–T04 machinery). Stage 0 scores **dollars**. `baseline.momentum_prediction` is reused as the *floor method*, but `evaluate/compare` are the wrong measuring system. |
| `settlement/engine.py` horizon math | **reuse the math, not the async DB path** | `horizon_exit_time` and the entry→exit→P&L shape are the model. The live `settle_due_trades` talks to the app-db + a live quote; Stage 0 settles deterministically against cached history (§6). |
| Three forecasting methods (momentum, mean_reversion, arima) | **NEW** | §5 requires all three, mechanical, no LLM. Only momentum exists today (in `agents/predict.py` + `backtest/baseline.py`). |
| Dollar-P&L harness (floor / oracle / ceiling / per-trade rows / running balance) | **NEW** | The core of Stage 0. |
| The five §4 sanity checks as harness assertions | **NEW** | §4 is explicit: "assertions in the harness, not commentary." |

---

## 3. What we build

Four new modules under `src/paper_trader/backtest/`:

**`methods.py` — the three deterministic forecasting methods.**
Each takes a symbol's daily history strictly *before* the decision date and returns a
`MethodForecast(direction, magnitude_pct, eligible: bool)`. Long-only per §3, so a
DOWN forecast = don't-enter (no short).
- `momentum` — last close vs the prior close (reuses the existing rule verbatim; must
  agree bit-for-bit with `baseline.momentum_prediction` — see §4 check #2).
- `mean_reversion` — position vs a short SMA; fade the recent move.
- `arima` — minimal AR(1)/ARIMA fit on the pre-decision window; ineligible if the fit
  can't be formed (too little history) → feeds R1 eligibility later.
Eligibility is per-method and per-point, so a point can have 1, 2, or 3 eligible
methods — this is what Stage 1's R4 will later select among.

**`dollar_engine.py` — deterministic settlement in fake dollars.**
Entry at the real cached close on the decision date; exit at the real cached close at
the horizon (Gap A default: **horizon-matched**). P&L = `qty * (exit − entry)` for an
entered LONG, `0` for don't-enter. This is the *model* of `settlement/engine.py` with
the app-db and live-quote seams removed — pure and replayable. Fixed seed bankroll,
fixed position sizing (kept trivial and identical across strategies so the *method
choice*, not the sizing, drives the comparison).

**`sanity.py` — the five §4 checks as assertions.** See §5.

**`stage0_harness.py` — the run + the dollar table.**
Loads cached history, builds the pre-specified point set, runs each strategy through
`dollar_engine`, computes:
- **Floor** — always-momentum realized $.
- **Oracle-best-method** — always picking (in hindsight) whichever *method* was right →
  the hard upper bound on any selector. `oracle − floor` = **the headroom**.
- **Ceiling** — perfect-foresight $ (horizon-matched, floors at 0 for long-only).
- **Running balance** + **per-trade rows** (entry, exit, P&L) so no number is a black box.

Plus a small CLI (`scripts/`) and a gate-report writer.

---

## 4. Gap C — the edge threshold (set here, per §2 Gap C)

§2 flags that the predecessor's **+3.0pp** bar was a *hit-rate* threshold and does **not**
transfer to a dollar metric. Stage 0 must set the dollar/return edge threshold explicitly.

**Proposal (for the gate to ratify):** express the threshold as a **return-on-bankroll
edge**, not percentage points: `GO if (oracle_pnl − floor_pnl) / seed_bankroll ≥ E`, with
**E = 3.0%** as the opening value — using +3pp only as a *reference magnitude*, not a copy
of the hit-rate rule. Rationale: a return-on-capital edge is the honest dollar analogue
and is directly comparable to Stage 1's "edge over floor." I'll surface the raw headroom
figure regardless, so the gate can move E with full information. **This is a flagged
parameter, not a silently-filled one** (§2 Gap C discipline).

---

## 5. The five §4 sanity checks → harness assertions

| # | §4 check | Assertion in `sanity.py` | Halts on |
|---|---|---|---|
| 1 | Ceiling is a hard bound | `strategy_pnl ≤ ceiling_pnl` per trade **and** in aggregate | any violation → scoring is broken |
| 2 | Floor cross-check | when the selected method **is** momentum, its per-trade P&L == the independently-computed momentum floor P&L for that point | any divergence → dropped-baseline bug class |
| 3 | Entry-price realism | every entry price == the real cached close (never a round-number fallback) | any `100.0`-style placeholder |
| 4 | No look-ahead | every method reads only bars **strictly before** the decision date; oracle/ceiling are computed separately and never fed to a method | any method touching ≥ decision-date bar |
| 5 | Settlement on a real non-zero move | trades settle on real magnitude; assert the aggregate isn't a degenerate all-zero-move set | all-zero (the T6b asterisk) |

---

## 6. How review findings fold in — the key mapping

§4 states the checks are *"motivated by the five bugs the live run surfaced."* Three of
those bug classes are findings from the recent review
([CODE_REVIEW_IMPROVEMENTS_001.md](../CODE_REVIEW_IMPROVEMENTS_001.md)). For Stage 0 they
are **not** a detour — passing the §4 assertions *requires* handling them. But the fix
lands **in the new Stage 0 code**, not by editing the live loop (that stays frozen until
its own stage).

**Folds in now (on the Stage 0 critical path):**

- **§4.3 ⟷ M25 / offline-100.0** — `OfflineMarketData.get_current_quote` returns a flat
  `100.0`, and `execute._entry_price` has a `100.0` fallback. Either would make every
  Stage 0 trade a zero-move settlement and trip check #5. **Fix in Stage 0:**
  `dollar_engine` prices exclusively from real cached closes and asserts it (check #3);
  it never touches `OfflineMarketData`. The live-loop fixes (M25 proper, offline seam)
  **defer** — Stage 0 doesn't use that path.
- **§4.2 ⟷ baseline sign/direction threading (M12 + the `-0.0` L-finding)** — the floor
  cross-check compares momentum-method P&L to the momentum floor; the DOWN/HOLD magnitude
  sign handling must be correct or check #2 trips. **Fix in Stage 0:** `dollar_engine`
  carries direction explicitly (long-only: enter iff UP), never encodes it in a
  magnitude sign. The live PostMortem `_baseline_pnl` fix **defers** to its stage.
- **§4.5 ⟷ H6 (exit-price guard)** — a `0.0`/NaN cached close must not settle a trade at
  garbage. **Fix in Stage 0:** `dollar_engine` guards `exit_price > 0 and isfinite`, and
  the harness drops NaN rows up front (also fixes the backtest-NaN L-finding for this
  path). The live `settle_due_trades` guard **defers**.
- **§4.4 ⟷ M24 (bar ordering)** — methods must read chronologically-sorted, pre-decision
  bars only. **Fix in Stage 0:** the point builder sorts by date and slices strictly
  `< decision_date` (the existing `sample.py` already sorts; the new methods inherit it).

**Deliberately deferred (not on the Stage 0 path — they belong to the live loop):**

- **C1** (per-cycle crash isolation + settlement recovery sweep), **H1** (cash/equity
  model), **H4/H7** (per-process budget reset, budget bypass), **H3** live hourly-vs-daily
  bars, **H5** (symbol-vs-identity settlement), and all framework findings (**H9–H13**,
  observer/DC-1/proposer/TOCTOU). **Why safe to defer:** Stage 0 has no scheduler, no LLM,
  no live clients, no app-db writes, and no Store A/B — the entire surface those findings
  live on is absent. They stay in the register and come due at **Stage 3** (live
  integration), which is exactly where the doc sequences the live run.

**Note on H3 specifically:** the live bug is that `YFinanceMarketData` defaults to
`interval="1h"`. Stage 0's `historical_fetch.py` already caches **daily** bars, so the
feasibility result is computed on correct daily semantics regardless. H3 must be fixed
before **Stage 3**'s live R4 run, or the live path will disagree with the Stage 0/1
backtest that justified it — I'll flag this loudly in the Stage 0 gate report as a
Stage-3 precondition.

---

## 7. What Stage 0 does NOT touch

- No LLM, no tokens, no router.
- No `evaluation` / verdict logic (that's Stage 2, gated on Gap B).
- No live clients, no scheduler, no Store A/B, no app-db.
- No shorting (§3 fence); long-only, ceiling floors at 0.
- No auto-optimization / no prompt-engineering around a NO (there's no prompt here).

---

## 8. Definition of done (Stage 0 gate)

A gate report containing:
1. The dollar table: floor, oracle-best-method, ceiling, running balance, per-trade rows.
2. The **headroom** figure (`oracle − floor`) and its ratio to bankroll.
3. All five §4 sanity-check results (must be green, or the run is not trustworthy).
4. The Gap-C threshold used, stated explicitly, with the GO/NO-GO call.
5. A loud flag: **H3 (hourly bars) is a Stage-3 precondition.**
6. Tests/lint/mypy green.

---

## 9. Proposed build order (one bounded step, then gate)

1. `methods.py` (+ tests: each method's forecast + eligibility on fixtures).
2. `dollar_engine.py` (+ tests: entry/exit/P&L, the exit-price guard, long-only enter-iff-UP).
3. `sanity.py` (+ tests: each of the five assertions fires on a seeded violation).
4. `stage0_harness.py` + CLI (+ an end-to-end test on a small cached slice).
5. Run on the real cached universe → write the gate report.

**Requesting the gate:** approve this note (or adjust Gap-C E, the universe, or the
deferral line) and I'll build steps 1–5. If you'd prefer this run under the full
`steward-wave` discipline (fresh branch, bounded task, completion report), say so and
I'll invoke it instead.
