"""Stage 1 gate-report markdown writer (step 4).

Renders the §9 definition-of-done: north-star line, step-0 note, the dollar table,
the LLM edge over max(momentum, null_selector) with trade counts and headroom
capture, the SUCCEEDED/FAILED/INCONCLUSIVE call, sanity + no-leak confirmation,
token/call accounting + diversity floors + the versioned prompt, the §2.1 real-math
confirmation, and the carried flags (no-news Stage-3 delta, H3, no-crypto, D1).
"""

from __future__ import annotations

from pathlib import Path

from paper_trader.backtest.llm_selector import SELECTION_PROMPT_VERSION
from paper_trader.backtest.stage1_harness import (
    MIN_DECISION_DATES,
    MIN_LLM_SETTLED,
    MIN_SYMBOLS,
    Stage1Report,
)

_NORTH_STAR = (
    "> **North star:** Does an LLM *choosing which forecasting method to trust* make "
    "measurably better trades than cheap alternatives — enough to be worth it — judged "
    "on real dollar P&L inside the floor/ceiling band? A NO-GO on evidence is a "
    "**successful** test."
)


def render_gate_report(rep: Stage1Report, *, floor_crosscheck: str) -> str:
    if rep.verdict == "INCOMPLETE":
        return "\n".join([
            "# Stage 1 — LLM-Selector Backtest · Gate Report",
            "", _NORTH_STAR, "",
            "## VERDICT: INCOMPLETE",
            f"- Reason: {rep.incomplete_reason}",
            "- The --max-calls cap was hit before coverage completed. Raise the cap or "
            "narrow the universe and re-run. No verdict is claimed.",
        ])

    diversity_ok = (
        rep.llm_distinct_symbols >= MIN_SYMBOLS
        and rep.llm_distinct_dates >= MIN_DECISION_DATES
        and rep.llm_settled >= MIN_LLM_SETTLED
    )
    lines = [
        "# Stage 1 — LLM-Selector Backtest · Gate Report",
        "", _NORTH_STAR, "",
        "## 1. Step 0 — inherited-floor cross-check",
        f"- {floor_crosscheck}",
        "",
        "## 2. Dollar table",
        "",
        f"- Seed bankroll: **${rep.seed_bankroll:,.0f}** · universe **{rep.n_symbols} "
        f"symbols**, **{rep.n_points:,} points**.",
        (
            f"- **Sampled run:** the LLM path ran on a date-stratified sample of "
            f"**{rep.llm_points_evaluated:,} points** "
            f"({rep.llm_points_evaluated / rep.n_points * 100:.1f}% of the universe); "
            "the edge/floor/oracle below are measured over those SAME points. All "
            "strategies + the trailing scoreboard still saw the full history."
            if rep.sampled
            else f"- Full run: the LLM path evaluated all {rep.llm_points_evaluated:,} points."
        ),
        "",
        "| Strategy | Realized P&L | Entered |",
        "|---|---:|---:|",
        f"| always_momentum (floor) | ${rep.floor_momentum_pnl:,.2f} | — |",
        f"| null_selector (real bar) | ${rep.null_pnl:,.2f} | — |",
        f"| random_among_eligible | ${rep.random_pnl:,.2f} | — |",
        f"| **llm_selector** | **${rep.llm_pnl:,.2f}** | {rep.llm_settled} |",
        f"| oracle_best_method (hindsight) | ${rep.oracle_pnl:,.2f} | — |",
        f"| ceiling (perfect foresight) | ${rep.ceiling_pnl:,.2f} | — |",
        "",
        "## 3. LLM edge (over the EFFECTIVE floor)",
        "",
        f"- Effective floor = max(momentum ${rep.floor_momentum_pnl:,.2f}, "
        f"null ${rep.null_pnl:,.2f}) = **${rep.effective_floor_pnl:,.2f}**.",
        f"- **LLM edge: ${rep.llm_edge:,.2f}** = **{rep.llm_edge_ratio * 100:.3f}%** "
        f"of bankroll, over **{rep.llm_settled} settled LLM points**.",
        f"- Headroom captured (edge / (oracle − eff-floor)): "
        f"**{rep.headroom_capture * 100:.1f}%**.",
        f"- LLM abstention rate: {rep.llm_abstain_rate * 100:.1f}% "
        f"(NoView / don't-enter across all points).",
        "",
        f"## 4. Verdict (Gap C, E = {rep.threshold_e * 100:.1f}%)",
        "",
        f"- **{rep.verdict}** — "
        + _verdict_gloss(rep),
        "",
        "## 5. Sanity + fusion-trap",
        "",
        f"- Five §4 sanity checks: **{'ALL PASSED' if rep.sanity_passed else 'FAILED'}**.",
        "- No-post-decision-data (§2.3): the null selector's trailing scoreboard is fed "
        "only by horizons closed **strictly before** each decision date; the LLM feature "
        "builder reads only pre-decision closes. Confirmed structurally + in tests.",
        "",
        "## 6. Token / call accounting + coverage (§5)",
        "",
        f"- LLM calls: **{rep.llm_calls}** · cache hits: {rep.llm_cache_hits} · "
        f"tokens: {rep.llm_tokens:,}.",
        f"- LLM-path points (≥2 eligible): {rep.llm_llm_path_points:,}.",
        f"- Diversity: {rep.llm_distinct_symbols} symbols (≥{MIN_SYMBOLS}), "
        f"{rep.llm_distinct_dates} dates (≥{MIN_DECISION_DATES}), "
        f"{rep.llm_settled} settled (≥{MIN_LLM_SETTLED}) — "
        f"**{'met' if diversity_ok else 'NOT met → INCONCLUSIVE'}**.",
        f"- Versioned prompt: `{SELECTION_PROMPT_VERSION}` (fixed up front; not tuned).",
        "",
        "## 7. Real-math + real-seam (§2.1)",
        "",
        "- **Imported, not re-coded:** `analytics.pnl`, `analytics.direction_score`, "
        "`settlement.engine.horizon_exit_time`, priced via the fixed `OfflineMarketData` "
        "seam. The Stage 1 harness adds no P&L/horizon arithmetic; every strategy settles "
        "through the same Stage 0 adapter.",
        "",
        "## 8. Carried flags (restated)",
        "",
        "- **No-news / Stage-3 Research delta (§2.2):** the backtest is equal-information "
        "with NO news/narrative bundle (point-in-time historical news isn't reliably "
        "available). Research's contribution is a **known Stage-3 delta**, not part of this "
        "verdict.",
        "- **H3 (live hourly-bar default):** a **Stage-3 precondition** — the live R4 path "
        "must be reconciled to daily semantics or it will disagree with this backtest.",
        "- **No-crypto gap:** cached data is equities-only; needed before any cross-asset "
        "claim at Stage 3.",
        "- **D1:** the Stage 0 live-loop math extraction (analytics/*) was a human-gated "
        "amendment; to be logged in the alternatives register.",
        "",
    ]
    return "\n".join(lines)


def _verdict_gloss(rep: Stage1Report) -> str:
    if rep.verdict == "SUCCEEDED":
        return (
            f"LLM edge {rep.llm_edge_ratio * 100:.3f}% ≥ E {rep.threshold_e * 100:.1f}% "
            "and beats the null selector, over sufficient settled points. The LLM adds "
            "measurable selection skill on this universe — open Stage 2 (verdict resolver)."
        )
    if rep.verdict == "FAILED":
        beat_null = rep.llm_pnl >= rep.null_pnl
        return (
            "enough points to judge, but the LLM "
            + ("did not clear the edge threshold" if beat_null
               else "did not even beat the cheap null selector")
            + f" (edge {rep.llm_edge_ratio * 100:.3f}% < E {rep.threshold_e * 100:.1f}%). "
            "A 5-line rule captures the available edge; the thesis is not supported. "
            "Successful test — do NOT tune the prompt to flip it."
        )
    return (
        "too few settled LLM points or diversity floors unmet (or a degenerate band). "
        "No skill claim can be made; gather more coverage before re-judging."
    )


def write_gate_report(rep: Stage1Report, path: str, *, floor_crosscheck: str) -> None:
    Path(path).write_text(render_gate_report(rep, floor_crosscheck=floor_crosscheck))
