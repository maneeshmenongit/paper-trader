# Stage 0 — Feasibility Backtest · Completion Report

**Branch:** `postv1-stage0-feasibility` (off `main`)
**Authority:** `STAGE0_BUILD_PROMPT` + approved `STAGE0_BUILD_NOTE`; `THESIS_STAGES_001` §2–§5.
**Mode:** single `steward-wave` bounded task, §7 build order, human gate at the end.
**Result:** **GO** — real headroom exists; Stage 1 is unblocked. (A NO-GO would have
been equally successful; inputs were not tuned.)

---

## What was built (§7 order)

| Step | Deliverable | Tests |
|---|---|---|
| 1 | `analytics/pnl.py` + `analytics/direction_score.py` (real math extracted from `postmortem.py`); `postmortem.py` rewired | `test_analytics_math.py` (9); `test_postmortem_agent.py` unchanged & green |
| 2 | `data/offline.py` seam serves real cached closes by `(symbol, timestamp)`, guarded `>0 & finite`; optional `timestamp` on the protocol | `test_offline_seam.py` (10) |
| 3 | `backtest/methods.py` — momentum (verbatim), mean_reversion, arima (numpy AR(1)) + per-point eligibility | `test_backtest_methods.py` (14) |
| 4 | `backtest/stage0_settlement.py` — thin adapter over the real math, long-only enter-iff-UP | `test_stage0_settlement.py` (6) |
| 5 | `backtest/sanity.py` — the five §4 checks as raising assertions | `test_stage0_sanity.py` (14) |
| 6 | `backtest/stage0_harness.py`, `stage0_universe.py` (frozen, de-correlated), `stage0_gate_report.py`, `scripts/run_stage0.py` | `test_stage0_harness.py` (6) |
| 7 | Ran on the real frozen universe → `STAGE0_GATE_REPORT.md` | — |

**Tests: 448 → 507 passed** (+59). Ruff clean. Mypy clean on all changed files
(see deviation D2 re: `--python-version`).

---

## The result (dollar table)

| Measuring stick | Realized P&L |
|---|---:|
| Floor (always-momentum) | **$2,110.90** |
| Oracle-best-method (must-trade hindsight pick) | **$88,443.33** |
| Ceiling (perfect foresight, horizon-matched) | **$116,808.97** |

- **Headroom (oracle − floor): $86,332.43 → 86.3% of a $100k bankroll.**
- Trade count: **14,340 points**, 30 symbols. Not a small-sample artifact.
- Threshold **E = 3.0%** (Gap C, return-on-bankroll). 86.3% ≫ 3.0% → **GO**, robustly.
- All five sanity checks **PASSED** (the run halts otherwise).

**Honest reading:** the 2024–2026 window is a rising market; momentum barely
participates ($2.1k of $116.8k available), so a perfect *method*-picker has large
headroom. GO means the headroom EXISTS for Stage 1 to chase — not that the LLM will
capture it. That is Stage 1's question, framed by the floor/ceiling band.

---

## §1 hard constraint — met

- **Imported, not re-coded:** `analytics.pnl` (`realized_pnl`, `actual_move_fraction`),
  `analytics.direction_score` (`direction_correct`), `settlement.engine.horizon_exit_time`.
- The Stage-0 adapter has **no P&L/horizon arithmetic of its own**; it drives the real
  functions over cached data through the fixed `OfflineMarketData` seam (real cached
  closes, never fabricated).
- Sanity check #2 is therefore load-bearing: momentum-method P&L and the momentum
  floor flow through the *same* real math — their equality is a real invariant, verified
  over all 14,340 points.

---

## Deviations (flagged, not silent)

**D1 — Recorded spec amendment: `analytics/pnl.py` + `analytics/direction_score.py`
did not exist.** `STAGE0_BUILD_PROMPT` §1/§3 named them as "the real math to import,"
but the math lived inline in `PostMortemAgent`. Per the human gate decision, it was
**extracted verbatim** (behavior-identical) into those two modules and `postmortem.py`
rewired to call them — creating the single real scoring path the prompt assumes. This
is the only sanctioned touch of the live loop; `test_postmortem_agent.py` is unchanged
and green, proving behavior-neutrality. **The authority docs should be updated to say
"extract to" rather than "import from."**

**D2 — Pre-existing mypy/numpy config drift.** The project pins `python_version = "3.11"`,
but the venv is 3.12 and numpy 2.5's stubs use a 3.12-only `type` statement, so mypy
under the pinned target errors *inside numpy's own `.pyi`* on any file importing numpy
directly (`methods.py` is the first such file in the tree). All Stage-0 code type-checks
**clean under `--python-version 3.12`** (the real interpreter). Not caused by this work;
recommended follow-up: bump the mypy `python_version` to `3.12` to match the venv.

**D3 — Oracle definition corrected mid-run.** The first run used a per-point
`max(0, best)` oracle (free abstention → $103k). §5 defines the oracle as picking the
best *method* and trading it, so it was changed to must-trade-best-eligible ($88k) — the
honest, **smaller** bound. This tightened the result against GO, not toward it.

---

## Scope honored (§8 deferrals)

No LLM/tokens/router, no scheduler, no live clients, no app-db, no Store A/B, no
shorting, no verdict logic. The frozen live loop was untouched except the sanctioned D1
extraction. Deferred review findings (**C1, H1, H3, H4/H5/H7, H9–H13**) remain in
`docs/CODE_REVIEW_IMPROVEMENTS_001.md`, due at Stage 3.

## ⚠ Loud flag carried forward — H3 is a Stage-3 precondition

Live `YFinanceMarketData` defaults to `interval="1h"`. Stage 0 ran on **daily** bars
(correct semantics). **Before Stage 3's live R4 run, the live path must be reconciled to
daily semantics** or it will disagree with the very backtest that justified it. Tracked as
finding **H3**.

## Known gaps

- **No crypto in the cached data.** §3 allows crypto; the harness supports it, but no
  crypto history was fetched. Recorded, not silently dropped — fetch before any run that
  claims cross-asset-class coverage.

---

## Gate

Stage 0 = **GO**. Do not open Stage 1 without human sign-off. Branch left for review +
merge. Next task (Stage 1) is a separate bounded prompt.
