# Code Review Improvements Register — 001

**Date:** 2026-07-08
**Reviewer:** Fable 5 (four parallel read-only reviews)
**Scope:** ~8,000 LOC across `src/steward/` (framework), `src/paper_trader/` (application), and `scripts/run_live.py`.
**Status:** findings only — **no code was changed**. This is a punch-list, not a change record.

---

## How to read this

Findings are grouped by severity and each carries a stable ID (`C#`/`H#`/`M#`/`L#`) so
they can be referenced from commits and gate reports. Each entry names the
**file:line**, the **defect**, and a **fix**. Where the same defect was flagged by more
than one reviewer, the entry says so.

Nothing here contradicts the project's discipline — the one-way import rule holds, Store
A/B are genuinely append-only (DB triggers back it), the six stores are cleanly
separated, and secrets are contained on the happy path. The findings cluster in three
themes:

1. **Crash / error isolation** in the long-running scheduled loop.
2. **Cash / equity accounting** consistency.
3. **Units drift** — hourly vs daily bars — the likely root of the T6b zero-trade finding.

---

## Top three actions (do these first)

| # | Finding | Why first |
|---|---------|-----------|
| 1 | **C1** — per-cycle error isolation + settlement recovery sweep | One flaky quote currently strands settled-but-unscored trades *and* kills the run |
| 2 | **H1** — fix the cash/equity model | Every risk number (Kelly, caps, loss halt, frozen equity) depends on it |
| 3 | **H3** — daily (not hourly) momentum & liquidity | Probable root cause of the documented zero-trade live run |

---

## Critical

### C1 — An agent exception aborts the cycle *after* settlement has irreversibly closed trades
*Flagged independently by 3 of 4 reviewers.*

Settlement marks trades `exited=1` at the **start** of a cycle
(`settlement/engine.py:74-78` → `repo.mark_trade_settled`); the hit/miss + P&L rows are
only written at the **end**, in `persist_cycle` (`harness/runner.py:117-141`). But three
agents have unguarded `await`s and neither `Supervisor.run_cycle`
(`graph/supervisor.py:88-103`) nor the runner's cycle loop (`harness/runner.py:102-111`)
has a `try/except`:

- `agents/filter.py:74,83` — `get_liquidity_metric` / `get_ohlcv`
- `agents/execute.py:86` — `_size_and_fill` (also `ZeroDivisionError` if fill price is 0)
- `agents/postmortem.py:84` — legacy `get_current_quote` fallback

A single live-provider failure unwinds the whole cycle: no Store A trace, no
`persist_cycle`, no portfolio update — while the DB already says the trades are closed.
`open_trades_due` never returns them again, so their P&L and post-mortems are lost
forever, and the scheduled run dies.

**Fix:**
- (a) Per-cycle `try/except Exception: logger.exception(...); continue` in `ScheduledRunner.run`, recording a failed-cycle record.
- (b) Per-asset guards in Filter/Execute/PostMortem (mirror Research's `skip_reasons` pattern).
- (c) Startup **recovery sweep**: `paper_trades WHERE exited=1` with no matching `post_mortems` row → re-score from the stored `exit_price` (all data is persisted). Makes settlement idempotent.
- (d) Ideally make *scoring persisted*, not `mark_trade_settled`, the point of no return (settle + score in one transaction).

### C2 — Finnhub API key can leak into the immutable Store A trace
The finnhub SDK sends the key as a **URL query parameter**, so any transport error
carries `&token=<KEY>` in its message. The chain:

1. `data/live/finnhub_client.py:59` — SDK raises; `retry_with_backoff` re-raises verbatim.
2. `agents/research.py:75` — `skips[sym] = f"research_failed: {exc}"` stringifies it.
3. `graph/emit_boundary.py:56` → `emission.py:79` — frozen into **append-only** Store A.

`freeze.py`'s key-scrub strips dict *keys*, not secrets embedded in message strings.
Because Store A rows are never UPDATE/DELETE, one connection error permanently embeds the
key.

**Fix:** wrap SDK exceptions in a sanitized domain error at the client boundary
(`raise CompanyNewsError(f"finnhub {type(e).__name__}: status={getattr(e,'status_code','?')}") from e`);
belt-and-braces, redact `token=...` at the emission boundary.

---

## High

### H1 — Cash is never debited at entry, so equity is inflated by every open position
`ExecuteAgent._equity` (`agents/execute.py:146-148`) = `cash + Σ open notional`, but
nothing subtracts notional from cash when a trade opens (Execute writes trades only; the
runner appends Positions without touching cash; PostMortem adds only the P&L delta at
close). So $100k cash + a $5k position → equity $105k. Every consumer is wrong while
positions are open: Kelly sizing (execute.py:117-124), `max_position_pct`,
`_exposure_after` (execute.py:150-154), `_daily_loss_breached` (execute.py:156-159), and
the `frozen_equity` in Store A (execute.py:65).

**Fix:** pick one model — debit cash by notional at entry (credit notional+P&L at
settlement), **or** define `_equity = cash_balance` under the current "cash never spent"
convention — and make all four consumers consistent.

### H2 — The "daily" loss halt gates on *lifetime* cumulative P&L
`_daily_loss_breached` (`agents/execute.py:156-159`) uses `portfolio.realized_pnl`, a
running total for the whole run (carried across cycles). Weeks of small losses trip a
permanent halt; old gains mask a bad day. The skill says *daily*.

**Fix:** track P&L per UTC trading day (reset at day rollover from the injected Clock, or
query `post_mortems WHERE created_at >= today`).

### H3 — Momentum & liquidity computed on hourly bars but designed for daily ones
*Likely root cause of the T6b zero-trade run.*

`YFinanceMarketData` defaults to `interval="1h"` (`data/live/yfinance_client.py:76,84`),
so:
- **Predict** (`predict.py:133`) measures the last *hourly* move vs the previous bar, though the comment (predict.py:32-34) intends two prior *daily* closes. The 0.60 confidence gate needs a 0.5% move — routine per day, rare per hour → nearly every cycle is `below_confidence_threshold`.
- **Liquidity** (`live/trading.py` `get_liquidity_metric`) averages `close*volume` over hourly bars but is ratified as *daily* dollar volume → the $10M floor becomes ~$70M daily for stocks (~24× off for crypto). Real names rejected as illiquid.
- **RSI-14 / SMA-cross** (`research.py`) become 14-*hour* / hourly-bar indicators, while every test fixture uses one bar/day.

**Fix:** fix the *semantics*, not the threshold — aggregate to daily closes (group bundle
bars by `timestamp.date()`, take last close per day), or add a dedicated `interval="1d"`
path for these calls. Don't loosen 0.60.

### H4 — The "per-cycle" token budget is actually per-process
`scripts/run_live.py:93` builds `TokenBudget(per_cycle_limit=...)` once; the router holds
it forever; **`budget.reset()` is never called** (zero call sites). A `--cycles 24` run
accumulates usage; once the limit is crossed, every later cycle hits
`BudgetExhaustedError`, sets `state.budget_exhausted`, and trades "dumber" for the rest of
its life — contradicting the per-cycle promise in `llm/budget.py`.

**Fix:** `self.llm_router.budget.reset()` at the top of `_run_one_cycle`
(`harness/runner.py:115`), or build a fresh budget/router per cycle.

### H5 — Portfolio positions removed by symbol, not trade identity
`_apply_settlements` (`harness/runner.py:171-179`) drops every position whose symbol is in
the settled set. With a 24h horizon and shorter intervals the same symbol is re-traded;
when the older trade settles, *both* positions vanish from the carried portfolio while the
DB still holds the younger one open. Cash/exposure accounting drifts for the rest of the
run.

**Fix:** track positions by trade id (add `paper_trades.id` to `Position`, or key
removals on `(symbol, entry_time)`).

### H6 — No exit-price sanity check on settlement
`engine.py:70-76` accepts any successful `get_current_quote`. yfinance can return
`0.0`/NaN on partial outages; settling at 0.0 books −100% P&L into a row the `exited=0`
guard (`repository.py:177`) makes un-re-settleable.

**Fix:** `if not (exit_price and exit_price > 0 and math.isfinite(exit_price)): continue`
— same retry-next-pass semantics as the exception path.

### H7 — Budget can be bypassed (tokens=0) and can overshoot (prompt tokens)
- **Bypass:** `groq_client.py:60` / `gemini_client.py:72-74` return `tokens=0` when the provider omits usage metadata → `budget.consume(0)` → unlimited free calls. Fall back to a conservative `max_tokens` estimate.
- **Overshoot:** the pre-call check reserves only `max_tokens` (`configurable_router.py:71`) but `consume()` books prompt+completion. Estimate prompt tokens in `has_capacity`, or document the budget as completion-only and consume consistently.

### H8 — `max_same_sector` parsed from the ratified skill but never enforced
`ExecuteParams.max_same_sector` (`agents/skill_params.py:87`) is extracted but no code in
`execute.py` reads it. A ratified constraint silently unenforced is exactly the drift the
governance layer exists to catch — but no predicate covers it, so the observer can't flag
it.

**Fix:** enforce it (Asset carries `sector`; count open + this-cycle per sector), **or**
record the deferral as a loud spec amendment and drop it from `ExecuteParams` so the
mirror-contract doesn't imply enforcement.

### H9 — Observer swallows every exception into an in-memory list
`officer/observer.py:100-112` catches **all** exceptions, appends to `self.failed` (dies
with the process despite the "durable" comment), and returns `[]`. This silently swallows
`UnregisteredPredicateError` (documented as a loud *build error*, `predicates.py:8-9`) and
`SkillIntegrityError`. An un-observed cycle is indistinguishable in replay from
"meaningful silence" (`replay.py:256`) — inverting the meaning of silence.

**Fix:** emit an `observer-failure` Store B entry via the existing writer; wrap
per-invocation (not per-cycle); either persist `failed` or drop the "durable" claim.

### H10 — `seed_skills.py` is application content inside the framework (DC-1 leak)
`storage/seed_skills.py:27-38` hardcodes `APPLICATION_ID = "paper-trader"`, the five agent
names, Predict's thesis prose, and `SKILLS_DIR = ...parents[3]/"docs"/...` — which only
lands on the repo root in a `src/` checkout and points at garbage under `site-packages`.
This is the one real DC-1 leak and the first thing a second app trips over.

**Fix:** move to `paper_trader/`, or parameterize
`seed_v1_skills(registry, *, application_id, agents, skills_dir, created_at)` and keep only
the mechanism in `steward/`.

### H11 — Registry SQLite connection leaked once per cycle
`harness/assembly.py:126-129` opens a raw `sqlite3.connect(registry.path)` for the
Observer every cycle (`build_governed_cycle` runs per cycle) and never closes it — one fd
+ one handle leaked per cycle over a multi-week run. Also opened read-write when the
config contract says the registry is read-only.

**Fix:** open it `mode=ro`, and close it after the cycle (or cache one for the runner's
lifetime).

### H12 — Restart resets the portfolio to $100k while the DB holds open trades
`harness/runner.py:96-97` (acknowledged deferred). After a restart, open DB trades are
absent from the carried portfolio: caps compute against an empty book and cash is
double-counted. `paper_trades` already holds everything needed to rehydrate at boot.

**Fix:** rehydrate open positions + derive cash at startup.

### H13 — Proposer evidence-gathering matches by unescaped substring `LIKE`
`officer/proposer.py:53-57` — `subject LIKE '%{target_skill}%'`. `filter` matches
`prefilter`; `execute` matches `execute2`; `%`/`_` unescaped. These rows become the
`evidence_refs` of cite-never-assert proposals, so over-match is a correctness bug.

**Fix:** promote `agent_name`/`skill_version_id` to explicit `Divergence` fields and match
with a prefix anchor + `ESCAPE` (e.g. `target_skill + '@%'`).

### H14 — Exposure cap breachable within one cycle; `min_notional` overrides the position cap
`agents/execute.py:150-154` — `_exposure_after` reads only committed
`open_positions`, so multiple UP views in one loop each see the same stale exposure and
total can exceed `max_total_exposure_pct`. Separately, `notional = max(min(kelly, cap),
min_notional)` (execute.py:124) lets `min_notional` beat the cap when equity is small.

**Fix:** accumulate `cycle_notional` and add to `current`; if `min(kelly, cap) <
min_notional`, reject with `below_min_notional` rather than forcing the size up.

---

## Medium

- **M1** — `persist_cycle` is not transactional (`persistence/cycle_writer.py:17-99` makes ~4N separate committed connections). A crash mid-persist leaves torn history. Add a `Repository.transaction()` context and route through it.
- **M2** — No `busy_timeout`/WAL on the app db (`persistence/db.py:31-33`). Running `summarize_run` while the harness writes → `database is locked` → (via C1) kills the run. Add `PRAGMA busy_timeout=5000`, consider WAL. (db.py says "do not edit independently" — file the sync upstream.)
- **M3** — Malformed JSON from Ollama/OpenRouter (`ollama_client.py:75`, `openrouter_client.py:69`) raises `JSONDecodeError`, caught by neither handler and not in `_FAILOVER_ERRORS` → defeats the whole fallback chain. Move `.json()` under `except (httpx.HTTPError, ValueError)`.
- **M4** — Proposal transitions have a TOCTOU window (`proposals.py:146-175`, `gate.py:91,124`) — validate-then-UPDATE-unconditionally lets two sessions double-decide. Use `UPDATE ... WHERE proposal_id=? AND status=?` + `rowcount==0` check. This is the one mutable governance record; guard it hardest.
- **M5** — Bias tags smeared across the batch (`agents/postmortem.py:144-158`): one parsed tag list assigned to all 4 trades → mislabeled attribution in durable history. Ask for per-trade lines and parse per id.
- **M6** — Input tokens unbounded: Research passes `str(news)` (raw repr of ≤30 days of NewsItems) as the prompt (`research.py:91-104`); budget only counts the output estimate. Truncate to top-K headlines, format explicitly.
- **M7** — `retry_with_backoff` retries everything incl. non-retryable (`retry.py:40` default `(Exception,)`): 401s, delisted symbols, CoinGecko 404s all get 3 attempts. No jitter, no `Retry-After`. Pass per-client `retry_on` tuples.
- **M8** — `StoreConnections` omits `proposals.sqlite` (validates 5 of 6 paths) and is unused in production — the never-co-mingled invariant is enforced nowhere at runtime. Add the path and wire it, or delete the class.
- **M9** — Observer `entry_id = f"{cycle_id}:obs:{seq:03d}"` minted per-emit in its own transaction (`observer.py:154-156`) — partial emission is permanent (re-observation hits the PK), and two observers collide. Seed `seq` from `max(entry_id)` or accept injected ids.
- **M10** — Late settlement silently prices at "now", not the horizon (`engine.py:62,70`): a 4-day-late 24h trade scores the 24h forecast against a 4-day move. Record a `settled_late` flag / the gap; for stocks, a historical-close lookup at the horizon is more faithful.
- **M11** — Research fetches news `since=now` → today-only window (`research.py:86` → `finnhub_client.py:57-58`); just after 00:00 UTC it's empty. Use `now - timedelta(days=N)`.
- **M12** — HOLD baseline shadows scored as long (`postmortem.py:139`): magnitude 0 → `+1` sign → "earns" the full move; should be 0. Latent today, live in the thesis phase. Thread baseline `direction` through `SettlementContext`.
- **M13** — `state.errors` never written → `cycle_status` "partial"/"failed" unreachable (`graph/freeze.py:73-75`). Have Research/Filter append to `errors` on per-asset exceptions.
- **M14** — Emission-neutrality gaps in the wrapper: `frozen_facts()` (`emit_boundary.py:50-54`) and header-arg construction (`supervisor.py:108-121`) run outside any try. Pure/safe today by inspection; make the "camera never breaks the film" guarantee structural.
- **M15** — Budget exhaustion ends the cycle before Predict (`graph/decisions.py:54` → `"end"`), discarding paid-for research — yet Predict (momentum) and Execute make zero LLM calls. Proceed to `predict` and degrade only LLM-dependent work (or record the spec amendment).
- **M16** — Wall-clock reads inside `FinnhubCompanyNews` (`finnhub_client.py:52,79`) bypass the clock seam; the `now()` fallback makes undated items look maximally fresh. Inject a `Clock`.
- **M17** — Fake↔live contract drift: fakes emit daily bars, live emits hourly (see H3); `FakeCompanyNews` returns exact items, live filters only at date granularity. Make granularity part of the `MarketDataProvider` contract; post-filter `published_at >= since`.
- **M18** — No NaN handling in `_frame_to_bars` (`yfinance_client.py:170-179`) — NaN rows poison liquidity/RSI/momentum. `dropna(subset=[...])` before slicing.
- **M19** — Shared blocking `requests.Session` across `to_thread` threads (`finnhub_client.py:58`, `coingecko_client.py:81`) under a semaphore of 4 — `requests.Session` isn't documented thread-safe. Session-per-call or lock.
- **M20** — `llm_provider` config not validated (`providers.py:123`): anything but `"openrouter"` (incl. `"hosted"`, typos) silently becomes Ollama. Validate against an enum in `load_live_config`.
- **M21** — `data/news.py` is dead code carrying live bugs (stale `NewsItem` stub; `mktime` UTC-as-local timezone bug; no feedparser timeout; `now()` date fallback). Delete or move out of the package until a consumer exists.
- **M22** — Ordering by `invocation_id` is an undocumented app contract (`observer.py:175`, `replay.py:114-116`) — chronological only because paper_trader mints ULID-prefixed ids; a uuid4 app gets random order. `ORDER BY started_at, invocation_id` or document the requirement.
- **M23** — Gate policy constants are trading vocabulary compiled into the framework (`gate.py:26-28`); a second app can't change window policy without editing framework source. Inject via constructor.
- **M24** — Predict trusts provider bar ordering (`predict.py:121-122` uses `[-2],[-1]`); an unsorted frame flips the momentum sign. Sort by timestamp in `_closes`.
- **M25** — `_entry_price` 100.0 fallback (`execute.py:161-173`) can price a real paper trade at a fabricated constant. Reject with `no_entry_price` instead.
- **M26** — Late/dead `Repository` methods: `insert_post_mortem` (`repository.py:210-227`, zero callers, would write a predictions-id into a paper_trades FK), `count_trade_decisions_for_prediction` (test-only), and the never-written `cycle_runs` table (`schema.sql:86-97`). Delete or wire up — writing `cycle_runs` would anchor C1's sweep and M1's torn-persist detection.
- **M27** — Relative default store paths (`config.py:28-40` `./data/*.sqlite`, `live/config.py:33`) make the process cwd-dependent — launching elsewhere silently creates fresh empty stores. Anchor to a project root or log resolved absolute paths at boot.
- **M28** — Schema has no migration story (`db.py:24-27` replays `CREATE TABLE IF NOT EXISTS`; new *columns* never apply to a live DB, no `user_version`). Add a `user_version` check that fails loudly on drift.
- **M29** — `config = cfg` (with secrets) stored on the runner (`runner.py:79`) but never read. Drop it; add `field(repr=False)` to the key fields in `live/config.py` regardless.
- **M30** — `officer_predicates._predict_threshold` regex only matches Unicode `≥` (`officer_predicates.py:276-283`); ASCII `>=` silently falls back to hardcoded 0.60 — a silent bend of "skill content drives thresholds". Match `(?:≥|>=)`.

---

## Low & Nits

Worth a pass when you next touch the relevant file; none block operation.

- **Scheduling drift** — the loop sleeps a fixed interval *after* cycle work (`runner.py:110-111`), so the true period is `interval + cycle_duration`. Compute next-fire as `start + i*interval`.
- **Sync LLM calls block the event loop** — all four clients are sync, called from async agents (`research.py:91,103`; `postmortem.py:146-147`); `timeout=120s` stalls settlement/logging. Wrap in `asyncio.to_thread`.
- **`LiveClock.is_market_open` is weekday-only / UTC-weekday** (`data/clock.py:21-27`) — admits pre-market and weekend bars. Prioritize now that operation is live.
- **`asserts` for validation** disappear under `python -O` — `engine.py:113,117`, `postmortem`, others. Raise `TypeError`.
- **LONG-only settlement semantics hardcoded** (`engine.py:81`, `postmortem.py:87` `direction_correct = exit >= entry`) — silent bugs the day SHORT/DOWN arrives. Select & score off `direction` now.
- **`-0.0` sign bug** in the baseline shadow (`repository.py:155-156`, `postmortem.py:139`) — DOWN with magnitude 0 → `-0.0` → treated as UP. Carry direction explicitly.
- **Substring error classification** — `"rate" in str(e).lower()` (`groq_client.py:55`, `gemini_client.py:58`) matches "gene**rate**". Use typed exceptions / status codes.
- **`get_current_quote` falsy-chain** (`yfinance_client.py:113-117`) — `or` treats a legit `0.0` price as missing. Use `is not None`.
- **Intraday period cap** `"1mo"` (`yfinance_client.py:44`) invalid for `1m`/`2m` intervals.
- **CoinGecko id guessing** falls back to `symbol.lower()` (`coingecko_client.py:72`) → 404s retried 3×; deprecated `MATIC` id. Fail-fast on unmapped symbols.
- **No jitter in backoff** (`retry.py:65`) — synchronized retries re-spike a rate-limited provider.
- **Over-broad write authorization** — `ExecuteAgent.writes` includes `"portfolio"` (`execute.py:29`) though Execute never writes it.
- **`summary.py`** counts distinct cycle_ids in `paper_trades` (`summary.py:43`), so zero-trade cycles (the T6b headline!) aren't counted; `all_pins_verified` (65-67) string-matches replay prose. Read structured findings instead.
- **Four `model_dump()`s per invocation** (`enforce.py:31-33`, `emit_boundary.py:29-31`) — measurable with 30-day OHLCV bundles. Dump once, share; dump only needed fields.
- **Store A `agent_input` is the write-set, not what was read** (`emit_boundary.py:38`) — Predict's recorded input omits its true input (`research_bundles`). Add a `reads` declaration.
- **`_volume_trend` / `_sma_cross`** tie-handling biases (`research.py:153,160-163`).
- **Idempotency guards inert** — `if symbol in decisions` (`execute.py:79-81`) can never fire; `count_trade_decisions_for_prediction` unused.
- **Dead framework code** — `lifecycle.execute_transition` (raises `NotImplementedError` on every path), `AgentPredicate` Protocol (unused), `approve()` step (c) no-op try/except (`gate.py:150-162`), forbidden-key `pop` in `freeze.py:60-64`.
- **Constant/comment drift** — `OFFICER_AUTHOR`/`OBSERVER_IDENTITY` duplicated; `gate.py:90` comment contradicts `LEGAL_TRANSITIONS`; `connections.py:1` "Four-store" title; `watchlist.py:58` error message; `historical_fetch.py:33` unused `symbol` param; `providers.py:119` dead conditional.
- **`_ro_connect` URI not percent-encoded** (`replay.py:42-47`); missing-file/WAL errors surface as a bare "unable to open database file". Wrap with context.
- **Committed `__pycache__` artifacts** under the packages — verify they're gitignored.
- **backtest NaN handling** (`sample.py:33-48`) — NaN close → `actual_direction="DOWN"`, NaN magnitude pollutes ground truth. Filter NaN rows.

---

## What's solid (keep as-is)

- **Boundaries hold** — zero `paper_trader` imports under `src/steward/` (only the conceptual `seed_skills.py` leak, H10). Append-only is clean: the only framework UPDATEs touch the two legitimately-mutable records; triggers + insert-only surfaces agree across all three immutable tables.
- **Store separation is real** — settlement/persistence touch only `paper_trader.sqlite`; `config.py` gives each of six stores its own env var + path + opener; observability opens Store A/B strictly `mode=ro`; nothing in the ops layer writes Store B.
- **Secrets hygiene on the happy path** — `LiveConfig` is the single env read-point, `redacted()` used at the log site, `field`-level auth headers keep keys out of logs (C2 is the one exception path).
- **Emission is genuinely non-throwing and never feeds back into decisions** — no path found where emission alters a trading decision.
- **`mark_trade_settled`'s `WHERE exited=0` guard** makes double-settlement of a row impossible; settle-before-cycle ordering prevents trading against a stale position list.
- **The `_baseline_pnl` fix** (scoring the shadow by realized move, not predicted magnitude) is correct, and its memorializing comment is exactly the right kind of note.
- **The fork is genuinely atomic** (single-file transaction, `skill_version.py:150-199`).
