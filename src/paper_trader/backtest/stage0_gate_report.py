"""Stage 0 gate-report markdown writer (step 6).

Renders the §9 definition-of-done: dollar table, headroom + trade count, sanity
results, the threshold E and GO/NO-GO, the sector spread (§3 discharge), and the
loud H3 Stage-3-precondition flag. Pure formatting over a ``Stage0Report``.
"""

from __future__ import annotations

from pathlib import Path

from paper_trader.backtest.stage0_harness import Stage0Report
from paper_trader.backtest.stage0_universe import sector_spread


def render_gate_report(rep: Stage0Report) -> str:
    verdict = "GO" if rep.go else "NO-GO"
    spread = ", ".join(f"{k}: {v}" for k, v in sorted(sector_spread().items()))
    lines = [
        "# Stage 0 — Feasibility Backtest · Gate Report",
        "",
        "**Deterministic, no LLM.** A NO-GO is a *successful* test (the thesis is",
        "falsified cheaply). Inputs were NOT tuned to force a GO.",
        "",
        "## 1. Dollar table",
        "",
        f"- Seed bankroll: **${rep.seed_bankroll:,.0f}**",
        f"- Universe: **{rep.n_symbols} symbols**, **{rep.n_points} points**",
        "",
        "| Measuring stick | Realized P&L |",
        "|---|---:|",
        f"| Floor (always-momentum) | ${rep.floor_pnl:,.2f} |",
        f"| Oracle-best-method (hindsight-perfect pick) | ${rep.oracle_pnl:,.2f} |",
        f"| Ceiling (perfect foresight, horizon-matched) | ${rep.ceiling_pnl:,.2f} |",
        "",
        "### Per-method",
        "",
        "| Method | P&L | Entered | Hit-rate |",
        "|---|---:|---:|---:|",
    ]
    for name, res in rep.per_method.items():
        lines.append(
            f"| {name} | ${res.total_pnl:,.2f} | {res.n_entered} | {res.hit_rate * 100:.1f}% |"
        )

    lines += [
        "",
        "## 2. Headroom",
        "",
        f"- **Headroom (oracle − floor): ${rep.headroom:,.2f}**",
        f"- Edge ratio (headroom / seed): **{rep.edge_ratio * 100:.3f}%**",
        f"- Trade count (points scored): **{rep.n_points}** "
        "(so a small-sample edge cannot masquerade as signal)",
        "",
        "## 3. Sanity checks (§4)",
        "",
        f"- **{'ALL PASSED' if rep.sanity_passed else 'FAILED'}** — "
        "#1 ceiling-bound, #2 floor cross-check, #3 entry-price realism, "
        "#4 no-look-ahead, #5 non-zero settlement.",
        "- The run halts on any violation, so reaching a verdict means all held.",
        "",
        "## 4. Threshold & verdict (Gap C)",
        "",
        f"- Edge threshold **E = {rep.threshold_e * 100:.2f}%** of seed bankroll "
        "(return-on-bankroll edge; +3pp used only as a reference magnitude).",
        f"- Edge ratio {rep.edge_ratio * 100:.3f}% "
        f"{'≥' if rep.go else '<'} E {rep.threshold_e * 100:.2f}%.",
        f"- **VERDICT: {verdict}** — "
        + (
            "real headroom exists; open Stage 1 (LLM-selector backtest)."
            if rep.go
            else "even a perfect picker has no edge on this universe; the thesis is "
            "dead. Stop the phase (weeks saved, like T02–T04)."
        ),
        "",
        "## 4b. How to read this headroom (honesty notes)",
        "",
        "- **Oracle definition (conservative).** Oracle-best-method = per point, pick "
        "the ELIGIBLE method that turned out right and **trade it** (must-trade — a "
        "losing best-of-a-bad-lot point still costs). It gets perfect *method choice* "
        "but NOT free abstention or timing. An earlier draft floored each point at 0 "
        "(free abstention), inflating the oracle to ~$103k; that conflates selection "
        "skill with timing skill Stage 1's selector won't have, so it was removed. The "
        "reported oracle is the smaller, honest bound.",
        "- **Market regime.** The 2024–2026 window is a rising market (ceiling "
        f"${rep.ceiling_pnl:,.0f} of available upside). The floor "
        f"(always-momentum) captured only ${rep.floor_pnl:,.0f} of it — momentum "
        "barely participates. The headroom is real, but Stage 1 must show the LLM "
        "captures it as *skill*, not just by riding the tape (that is exactly the "
        "floor/ceiling band's job).",
        "- **What GO means precisely.** A *perfect* method-picker clears the floor by "
        f"{rep.edge_ratio * 100:.1f}% of bankroll over {rep.n_points:,} points. So "
        "there IS headroom for a selector to fight for — the necessary precondition "
        "for Stage 1. It does NOT mean the LLM will capture it; that is Stage 1's "
        "question.",
        "",
        "## 5. Universe spread (§3 discharge)",
        "",
        f"- Sector spread: {spread}.",
        "- Deliberately de-correlated and tech-capped (not the predecessor's "
        "tech-heavy 50-name set), so the result is not a false NO-GO from homogeneity.",
        "- **Gap:** no crypto in the cached data — the harness supports crypto symbols, "
        "but none were fetched. Recorded, not silently dropped.",
        "",
        "## 6. Real-math + real-seam constraint (§1)",
        "",
        "- **Imported (not re-coded):** `analytics.pnl` (realized_pnl, "
        "actual_move_fraction), `analytics.direction_score` (direction_correct), and "
        "`settlement.engine.horizon_exit_time`.",
        "- The Stage-0 adapter contains **no P&L or horizon arithmetic of its own** — "
        "it drives the real functions over cached data via the fixed `OfflineMarketData` "
        "seam (real cached closes, never a fabricated price).",
        "- This is why sanity check #2 is load-bearing: the momentum method and the "
        "momentum floor flow through the *same* real math, so their equality is a real "
        "invariant.",
        "",
        "## 7. ⚠ Stage-3 precondition — H3 (live hourly-bar default)",
        "",
        "- The live `YFinanceMarketData` defaults to `interval=\"1h\"`. Stage 0 ran on "
        "**daily** cached bars (correct semantics), but the live R4 run in Stage 3 must "
        "be reconciled to daily semantics **or it will disagree with this backtest** — "
        "the momentum/liquidity signals were designed for daily closes. This is a "
        "**hard precondition for Stage 3**, tracked in "
        "`docs/CODE_REVIEW_IMPROVEMENTS_001.md` (finding H3).",
        "",
    ]
    return "\n".join(lines)


def write_gate_report(rep: Stage0Report, path: str) -> None:
    Path(path).write_text(render_gate_report(rep))
