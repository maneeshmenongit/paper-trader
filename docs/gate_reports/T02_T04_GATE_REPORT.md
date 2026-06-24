# T02–T04 Gate Report — Thesis Validation Backtest

**Branch:** feat/T02-T04-thesis-backtest
**Commits:**
- c615182 — T02: historical OHLCV fetcher with disk cache
- 52e847d — T02: fix ruff E501 line lengths and cache-coverage start slack
- bd37996 — T03: momentum baseline + sampling + evaluation harness
- 5ae7ca0 — T04: Gemini evaluation loop + GO/NO-GO orchestrator
- (this report)

**Started:** 2026-06-23
**Completed:** 2026-06-23

---

## Confirmation of understanding (per prompt §"Read First")

- This is a **self-contained validator**, not part of the production agent system. It
  lives entirely in `src/paper_trader/backtest/`, `scripts/`, and `tests/unit/`. No
  production code under `agents/`, `graph/`, or the live `data/` clients was touched.
- Gemini calls cost real free-tier quota. The implementation samples first, caches every
  prediction to disk, hard-caps calls per run, checkpoints every 25 calls, and spaces
  calls 1s apart. One full run = 500 calls, well within the daily free tier.
- **A NO-GO result is a successful outcome for this gate** — discovering the thesis is
  weak now, at week 0, is exactly what the gate is for. The run below honestly reports
  FAIL; no prompt or threshold was tweaked mid-run to manufacture a PASS.

---

## T02 — Historical Fetch

- **N symbols requested:** 50 (the built-in `DEFAULT_UNIVERSE`)
- **N successfully cached:** 50
- **N failed (with reasons):** 0
- **Cache total size:** 1.4 MB (50 Parquet files; well under the 50 MB ceiling)
- **Date range fetched:** 2024-06-24 → 2026-06-22 (2-year lookback, 500 trading days each)
- **Idempotency verified:** a second `python scripts/fetch_backtest_data.py` made **0
  network fetches** (50 cache hits). `--force` re-fetches all 50.
- **Schema verified:** each Parquet has `Open/High/Low/Close/Volume/Adj Close` indexed by
  a `Date` `datetime64` index.
- **Tests:** `pytest tests/unit/test_historical_fetch.py` — **8 passed** (yfinance mocked,
  no real network in tests). Covers download+cache, cache-hit-no-network, `--force`,
  stale-range refetch, empty/missing-column validation, per-symbol failure isolation,
  and `load_cached`.

## T03 — Baseline + Harness

- **Tests:** `pytest tests/unit/test_baseline.py test_evaluation.py test_sample.py`
  — **15 passed** (5 + 5 + 5), synthetic OHLCV, fully deterministic.
- **Baseline implementation matches spec:** yes. `momentum_prediction` returns UP iff
  `close[t-1] > close[t-2]`, else DOWN, using only history strictly before the
  prediction date, and raises `ValueError` on insufficient history.
- **Sample diversity constraints work:** yes. `sample_prediction_points` enforces ≥20
  distinct symbols and ≥130 distinct trading days, raises `ValueError` when the dataset
  can't meet them (verified with a 5-symbol universe and a too-short-history universe),
  and is reproducible for a fixed seed. Diversity check from the real run: **500 sampled
  points, 50 distinct symbols, 469 distinct trading days** — both floors cleared with
  large margin.
- **No LLM calls in T03:** confirmed — `baseline.py`, `sample.py`, `evaluation.py` import
  no LLM module (greppable: no `genai`/`groq`/`google.generativeai`).

## T04 — LLM Evaluation

- **Sample size:** 500 prediction points
- **Gemini calls actually made:** 500 (vs. cap of 500). 0 ERROR responses — every call
  returned valid JSON.
- **LLM cache hit on re-run:** **yes.** Re-running the identical command logged
  `cache hit: all 500 predictions loaded from 3b697badade2298d.jsonl` and made
  **0 new Gemini HTTP calls** (verified by counting requests to
  `generativelanguage.googleapis.com`). Exit code on re-run: 1 (FAIL), matching first run.
- **Hard cap respected:** a `--max-calls 5` run stopped at 5, saved a partial cache, and
  exited 2 (INCOMPLETE); resuming evaluated only the remaining points.
- **Tests:** `pytest tests/unit/test_llm_prompt.py test_llm_eval.py` — **12 passed**
  (8 prompt/parse + 4 cache/cap/resume), Gemini stubbed, no real calls in tests.

### VERDICT: **FAIL** (NO-GO)

### Verdict details
- **LLM hit rate:** 51.7%
- **Baseline hit rate:** 51.6%
- **Edge:** **+0.1 percentage points**
- **Threshold required:** 3.0 percentage points
- **N evaluated (non-HOLD) LLM predictions:** 232 (above the 200 minimum)
- **N overlapping predictions (both non-HOLD):** 232

The LLM cleared the *volume* gates (≥200 points, ≥20 symbols, ≥6 months of days) but
missed the *edge* gate by a wide margin: +0.1pp against a required +3.0pp.

### LLM behavior
- UP: 145 (29.0%) · DOWN: 87 (17.4%) · **HOLD: 268 (53.6%)** · ERROR: 0 (0.0%)
- Mean confidence (UP/DOWN only): 0.66
- The humble prompt did its job: the model abstained on more than half the points. On the
  ~46% where it committed, it was essentially a coin flip relative to momentum.

### Head-to-head (232 points where both predicted)
- LLM correct, baseline wrong: 36
- Baseline correct, LLM wrong: 47
- Both correct: 84 · Both wrong: 65
- Baseline actually won the head-to-head bucket (47 vs 36) — the slim +0.1pp aggregate
  edge comes from the differing denominators, not from the LLM out-picking momentum.

### Per-symbol summary
The full per-symbol table is in
`data/backtest/reports/20260623T223059_thesis_report.md`. The edge is **not** uniformly
distributed — it swings from −57pp (PG) to +54pp (TSLA). Strong-positive names (META
+50, ORCL +47, COST +44, TXN +44, PEP +40, OPEN +38) are offset by strong-negative ones
(PG −57, KO −46, MA −42, SNAP −42, JPM −38, AMZN −39). This looks like sampling variance
on small per-symbol N (most symbols have 2–16 points), not a stable sector signal.

## Recommendation to operator

**Do NOT proceed to T05 without operator review.** The thesis as currently specified —
that a humble, price-history-only LLM prediction beats a momentum baseline by ≥3pp — does
**not** hold on this 2-year, 50-stock, 500-point backtest. The edge is +0.1pp.

Possible interpretations (for the operator to weigh):
1. **The prompt is too restrictive.** A 53.6% HOLD rate means the LLM only commits on
   ~46% of points. A less humble prompt would commit more often, but there's no evidence
   here that its *committed* calls are better than momentum (it lost the head-to-head
   bucket 47–36), so loosening the prompt may just add noise.
2. **The LLM genuinely has no edge from price history alone.** This is the weakest case by
   design — the production system adds news + sentiment + technicals. The architect's
   premise (§T04 prompt) was "if it beats baseline on price alone, news can only help."
   That premise was not met, so the production research bundle would have to carry *all*
   of the signal, which this backtest cannot speak to.
3. **The threshold is too high.** +3pp on next-day direction is demanding. The operator
   may revise it — but +0.1pp is not close under any reasonable threshold.
4. **The universe is wrong.** Edge is dispersed and looks like variance; a different
   universe might or might not change that.

The architecture document (PAPER_TRADER_ARCH_001) and the rest of the build sequence
remain valid; only the thesis needs revision before continuing. The cost of stopping here
is one afternoon and 500 free-tier Gemini calls; the cost of building the full system on a
thesis that shows +0.1pp would be multiple weeks.

## Deviations from spec

1. **Gemini SDK.** The T04 prompt's `llm_eval.py` sketch used the legacy
   `import google.generativeai as genai`. The repo's copied `llm/gemini_client.py` (from
   oracle-agents) uses the **newer `google-genai` SDK** (`from google import genai`). To
   stay consistent with the repo's actual Gemini integration and the SDK that is installed
   and proven working, `backtest/llm_eval.py` uses `google-genai`. Both SDKs are listed in
   `pyproject.toml`. Functionally identical for this use; the response-parsing is robust to
   markdown fences and bad JSON regardless of SDK.
2. **`evaluation.compare()` helper added.** The spec defined `EvaluationResult`,
   `ComparisonResult`, and `evaluate()` but no constructor for `ComparisonResult`. Added a
   `compare(llm, baseline, points)` function that builds the head-to-head buckets and
   `edge_pp`. Pure addition; `evaluate()` matches the spec signature exactly.
3. **`historical_fetch.load_cached()` / `cache_stats()` helpers added.** Not in the T02
   signature list, but the T04 orchestrator needs a network-free cache loader and the CLI
   summary needs a pre-existing-count. Both are read-only and additive.
4. **Sampler day-greedy fill.** To reliably meet the ≥130-distinct-day floor, the sampler
   does a symbol-stratified guarantee pass, then fills remaining slots preferring
   not-yet-covered trading days. Still seed-reproducible. (The naive round-robin in the
   spec sketch clustered on too few distinct days for mid-range sample sizes.)
5. **`sample_hash` is order-sensitive (as specified).** `json.dumps(..., sort_keys=True)`
   sorts dict keys, not the points list, so the hash depends on point order. This is fine
   because `sample_prediction_points` is deterministic for a given seed — the same
   `--seed` + `--n-samples` reproduces the same ordered sample and therefore the same
   cache file.

## Open questions for the reviewer

1. **Is +0.1pp a kill, or a "revise the thesis and re-run"?** Per the architecture's
   Phase-0.5 discipline this is a clear NO-GO at the default +3pp threshold. The decision
   on what to do next (revise prompt / add news context / change universe / kill) is the
   operator's, not Claude Code's.
2. **HOLD handling in the hit rate.** HOLD/ERROR are dropped from the denominator (per the
   spec's `evaluate` docstring). If the operator would rather score HOLD as a half-miss or
   penalize abstention, that's a scoring-policy change to discuss before any re-run.
3. **Per-symbol N is small.** Most symbols have <12 evaluated points, so per-symbol edges
   are noisy. A re-run with more samples per symbol would tighten those, at the cost of
   more Gemini calls.
