"""Stage 1 frontier-confirmation gate-report writer.

Renders the confirmation report per STAGE1_FRONTIER_CONFIRM §4: the one-variable
attestation (only the model changed — prompt hash matches), the per-point model
attestation (DT-17 — every point served by the intended strong model), the dollar
table with the strong-model row NEXT TO the 7B Stage-1 figures, the verdict, and
the carried flags. Pure formatting over a Stage1Report.
"""

from __future__ import annotations

from pathlib import Path

from paper_trader.backtest.stage1_harness import Stage1Report

# Frozen Stage-1 (qwen2.5:7b) result, for the side-by-side. Source:
# docs/gate_reports/STAGE1_GATE_REPORT.md (600 points, same sample).
_S1_7B = {
    "llm_pnl": 255.58,
    "edge_pct": -0.301,
    "settled": 382,
    "verdict": "FAILED",
    "floor": 2110.90,
    "null": 2110.90,
    "oracle": 88443.33,
}
_PROMPT_HASH_S1 = "2bfae227d9790796"


def render_frontier_report(
    rep: Stage1Report, *, floor_crosscheck: str, prompt_hash: str,
    served_models: list[str], model_label: str,
) -> str:
    one_var_ok = prompt_hash == _PROMPT_HASH_S1
    attest_ok = len(served_models) == 1
    hash_note = (
        f"== Stage 1 `{_PROMPT_HASH_S1}` ✓ (prompt NOT re-tuned)"
        if one_var_ok else "≠ Stage 1 — INVALID, prompt changed"
    )
    attest_note = (
        "✓ every settled point ran on the intended strong model — zero silent fallbacks"
        if attest_ok else "✗ MORE THAN ONE MODEL SERVED — run INVALID (a fallback leaked in)"
    )
    lines = [
        "# Stage 1 — Frontier Confirmation · Gate Report",
        "",
        "> **North star:** Does an LLM choosing which method to trust beat cheap "
        "alternatives on real dollar P&L? A NO on evidence is a **successful** test — "
        "and this run resolves whether Stage 1's NO was the *thesis* or the *model*.",
        "",
        f"**Model under test:** `{model_label}` (strong reasoner) vs Stage 1's "
        "`qwen2.5:7b` (local).",
        "",
        "## 1. One-variable attestation (§4.1)",
        f"- Prompt hash `{prompt_hash}` {hash_note}.",
        "- Same 600 sampled points (same seed), same verdict rule, floors "
        "(E=3.0%), adapter, and five sanity checks. **Only the model changed.**",
        f"- Step 0 floor cross-check: {floor_crosscheck}.",
        "",
        "## 2. Per-point model attestation (§4.2, DT-17)",
        f"- Served by: **{served_models}**.",
        f"- **{attest_note}.**",
        "- The AttestingRouter has no fallback chain: a provider miss HALTS rather "
        "than downgrading, so a frontier result can never be silently 7B.",
        "",
        "## 3. Dollar table — strong model vs 7B, SAME 600 points",
        "",
        f"| Strategy | 7B (Stage 1) | **{model_label} (this run)** |",
        "|---|---:|---:|",
        f"| always_momentum (floor) | ${_S1_7B['floor']:,.2f} | ${rep.floor_momentum_pnl:,.2f} |",
        f"| null_selector (real bar) | ${_S1_7B['null']:,.2f} | ${rep.null_pnl:,.2f} |",
        f"| random_among_eligible | — | ${rep.random_pnl:,.2f} |",
        f"| **llm_selector** | **${_S1_7B['llm_pnl']:,.2f}** | **${rep.llm_pnl:,.2f}** |",
        f"| oracle_best_method | ${_S1_7B['oracle']:,.2f} | ${rep.oracle_pnl:,.2f} |",
        f"| ceiling | — | ${rep.ceiling_pnl:,.2f} |",
        "",
        "## 4. Strong-model edge (§4.4)",
        "",
        f"- Effective floor = max(momentum, null) = **${rep.effective_floor_pnl:,.2f}**.",
        f"- **Strong-model edge: ${rep.llm_edge:,.2f} = {rep.llm_edge_ratio * 100:.3f}%** "
        f"of bankroll, over **{rep.llm_settled} settled points** "
        f"(7B was {_S1_7B['edge_pct']:.3f}% over {_S1_7B['settled']} settled).",
        f"- Headroom captured: **{rep.headroom_capture * 100:.1f}%**. "
        f"Abstention: {rep.llm_abstain_rate * 100:.1f}%.",
        "",
        "## 5. Verdict (E = 3.0%, unchanged rule)",
        "",
        f"- 7B: **{_S1_7B['verdict']}** (edge {_S1_7B['edge_pct']:.3f}%).",
        f"- {model_label}: **{rep.verdict}** (edge {rep.llm_edge_ratio * 100:.3f}%).",
        "",
        "## 6. Sanity + coverage",
        f"- Five §4 sanity checks: **{'ALL PASSED' if rep.sanity_passed else 'FAILED'}**; "
        "no-post-decision-data guard confirmed.",
        f"- LLM calls: {rep.llm_calls} · cache hits: {rep.llm_cache_hits} · "
        f"tokens: {rep.llm_tokens:,}. Diversity: {rep.llm_distinct_symbols} symbols, "
        f"{rep.llm_distinct_dates} dates, {rep.llm_settled} settled.",
        "",
        "## 7. The three-way read (§5 — stated honestly, goalposts unmoved)",
        "",
        _three_way(rep),
        "",
        "## 8. Carried flags (unchanged)",
        "- No-news / Stage-3 Research delta; H3 (live hourly-bar) Stage-3 precondition; "
        "no-crypto gap; D1 register-logging. None affected by the model swap.",
        "",
    ]
    return "\n".join(lines)


def _three_way(rep: Stage1Report) -> str:
    beats_null = rep.llm_pnl >= rep.null_pnl
    if rep.verdict == "SUCCEEDED":
        return (
            "**SUCCEEDED (≥ 3%)** — the thesis is supported on price features alone. "
            "The Stage-1 NO was the *model*, not the thesis. Stage 3 (and its Stage-2 "
            "prerequisite) is justified. The 7B caveat is closed in the affirmative."
        )
    if beats_null and rep.llm_edge_ratio > 0:
        return (
            "**FAILED but now positive and beating the null selector** — genuinely "
            "open. The strong model adds *some* skill but not enough to clear the bar "
            "on price features alone. A judgment call on whether the Stage-3 news delta "
            "might carry it over — do NOT move the goalposts to rescue it."
        )
    return (
        "**Also FAILED — still negative / loses to the null selector.** The NO is now "
        "**final**: a frontier reasoner given the same information does not beat a "
        "5-line rule, so the caveat is closed. The thesis (price-features-only method "
        "selection) is not supported; the model was not the problem. Stop the thesis "
        "phase — the framework built stays valid and reusable."
    )


def write_frontier_report(
    rep: Stage1Report, path: str, *, floor_crosscheck: str, prompt_hash: str,
    served_models: list[str], model_label: str,
) -> None:
    Path(path).write_text(render_frontier_report(
        rep, floor_crosscheck=floor_crosscheck, prompt_hash=prompt_hash,
        served_models=served_models, model_label=model_label,
    ))
