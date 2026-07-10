# Thesis Phase Close-Out — Price-Features Method-Selector

**Document ID:** `STEWARD_THESIS_CLOSEOUT_PRICE_SELECTOR_001`
**Date:** 2026-07-08
**Purpose:** Bank the price-features method-selector thesis with a terminal finding and its
evidence, record the decisions and capabilities produced, and hand the research-driven
thesis cleanly to a new thread. Two bounded tasks (§6) execute the close; then this thread
is done.

---

## 1. Terminal finding (the result we are banking)

**On this system, an LLM selecting among price-only forecasting methods (momentum,
mean_reversion, arima) does not produce trades that beat a five-line trailing-performance
rule** — whether the LLM is weak (it over-commits and loses) or strong (it honestly
abstains). Combined with the predecessor forecaster failure, the evidence says
**price-derived information alone carries no confidently-exploitable next-horizon signal
that method-selection can capture.**

This is a **NO on evidence** — a successful test, the outcome the cheap-falsifier discipline
exists to produce. The thesis is **stopped, not paused.**

---

## 2. The evidence chain (why the NO is earned, not inferred)

Four converging results, cheapest first, none tuned to force an outcome:

| Step | What ran | Result |
|---|---|---|
| Predecessor (LLM-as-forecaster) | LLM predicts direction directly (T02–T04) | **FAILED** — +0.1pp vs a +3pp bar; momentum 47 / LLM 36. Essentially a coin flip. |
| Stage 0 (feasibility) | Deterministic oracle over 3 methods, 14,340 points | **GO** — but the 86.3% headroom is a *hindsight* bound (best-of-three, ex-post). It proved headroom *exists*, not that it's reachable. |
| Stage 1 (7B selector) | qwen2.5:7b picks among methods, 600 points | **FAILED** — edge −0.301% over the effective floor; lost to the null rule *and* to random. Over-committed to mean_reversion (69%) and got punished in a rising market. |
| Frontier confirmation (Sonnet 5) | strong reasoner, same frozen prompt/points | **INCONCLUSIVE-by-abstention** — confidence capped 0.45–0.60, abstained on 99.7%. The strong model declined to fake conviction it didn't have. |

The weak model exploited noise and lost; the strong model saw there was nothing to
confidently exploit and stepped back. Together: no price-only signal worth trading.

---

## 3. What this NO does and does NOT say

- **Does say:** price-features-only method-selection doesn't beat a trivial rule on this
  universe, at this (next-horizon) framing, across weak and strong models.
- **Does NOT say:** anything about **research/news-driven** prediction — deliberately scoped
  out of every backtest (point-in-time historical news wasn't available; faking it risked
  look-ahead). That is the one untested lever, and it is the entire premise of the new
  thread.
- **Does NOT test:** dynamic exit timing (everything here exits at a fixed horizon), or
  longer holding horizons. Both belong to the new thread's scope.

The NO is therefore *also* the justification for the new thread: it's the evidence that says
"don't keep mining price; if there's signal, it has to come from research — and at a framing
that isn't fighting market efficiency head-on."

---

## 4. Decisions recorded at close

- **DT-19 — C1 confidence semantics for a selector: recorded as a known limitation, not
  operationally redefined.** The selector inherited the forecaster's C1 gate (directional
  certainty ≥ 0.60); it was never cleanly redefined for a *selector's* confidence. Because
  the thesis is stopped, we do not re-gate. **The lesson carries forward:** any agent that
  reuses a confidence gate must define what that confidence *measures* for its role, up
  front. (You may override and formally rule A/B/split instead — but for a NO it's recorded,
  not re-run.)
- **D1 — analytics extraction:** the Stage 0 extraction of `analytics/pnl.py` +
  `analytics/direction_score.py` from `postmortem.py` (behavior-neutral, human-gated) is a
  recorded spec amendment; authority docs read "extract to," not "import from."

---

## 5. Assets banked (reusable by the new thread)

Closing this thread is not a loss — it banks a working instrument:

- The **real-math scoring path** (`analytics/pnl`, `analytics/direction_score`, settlement
  horizon logic) on the fixed `data/offline.py` seam — the single scoring path, bug-hunted.
- The **backtest harness** (fixed universe, point sampling, dollar table, floor/ceiling,
  five sanity assertions) — a disconfirmation engine ready to point at a new thesis.
- **Tiered model routing** (`llm/model_tiers.py`, `build_tiered_router`) — fast vs reasoning
  per purpose.
- **`ClaudeClient`** — the framework's Anthropic client.
- **`AttestingRouter` (DT-17)** — halt-not-silent-downgrade with per-point model attestation.
  **Caveat carried:** it was exercised only over cache this run; its live halt must be
  **fired once for real** before it's trusted in the new thread.

Log the three capabilities (tiered router, ClaudeClient, AttestingRouter) in the
alternatives register as ratified additive framework surface.

---

## 6. The two bounded tasks that execute the close

**Task A — fix the reporting defects, then unblock merge (Claude Code).**
Both are the same class (numbers narrated instead of emitted deterministically):
- **Frontier gate report:** thread `served_models` through the cache layer so attestation
  works on cached replays; regenerate the report; confirm which pass is authoritative and
  that the Sonnet-5 numbers stand. Resolve the `served_models: []` / "MORE THAN ONE MODEL"
  contradiction against the completion report's `{claude/claude-sonnet-5}`.
- **Stage 1 gate report:** relabel every row consistently as full-universe (14,340) vs
  sampled (600); fix the `max($2,110.90, $2,110.90) = $556.75` line to read "sampled floor
  = $556.75"; clarify whether `random`'s $5,138.41 is sampled or full.
- **Adopt the rule:** number-bearing report output is emitted by the harness/report writer,
  never re-narrated by a model (prose *around* the numbers is fine).
- Verify tests green; the verdicts (Stage 1 FAILED, frontier INCONCLUSIVE-by-abstention) are
  unchanged by relabeling.

**Task B — records + terminal finding + merge (Claude Code).**
- Commit this close-out record and its terminal finding to the repo.
- Log DT-19 and D1 (§4) and the three capabilities (§5) in the alternatives register.
- Update authority docs where they still say "import from" → "extract to."
- Merge `postv1-stage1-llm-selector` and `postv1-stage1-frontier-confirm` to main.
- Confirm main is green and the thesis flag reads **STOPPED (price-features), NO on
  evidence** — not UNVALIDATED (it is now tested), not VALIDATED.

---

## 7. Carry-forward to the research-driven thread (do NOT lose these)

- **The premise:** research/news-driven prediction is the untested lever (§3); the new
  thread owns it end-to-end. This thread does not chase it at a Stage 3.
- **The second decision:** "when to pull out" is a *dynamic exit* problem the current
  fixed-horizon system has never modelled — potentially two predictions (enter, and exit),
  not one. Name it in the new kickoff.
- **The efficiency wall:** "LLM analyst predicts the next move from public news" is the
  hardest framing (public info is already priced in). The new thread needs disconfirmation-
  first discipline and a horizon/framing that isn't fighting efficiency head-on (longer
  holds, or regime/quality identification, rather than next-day direction).
- **AttestingRouter live-fire** before trust (§5 caveat).
- **Still-open engineering preconditions** if the new thread ever goes live: **H3** (live
  hourly-bar default vs daily backtest), **no-crypto** in cached data, and completion of the
  **purpose→tier map** (audit DT-18) for the officer/proposer.

---

## 8. Terminal state of this thread

After Tasks A and B: the price-features method-selector thesis is closed with a durable NO,
the reporting defects are fixed, the branches are merged, the decisions and capabilities are
on the record, and the reusable instrument is banked. This thread is done. The next action
is a fresh thread with a research-driven redefinition kickoff.
