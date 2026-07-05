# DT-4.2 freeze checklist — config the frozen trace must capture

**Task:** DT-9.2 (Steward Wave 2). **Consumer:** DT-4.2 (Wave 3) — the cycle-header
emission point that freezes `orchestrator_input`.
**Status:** checklist artifact only. Runtime verification (asserting the frozen
trace actually contains these) is **deferred to Wave 3**.

## Why this list exists

Spec §5.1: `orchestrator_input` "must contain everything the decision depended on
and nothing it didn't, or reconstructive replay cannot faithfully reconstruct why
the shape was chosen." Skill *content* is already frozen via the `skill_version_id`
pin (§5.2) + the registry row. This checklist covers the **ungoverned config** the
five @v1 skills operate over — values that are not skill content but that change
what the loop does, so replay needs the in-effect value at cycle time.

Authoritative source for the set: reconcile "Config (ungoverned, frozen into trace
for replay)" line + Appendix A's per-skill config callouts + `.env.example`.

## MUST be frozen into the trace (per cycle)

Capture the value **in effect at cycle start**. These are the replay-load-bearing
config values.

| Value | In-effect source (today) | Which skill(s) operate over it | Notes |
|-------|--------------------------|-------------------------------|-------|
| `watchlist` | `paper_trader/backtest/universe.py` `DEFAULT_UNIVERSE` (operator may override) | Filter (R1–R4 run per entry) | The exact symbol set drives which assets are considered; freeze the resolved list, not a reference to it. |
| `CYCLE_TIME_HORIZON_HOURS` | `.env` (default 24) | Predict (View horizon), PostMortem (settlement timing) | Changes what "settled" means and the forecast horizon. |
| `CYCLE_TOKEN_BUDGET` | `.env` (default 15000) | Research (R3 budget-exhaustion path), Predict/PostMortem LLM calls | Determines when the budget-exhausted branch fires — replay must know the ceiling. |
| Research semaphore bounds | reconcile A.3 / config: **yfinance 2; Finnhub/CoinGecko 4** | Research (fan-out concurrency) | Deliberately config, not skill (G1: politeness limits, not decision rules). Reconcile explicitly says freeze into trace for replay. |
| `calibration_version` | app db `predictions.calibration_version` / calibration_versions table (ARCH_002); v1 = identity calibration | Predict (which calibration the confidence ≥ 0.60 gate is measured against, I-10) | The 0.60 threshold is skill content; the calibration it is applied through is config. Both are needed to reconstruct a View decision. |
| `CYCLE_LOG_LEVEL` | `.env` (default INFO) | (none decision-bearing) | Low-value for decision replay but cheap; include for completeness of "config in effect." |

## MUST NOT be frozen into the trace

| Value | Reason |
|-------|--------|
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `FINNHUB_API_KEY` | Secrets. Freezing credentials into an immutable, append-only replay store is a leak that can never be redacted. The decision does not depend on the key's value, only on the call it authorized — which is captured as the invocation's frozen input/output (§5.2). |
| Store paths (`PAPER_TRADER_DB_PATH`, `CHECKPOINTER_DB_PATH`, and the three governance-store paths) | Environment plumbing, not decision inputs. The trace records *what* was decided, not *where* bytes live. (DC-1: framework opens connections by injected path; the path is not a governance record.) |

## Already frozen by other mechanisms (not this checklist's job)

- **Skill content** (all rules/constraints/thresholds — Filter $10M/$50M, Execute
  Kelly 0.25 etc., Predict ≥0.60): frozen via the `skill_version_id` pin + the
  registry row (G2 content-in-row). Not config; do not duplicate into the freeze.
- **The situation snapshot** (prices, news, indicators the orchestrator saw):
  that is the substance of `orchestrator_input` itself (§5.1), captured by DT-4.2
  directly, not a config value.

## Deferred to Wave 3 (do NOT do here)

- The DT-4.2 emission code that actually freezes these values.
- A runtime test asserting the frozen `orchestrator_input` contains each MUST-freeze
  value and none of the MUST-NOT ones.
- Resolving `watchlist` from a live config seam (today only `DEFAULT_UNIVERSE`
  exists; the operator-override path is a Wave 3 concern).
