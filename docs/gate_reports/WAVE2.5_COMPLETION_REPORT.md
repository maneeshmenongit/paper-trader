# Steward Wave 2.5 — Domain Build Completion Report

**Branch:** `wave2-versioned-skills` (Wave 2 + 2.5 stacked; NOT merged — for review)
**Scope:** The paper-trader domain layer — five agents + supervisor + domain
models + seams — that Waves 3–6 assume exists. Application code under
`src/paper_trader/`; framework (`steward/`) untouched.
**Status:** All nine tasks complete. STOP — Wave 2.5 boundary reached.

---

## Discovery (Task 0)

Found: `enforce_writes` + Agent protocol (real, oracle-agents-frozen), LLM router
seam + live clients + budget, momentum computation (backtest). Absent (built this
wave): CycleState, all domain models, market-data/Clock/trading seams + fakes,
app-db `schema.sql` (was missing — `Database._init_schema` would have failed),
config/registry wiring. No pre-existing agent/supervisor code (stubs only) →
within "build domain models and seams against a scaffolded package." No hard stop.

## Each agent loads its @v1 skill from the registry — confirmed

Every agent is **born registry-loading** (constructed from `load_skill(...)`) and
drives behavior from the loaded content. No inline risk/decision thresholds
anywhere; values are parsed from the loaded skill (`agents/skill_params.py`).

| Agent | Skill | LLM | Key behavior |
|-------|-------|-----|--------------|
| Filter | filter@v1 | zero | R1–R4 + C1–C3; R2 floors ($10M/$50M) + R4 (60min) from skill |
| Research | research@v1 | 1 Groq + 1 Gemini/asset via seam | async fan-out; honest degradation; budget-exhaustion → skip |
| Execute | execute@v1 | zero | Kelly 0.25 / caps / loss-halt / ≥0.55 / ≥0.5% all from skill; symmetric logging; idempotency |
| PostMortem | postmortem@v1 | Groq bias-tags (batched) | measures never reacts; **no Store B seam**; app db only; bias_tags nullable |
| Predict | predict@v1 | zero (momentum) | View/NoView union; rules-first selector |

## Provisional-Predict roster gap (Task 7)

Predict implements **momentum only**. It reads and reports the full declared
roster from the skill:
- **declared:** `momentum, mean_reversion, arima`
- **implemented:** `momentum`
- **unimplemented (reported):** `mean_reversion, arima`

Consequence: with one implemented method, R3 (exactly-one-eligible → rule-select)
is the operative path and **R4 (multiple-eligible → LLM selection) never fires
yet**. Building the rest of the roster + the LLM selector is a deferred step.

## Supervisor / Decision B (Task 8)

Rules-first sequencer; A/C/D/E deterministic if/elif. **Decision B is the
reconciled (demoted) form:** deterministic proceed-to-filter; the always-on
Gemini routing node is NOT built; the LLM-fallback slot is built but DORMANT +
tag-wired (never fires in v1); no in-cycle adaptation (Predict never reads
`recent_post_mortems`). Decision E is DT-5.5 ("any actionable View, direction ≠
HOLD"), not the dead-thesis "any UP"; NoView and the baseline shadow are never
actionable.

## End-to-end cycle result (Task 9)

A full cycle runs with fakes: all five agents load from the registry; Filter →
Research → Predict → Execute (PostMortem via Decision A) executes an actionable UP
View into a paper trade; `persist_cycle` writes predictions / trade_decisions /
paper_trades to the **app db** with DT-8.3 provenance columns populated. Graceful
early-exit verified (market-closed → ends at Decision C). **No Store A/B
emission** anywhere — the loop writes app db + checkpointer only.

## Mirror-contract upgrade result (Task 9)

`tests/test_skill_mirror_contract.py` upgraded from the forward contract to
**value-equality**: the LIVE agents' effective parsed values equal the ratified
skill values (Filter $10M/$50M/60min; Execute Kelly 0.25 / 5% / $100 / 60% / 3 /
10 / >5% / ≥0.55 / ≥0.5%; Predict ≥0.60). Achievable by construction — the agents
carry no inline thresholds, so equality proves the running loop is driven by
exactly the ratified numbers. No `risk_gates.toml` fabricated (the DT-9.1
hard-stop resolution: the agents ARE the baseline, driven by the skills).

## Aggregate tests

**228 passed, 0 failed** (was 147 at Wave 2). ruff + mypy clean across all new
modules. DC-1 boundary green. No network in tests (fakes only). Clock injected
everywhere (no `datetime.now()` in agents).

Commits (branch `wave2-versioned-skills`): `5845df0` T1 · `847e95f` T2 ·
`f62d35e` T3 · `2bc96c4` T4 · `9b0a1df` T5 · `56ccad8` T6 · `51cc2c7` T7 ·
`825f99f` T8 · `90a85e8` T9.

## Deviations & ambiguities

1. **CycleState/predictions built in the RECONCILED shape**, not verbatim
   ARCH_002 §4.1 (View/NoView union per DT-4.5; predictions columns per DT-8.3) —
   the docs' own resolution of their `[v2-FLAG]`. Agreed at Task 1.
2. **`schema.sql` authored** (was missing); `cycle_runs` kept distinct from the
   Store A header (DT-8.4).
3. **Async agents → `agents/enforce.py`** mirrors the frozen sync `base.py`
   (reusing its `ALWAYS_WRITABLE` + `WriteAuthorizationError`) rather than editing
   the oracle-agents-frozen file.
4. **Thresholds parsed from skill PROSE via regex** (`skill_params.py`) — v1
   skills store values in rule text; this is the single seam where a future
   structured-param lookup replaces the regex without changing call sites.
5. **Live data clients (yfinance/Finnhub/CoinGecko) NOT built** — only protocols
   + fakes (+ `LiveClock`). The wave's "fakes only, no network" invariant makes
   untested network clients speculative; seams are complete so they slot in later.
6. **`TradingClient` seam added** (beyond ARCH_002's four protocols) for
   simulated execution + Filter-R2 liquidity.
7. **Kelly sizing is a simplified edge proxy** — the exact continuous-Kelly
   formula isn't specified in the docs; the skill's fraction + position cap are
   consumed correctly, only the interior math is provisional (oracle-agents
   `kelly.py` would slot in).
8. **PostMortem `baseline_pnl` / `predicted_magnitude_pct` are parity
   placeholders** — full baseline comparison needs the settling View threaded
   through `pending_settlements` (settlement-loading, a later wave).
9. **Execute same-sector cap (max 3) parsed but not enforced** — needs sector
   data threaded through positions; value is locked to the skill, predicate is a
   no-op this wave.
10. **"Port oracle-agents test patterns"** — that source isn't in this repo;
    tests written in the same shape (construct state → run → assert mutations).
11. **Registry-path env var `SKILL_REGISTRY_DB_PATH`** added (not yet in
    `.env`/`.env.example`). Store A/B paths deliberately NOT wired (no emission).

No framework code changed. No governance row emitted. No spec amendment required.

## Deferred to Wave 3 (do NOT do until opened)

Full method-selector Predict (mean_reversion, arima, LLM selection); Store A/B
emission (cycle headers, invocation pins, DT-4.x); the officer; wiring Store A/B
paths into config; live data clients; full Kelly/baseline/sector-cap completion.
