"""CLI: Stage 1 FRONTIER CONFIRMATION run (STEWARD_PAPER_TRADER_STAGE1_FRONTIER_CONFIRM_001).

Re-runs Stage 1 changing EXACTLY ONE variable — the predict_selection model → a
strong reasoner (default Sonnet 5) — with everything else pinned byte-identical:
the same 600 sampled points (same seed), the same versioned prompt, the same verdict
rule, floors, adapter, and sanity checks.

Enforces the audit's DT-17 no-silent-downgrade guarantee via the AttestingRouter:
ONE model, no fallback chain, per-call model attestation. If the strong model is
unavailable for any point, the run HALTS (it never quietly drops to a weaker tier),
and the cache makes a quota-driven halt a resumable pause.

Exit codes: 0 on a clean verdict; 2 on INCOMPLETE (cap hit — resume later);
1 on a halt (floor mismatch, sanity violation, model downgrade, or no LLM).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

import pandas as pd

from paper_trader.backtest import historical_fetch
from paper_trader.backtest.attesting_router import AttestingRouter, ModelDowngradeError
from paper_trader.backtest.llm_selector import (
    _SELECTION_SYSTEM_PROMPT,
    LLMSelector,
    LLMUnavailableError,
    SelectorRouter,
)
from paper_trader.backtest.sanity import SanityViolationError
from paper_trader.backtest.stage0_universe import STAGE0_UNIVERSE
from paper_trader.backtest.stage1_harness import (
    _ordered_points,
    run_stage1,
    select_sample,
)

# A SEPARATE cache from the 7B run — frontier results must never mix with 7B ones.
_CACHE_PATH = Path("data/backtest/stage1_frontier_cache.json")


def _prompt_hash() -> str:
    return hashlib.sha256(_SELECTION_SYSTEM_PROMPT.encode()).hexdigest()[:16]


def _floor_crosscheck(history: dict[str, pd.DataFrame]) -> tuple[bool, str]:
    from paper_trader.backtest.methods import MEAN_REVERSION_MIN_HISTORY as HMIN

    notional, total = 1000.0, 0.0
    for sym in sorted(history):
        closes = [float(c) for c in history[sym].sort_index()["Close"].tolist()]
        for i in range(HMIN, len(closes) - 1):
            entry, nxt = closes[i], closes[i + 1]
            if entry > 0 and nxt > 0 and closes[i] > closes[i - 1]:
                total += (notional / entry) * (nxt - entry)
    ok = abs(total - 2110.90) < 1.0
    status = "ok" if ok else "MISMATCH"
    return ok, f"independent recompute ${total:,.2f} vs inherited $2,110.90 ({status})"


def _build_selector(provider: str, model: str, max_calls: int | None) -> LLMSelector | None:
    from paper_trader.live.config import load_live_config
    from paper_trader.llm.budget import TokenBudget
    from paper_trader.llm.model_tiers import build_client

    try:
        config = load_live_config()
        client = build_client(provider, model=model, config=config)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot build {provider}/{model}: {exc}", file=sys.stderr)
        return None

    expected = f"{client.name}/{getattr(client, '_model', model)}"
    router = AttestingRouter(
        client, expected_model=expected, budget=TokenBudget(per_cycle_limit=100_000_000)
    )
    cache = {}
    if _CACHE_PATH.exists():
        cache = {k: tuple(v) for k, v in json.loads(_CACHE_PATH.read_text()).items()}
    sel = LLMSelector(cast(SelectorRouter, router), max_calls=max_calls, cache=cache)
    sel._router_ref = router  # type: ignore[attr-defined]  # for attestation readout
    return sel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1 frontier confirmation run.")
    parser.add_argument("--provider", default="claude")
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--sample", type=int, default=600)
    parser.add_argument("--max-calls", type=int, default=700)
    parser.add_argument("--threshold", type=float, default=0.03)
    parser.add_argument("--bankroll", type=float, default=100_000.0)
    parser.add_argument("--report", help="write the confirmation gate-report markdown here")
    args = parser.parse_args(argv)

    history = historical_fetch.load_cached(STAGE0_UNIVERSE)
    missing = [s for s in STAGE0_UNIVERSE if s not in history]
    if missing:
        print(f"ERROR: {len(missing)} symbols not cached: {missing}", file=sys.stderr)
        return 1

    print(f"prompt hash: {_prompt_hash()} (must match Stage 1's 2bfae227d9790796)")
    ok, crosscheck = _floor_crosscheck(history)
    print(f"Step 0 floor cross-check: {crosscheck}")
    if not ok:
        print("HALT: inherited floor does not reconcile.", file=sys.stderr)
        return 1

    selector = _build_selector(args.provider, args.model, args.max_calls)
    if selector is None:
        return 1
    print(f"frontier model: {args.provider}/{args.model} (single model, no downgrade — DT-17)")

    # Same 600 points, same seed as Stage 1.
    sample_ids = select_sample(_ordered_points(history), target=args.sample)
    print(f"sample: {len(sample_ids)} points (same seed as Stage 1)")

    def _progress(evaluated: int, calls: int) -> None:
        print(f"  ... {evaluated} points, {calls} calls", flush=True)

    try:
        rep = run_stage1(history, selector, seed_bankroll=args.bankroll,
                         threshold_e=args.threshold, sample_llm_points=sample_ids,
                         progress=_progress)
    except SanityViolationError as exc:
        print(f"SANITY VIOLATION: {exc}", file=sys.stderr)
        return 1
    except ModelDowngradeError as exc:
        print(f"HALT (DT-17): {exc}", file=sys.stderr)
        return 1
    except LLMUnavailableError as exc:
        print(f"HALT: {exc} — resume in the next quota window (cache persists).",
              file=sys.stderr)
        # Persist whatever the cache accumulated so the resume is free.
        _persist_cache(selector)
        return 1

    _persist_cache(selector)

    router = selector._router_ref  # type: ignore[attr-defined]
    print(f"\nVERDICT: {rep.verdict}")
    print(f"  floor(momentum) ${rep.floor_momentum_pnl:,.2f} | null ${rep.null_pnl:,.2f} "
          f"| STRONG-llm ${rep.llm_pnl:,.2f} | oracle ${rep.oracle_pnl:,.2f}")
    print(f"  edge {rep.llm_edge_ratio * 100:.3f}% | calls {rep.llm_calls} "
          f"| served by: {sorted(router.served_models)}")

    if args.report:
        from paper_trader.backtest.stage1_frontier_report import write_frontier_report
        write_frontier_report(
            rep, args.report, floor_crosscheck=crosscheck,
            prompt_hash=_prompt_hash(), served_models=sorted(router.served_models),
            model_label=f"{args.provider}/{args.model}",
        )
        print(f"\nconfirmation report written: {args.report}")

    return 2 if rep.verdict == "INCOMPLETE" else 0


def _persist_cache(selector: LLMSelector) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps({k: list(v) for k, v in selector.cache.items()}))


if __name__ == "__main__":
    raise SystemExit(main())
