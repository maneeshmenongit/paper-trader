# Stage 1 — LLM-Selector Backtest · Gate Report

> **North star:** Does an LLM *choosing which forecasting method to trust* make measurably better trades than cheap alternatives — enough to be worth it — judged on real dollar P&L inside the floor/ceiling band? A NO-GO on evidence is a **successful** test.

## 1. Step 0 — inherited-floor cross-check
- independent recompute $2,110.90 reconciles to inherited $2,110.90

## 2. Dollar table

- Seed bankroll: **$100,000** · universe **30 symbols**, **14,340 points**.
- **Sampled run:** the LLM path ran on a date-stratified sample of **600 points** (4.2% of the universe); the edge/floor/oracle below are measured over those SAME points. All strategies + the trailing scoreboard still saw the full history.

| Strategy | Full-universe P&L (14,340 pts) | Sampled P&L (600 pts) |
|---|---:|---:|
| always_momentum (floor) | $2,110.90 | $556.75 |
| null_selector (real bar) | $2,110.90 | $556.75 |
| random_among_eligible | $5,138.41 | $-112.40 |
| **llm_selector** | — | **$255.58** (382 settled) |
| oracle_best_method (hindsight) | $88,443.33 | — |
| ceiling (perfect foresight) | $116,808.97 | — |
- The verdict/edge below use the **Sampled** column (same points the LLM ran on); the Full-universe column is band context only. Never compare the sampled llm_selector against a full-universe floor.

## 3. LLM edge (over the EFFECTIVE floor)

- Sampled effective floor = max(momentum $556.75, null $556.75) = **$556.75** (over the 600 LLM points).
- **LLM edge: $-301.17** = **-0.301%** of bankroll, over **382 settled LLM points**.
- Headroom captured (edge / (oracle − eff-floor)): **-9.3%**.
- LLM abstention rate: 2.0% (NoView / don't-enter across all points).

## 4. Verdict (Gap C, E = 3.0%)

- **FAILED** — enough points to judge, but the LLM did not even beat the cheap null selector (edge -0.301% < E 3.0%). A 5-line rule captures the available edge; the thesis is not supported. Successful test — do NOT tune the prompt to flip it.

## 5. Sanity + fusion-trap

- Five §4 sanity checks: **ALL PASSED**.
- No-post-decision-data (§2.3): the null selector's trailing scoreboard is fed only by horizons closed **strictly before** each decision date; the LLM feature builder reads only pre-decision closes. Confirmed structurally + in tests.

## 6. Token / call accounting + coverage (§5)

- LLM calls: **0** · cache hits: 600 · tokens: 0.
- LLM-path points (≥2 eligible): 600.
- Diversity: 30 symbols (≥20), 478 dates (≥130), 382 settled (≥100) — **met**.
- Versioned prompt: `stage1-selector-v1` (fixed up front; not tuned).

## 7. Real-math + real-seam (§2.1)

- **Imported, not re-coded:** `analytics.pnl`, `analytics.direction_score`, `settlement.engine.horizon_exit_time`, priced via the fixed `OfflineMarketData` seam. The Stage 1 harness adds no P&L/horizon arithmetic; every strategy settles through the same Stage 0 adapter.

## 8. Carried flags (restated)

- **No-news / Stage-3 Research delta (§2.2):** the backtest is equal-information with NO news/narrative bundle (point-in-time historical news isn't reliably available). Research's contribution is a **known Stage-3 delta**, not part of this verdict.
- **H3 (live hourly-bar default):** a **Stage-3 precondition** — the live R4 path must be reconciled to daily semantics or it will disagree with this backtest.
- **No-crypto gap:** cached data is equities-only; needed before any cross-asset claim at Stage 3.
- **D1:** the Stage 0 live-loop math extraction (analytics/*) was a human-gated amendment; to be logged in the alternatives register.
