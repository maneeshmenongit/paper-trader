"""CLI: python scripts/run_stage1.py [--max-calls N] [--threshold E] [--report PATH]

Runs the Stage 1 LLM-selector backtest over the frozen Stage 0 universe. Requires a
configured LLM (Ollama primary, or cloud fallback keys) — the selector routes the
`predict_selection` purpose at the STRONGER model first (§4.B). Caches selection
calls to disk so re-runs are free.

Exit codes: 0 on a clean verdict (SUCCEEDED / FAILED / INCONCLUSIVE are ALL
successful outcomes); 2 on INCOMPLETE (cap hit); 1 on a halt (floor mismatch,
sanity violation, or no LLM configured).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

import pandas as pd

from paper_trader.backtest import historical_fetch
from paper_trader.backtest.llm_selector import (
    PREDICT_SELECTION_PURPOSE,
    LLMSelector,
    LLMUnavailableError,
    SelectorRouter,
)
from paper_trader.backtest.sanity import SanityViolationError
from paper_trader.backtest.stage0_universe import STAGE0_UNIVERSE
from paper_trader.backtest.stage1_gate_report import write_gate_report
from paper_trader.backtest.stage1_harness import run_stage1

_CACHE_PATH = Path("data/backtest/stage1_selection_cache.json")


def _floor_crosscheck(history: dict[str, pd.DataFrame]) -> tuple[bool, str]:
    """Independent recompute of always-momentum P&L (§3). No harness/adapter."""
    from paper_trader.backtest.methods import MEAN_REVERSION_MIN_HISTORY as HMIN

    notional, total = 1000.0, 0.0
    for sym in sorted(history):
        closes = [float(c) for c in history[sym].sort_index()["Close"].tolist()]
        for i in range(HMIN, len(closes) - 1):
            entry, nxt = closes[i], closes[i + 1]
            if entry > 0 and nxt > 0 and closes[i] > closes[i - 1]:
                total += (notional / entry) * (nxt - entry)
    inherited = 2110.90
    ok = abs(total - inherited) < 1.0
    msg = (
        f"independent recompute ${total:,.2f} "
        f"{'reconciles to' if ok else 'DOES NOT reconcile to'} inherited ${inherited:,.2f}"
    )
    return ok, msg


def _build_selector(max_calls: int | None) -> LLMSelector | None:
    """Build an LLMSelector wired to the strongest configured provider, or None."""
    from paper_trader.live.config import load_live_config
    from paper_trader.live.providers import build_llm_router
    from paper_trader.llm.budget import TokenBudget

    try:
        config = load_live_config()
        # A generous budget — the --max-calls cap is the real governor here.
        router = build_llm_router(config, TokenBudget(per_cycle_limit=10_000_000))
    except Exception as exc:  # noqa: BLE001 — no provider configured is a clean halt
        print(f"no LLM provider configured: {exc}", file=sys.stderr)
        return None

    # §4.B: point predict_selection at the STRONGER model first. The fallback chain
    # (cloud) leads if present; else the primary. We prepend a route explicitly.
    stronger_first = list(reversed(router.default)) if len(router.default) > 1 else router.default
    router.routes[PREDICT_SELECTION_PURPOSE] = stronger_first  # type: ignore[index]

    cache = {}
    if _CACHE_PATH.exists():
        cache = {k: tuple(v) for k, v in json.loads(_CACHE_PATH.read_text()).items()}
    # The router's `call` types `purpose` as the frozen LLMPurpose Literal; the
    # selector seam types it as `str` (it uses the unmapped `predict_selection`
    # purpose). Runtime-compatible; cast bridges the Literal-vs-str variance without
    # editing the frozen oracle-provenance interface.
    return LLMSelector(cast(SelectorRouter, router), max_calls=max_calls, cache=cache)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Stage 1 LLM-selector backtest.")
    parser.add_argument("--max-calls", type=int, default=2000)
    parser.add_argument("--threshold", type=float, default=0.03)
    parser.add_argument("--bankroll", type=float, default=100_000.0)
    parser.add_argument("--report", help="write the gate-report markdown here")
    args = parser.parse_args(argv)

    history = historical_fetch.load_cached(STAGE0_UNIVERSE)
    missing = [s for s in STAGE0_UNIVERSE if s not in history]
    if missing:
        print(f"ERROR: {len(missing)} symbols not cached: {missing}", file=sys.stderr)
        return 1

    ok, crosscheck = _floor_crosscheck(history)
    print(f"Step 0 floor cross-check: {crosscheck}")
    if not ok:
        print("HALT: inherited floor does not reconcile — GO is suspect.", file=sys.stderr)
        return 1

    selector = _build_selector(args.max_calls)
    if selector is None:
        print("HALT: Stage 1 needs a configured LLM. Set up Ollama or cloud keys.",
              file=sys.stderr)
        return 1

    try:
        rep = run_stage1(history, selector, seed_bankroll=args.bankroll,
                         threshold_e=args.threshold)
    except SanityViolationError as exc:
        print(f"SANITY VIOLATION — run not trustworthy: {exc}", file=sys.stderr)
        return 1
    except LLMUnavailableError as exc:
        print(f"HALT: {exc}", file=sys.stderr)
        print("The configured LLM is unreachable. Start Ollama (`ollama serve` + "
              "`ollama pull <model>`) or add a cloud key, then re-run.", file=sys.stderr)
        return 1

    # Persist the selection cache for free re-runs.
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps({k: list(v) for k, v in selector.cache.items()}))

    print(f"\nVERDICT: {rep.verdict}")
    print(f"  floor(momentum) ${rep.floor_momentum_pnl:,.2f} | null ${rep.null_pnl:,.2f} "
          f"| llm ${rep.llm_pnl:,.2f} | oracle ${rep.oracle_pnl:,.2f}")
    print(f"  LLM edge {rep.llm_edge_ratio * 100:.3f}% over eff-floor "
          f"${rep.effective_floor_pnl:,.2f}; calls {rep.llm_calls}, settled {rep.llm_settled}")

    if args.report:
        write_gate_report(rep, args.report, floor_crosscheck=crosscheck)
        print(f"\ngate report written: {args.report}")

    return 2 if rep.verdict == "INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
