"""CLI: python scripts/run_stage0.py [--threshold E] [--bankroll N] [--report PATH]

Runs the Stage 0 feasibility backtest over the frozen de-correlated universe and
the cached daily history, prints the dollar table + GO/NO-GO, and (optionally)
writes the gate-report markdown.

Exit code: 0 on a clean run (GO or NO-GO are BOTH successful outcomes); 1 if a
sanity assertion halted the run (scoring not trustworthy) or data is missing.
"""

from __future__ import annotations

import argparse
import sys

from paper_trader.backtest import historical_fetch
from paper_trader.backtest.sanity import SanityViolationError
from paper_trader.backtest.stage0_harness import Stage0Report, run_stage0
from paper_trader.backtest.stage0_universe import STAGE0_UNIVERSE, sector_spread


def _format_report(rep: Stage0Report) -> str:
    lines = [
        "=== Stage 0 — Feasibility Backtest ===",
        f"universe: {rep.n_symbols} symbols, {rep.n_points} points",
        f"seed bankroll: ${rep.seed_bankroll:,.0f}",
        "",
        f"floor (always-momentum):     ${rep.floor_pnl:>14,.2f}",
        f"oracle-best-method:          ${rep.oracle_pnl:>14,.2f}",
        f"ceiling (perfect foresight): ${rep.ceiling_pnl:>14,.2f}",
        "",
        f"headroom (oracle - floor):   ${rep.headroom:>14,.2f}",
        f"edge ratio (headroom/seed):  {rep.edge_ratio * 100:>14.3f}%",
        f"threshold E:                 {rep.threshold_e * 100:>14.3f}%",
        "",
        "per-method totals:",
    ]
    for name, res in rep.per_method.items():
        lines.append(
            f"  {name:<16} pnl ${res.total_pnl:>12,.2f}  "
            f"entered {res.n_entered:>4}  hit-rate {res.hit_rate * 100:5.1f}%"
        )
    lines += ["", f"sanity checks: {'PASSED' if rep.sanity_passed else 'FAILED'}"]
    verdict = (
        "GO — headroom exists, open Stage 1"
        if rep.go
        else "NO-GO — thesis dead (successful test)"
    )
    lines += [f"VERDICT: {verdict}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Stage 0 feasibility backtest.")
    parser.add_argument(
        "--threshold", type=float, default=0.03, help="edge threshold E (default 0.03 = 3%%)"
    )
    parser.add_argument("--bankroll", type=float, default=100_000.0)
    parser.add_argument("--report", help="write the gate-report markdown to this path")
    args = parser.parse_args(argv)

    history = historical_fetch.load_cached(STAGE0_UNIVERSE)
    missing = [s for s in STAGE0_UNIVERSE if s not in history]
    if missing:
        print(f"ERROR: {len(missing)} universe symbols not cached: {missing}", file=sys.stderr)
        print("Run scripts/fetch_backtest_data.py first.", file=sys.stderr)
        return 1

    try:
        rep = run_stage0(history, seed_bankroll=args.bankroll, threshold_e=args.threshold)
    except SanityViolationError as exc:
        print(f"SANITY VIOLATION — run NOT trustworthy: {exc}", file=sys.stderr)
        return 1

    print(_format_report(rep))
    print("\nsector spread:", sector_spread())

    if args.report:
        from paper_trader.backtest.stage0_gate_report import write_gate_report
        write_gate_report(rep, args.report)
        print(f"\ngate report written: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
