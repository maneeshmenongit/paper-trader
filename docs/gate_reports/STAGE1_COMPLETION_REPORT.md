# Stage 1 — LLM-Selector Backtest · Completion Report

**Branch:** `postv1-stage1-llm-selector` (off main, after Stage 0 merged)
**Authority:** `STAGE1_BUILD_PROMPT` + `THESIS_STAGES_001` §6; carries Stage 0 §1 real-math constraint.
**Mode:** single `steward-wave` bounded task, §8 build order, human gate at the end.
**Result:** **FAILED** — the LLM selector did not beat the cheap null selector; it made
*worse* method picks than doing nothing clever. Per the discipline, **a FAILED on
evidence is a successful test.** The prompt/threshold/universe were NOT tuned to flip it.

---

## The verdict, in one line

An LLM (qwen2.5:7b) choosing which of three mechanical forecasting methods to trust,
over 600 real point-in-time decisions, **lost money relative to always-momentum** — and
came nowhere near the +3% edge bar. The "let an LLM pick the method" thesis is **not
supported** on this universe and this model.

---

## The dollar table (600 sampled points, same points for every strategy)

| Strategy | Realized P&L | Note |
|---|---:|---|
| always_momentum (floor) | $2,110.90 | the dumb, free baseline |
| null_selector (the real bar) | $2,110.90 | 5-line "best recent method" rule → picked momentum |
| random_among_eligible | $5,138.41 | random beat the LLM (!) |
| **llm_selector** | **$255.58** | 382 settled, 600 evaluated |
| oracle_best_method (hindsight) | $88,443.33 | perfect method pick — the headroom |
| ceiling (perfect foresight) | $116,808.97 | unreachable bound |

- **LLM edge over the effective floor: −$301.17 (−0.301% of bankroll)** vs the **+3.0%**
  bar (Gap C, E). Not just short — **negative**.
- **Headroom captured: −9.3%** (it moved *away* from the oracle, not toward it).

## Why it failed — the mechanism (not just the number)

The LLM picked **mean_reversion 412/600 times (69%)**, momentum 175, arima 13. The null
selector's trailing-performance rule, by contrast, stuck with **momentum** (which had the
best recent record — so its P&L equals momentum's exactly). In this rising-market window,
the LLM's systematic bet on *fading* moves (mean_reversion) was the wrong call: momentum
kept paying and reversion kept losing. The AI's active method-switching **destroyed** the
value that simply riding momentum would have captured. Even **random** selection beat it,
because random still lands on momentum a third of the time instead of over-committing to
reversion.

This is a decisive, legible failure — exactly the kind the experiment exists to surface.

---

## Trust: why the verdict is FAILED (not INCONCLUSIVE, not a bug)

- **Diversity floors MET** — 30 symbols (≥20), 478 distinct decision-dates (≥130), 382
  settled LLM points (≥100). Enough coverage to judge → FAILED, not INCONCLUSIVE.
- **All five §4 sanity checks PASSED** — ceiling-bound, floor cross-check, entry-price
  realism, no-look-ahead, non-zero settlement. Scoring is trustworthy.
- **Step 0 floor cross-check PASSED first** — an independent 5-line recompute reconciled
  the inherited $2,110.90 momentum floor to the penny *before* any LLM token was spent,
  so the load-bearing GO number is verified.
- **Fusion-trap guard confirmed (§2.3)** — the null selector's trailing scoreboard is fed
  only by horizons closed strictly before each decision; the LLM feature builder reads
  only pre-decision closes. No post-decision data reached either selector.
- **Same-points comparison** — the LLM edge is measured over the *same* 600 points the LLM
  ran on (sampled-subset floor/null/oracle), not full-universe totals — a fair edge.

## §2.1 real-math constraint — met

Imported, never re-coded: `analytics.pnl`, `analytics.direction_score`,
`settlement.engine.horizon_exit_time`, priced via the fixed `OfflineMarketData` seam.
The Stage 1 harness adds no P&L/horizon arithmetic; every strategy — including the LLM's
picks — settles through the same Stage 0 adapter, which is what makes the floor
cross-check load-bearing.

## LLM discipline (§5) — honored

- **600 calls, cache 0, 180,866 tokens.** Cap `--max-calls 700` (not hit). Cache persists
  to `data/backtest/stage1_selection_cache.json` → re-runs are free.
- **Fixed, versioned prompt** `stage1-selector-v1`, set up front. NOT iterated to chase a
  pass (the predecessor's failure mode, forbidden by §2.4).
- **Model:** qwen2.5:7b, local via Ollama.

---

## Deviations & decisions (flagged)

**Model choice — a weaker-model caveat (honest).** The run used a local **7B** model
(qwen2.5:7b), not a frontier selector. §5 notes a weak model makes a FAILED a *somewhat*
weaker refutation. Rationale for the choice: Groq's free tier (llama-3.3-70b) hit its
100k-tokens/day limit after ~150 calls, and a full floor-clearing run needs ~600; the
local model is unlimited and free (honoring the user's "free before paid" guidance). The
result is still decisive **directionally** — the LLM didn't merely tie the cheap rule, it
lost to it *and* to random, a margin a stronger model would have to overturn entirely, not
just nudge. A frontier-model re-run is a cheap future confirmation if desired, but is not
required to accept the NO on this model.

**New framework capability built mid-stage (user-requested): fast/reasoning model-tier
routing.** `llm/model_tiers.py` + `live/providers.build_tiered_router` + config fields
route judgment-heavy purposes (predict_selection) to a reasoning model and high-volume
mechanical purposes to a fast model, independently. Empty reasoning tier → reuses the fast
tier (a pure superset of prior behavior). Used to run this stage; reusable for Stage 3.

**Latent seam regression fixed.** The Stage 0 widening of
`MarketDataProvider.get_current_quote(symbol, timestamp=None)` had left `YFinanceMarketData`
and `FakeMarketData` on the old signature; mypy caught it once `providers.py` was
type-checked. Both now conform (timestamp ignored live).

**Infrastructure hardening.** `select_sample` was fixed to respect its target (it had
floored to ~478 regardless — the cause of two seemingly-"hung" runs); a per-run progress
callback was added so a slow run is never mistaken for a stall; and the selector raises a
typed `LLMUnavailableError` (clean halt) instead of a raw transport traceback.

---

## Scope honored (§7 deferrals)

No verdict *resolver* (Stage 2, gated on Gap B — Stage 1 only computes the pass/fail
figure). No scheduler, no live clients, no app-db, no Store A/B, no shorting, no edits to
the frozen live loop (except the sanctioned Stage 0 analytics extraction, already gated).
Deferred review findings (C1, H1, H3, H4/H5/H7, H9–H13) remain in the register, due at
Stage 3.

## Carried flags (restated)

- **No-news / Stage-3 Research delta (§2.2):** the backtest is equal-information with no
  news bundle. Research's contribution is a known Stage-3 delta, not in this verdict — so
  the NO is specifically "price-features-only method selection doesn't work," leaving open
  (barely) whether news would change it at Stage 3.
- **H3 (live hourly-bar default):** a **Stage-3 precondition**.
- **No-crypto gap:** cached data is equities-only.
- **D1:** the Stage 0 live-loop extraction to be logged in the alternatives register.

## Tests / quality

- **Full suite green** at the last commit before the run (551 tests). Ruff clean. Mypy
  clean on all changed files under `--python-version 3.12` (Stage 0 D2 config note stands).

---

## Gate — what happens next

Stage 1 = **FAILED**, a successful, decisive test. The recommended read:

1. **The thesis, as scoped here, is not supported.** An LLM picking among momentum /
   mean_reversion / arima on price features alone does not beat a trivial rule — it loses.
   This is the cheap-falsifier working exactly as intended (cf. T02–T04's coin-flip NO).
2. **What remains genuinely open** before calling the whole method-selector idea dead:
   (a) a **stronger model** (the 7B caveat), and (b) the **Research/news delta** (§2.2) —
   both deferred by design. Neither is guaranteed to flip a −0.30% result, but both are
   legitimate follow-ups.
3. **Do not tune to force a pass.** The prompt, threshold, and universe stay fixed.

Per the discipline: **stop at the gate.** Do not open Stage 2. The human decides whether
to (a) accept the NO and stop the thesis phase, (b) re-run once with a frontier model to
confirm, or (c) proceed to Stage 3 to test the news delta on live data. Branch left for
review + merge.
