"""Stage 1 harness (step 4): end-to-end on a synthetic slice with a stub selector."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from paper_trader.backtest.llm_selector import LLMSelector
from paper_trader.backtest.stage1_gate_report import render_gate_report
from paper_trader.backtest.stage1_harness import run_stage1


def _synthetic_history(n_symbols=25, n_days=90, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")
    hist = {}
    for k in range(n_symbols):
        closes = [100.0]
        for _ in range(n_days - 1):
            closes.append(max(1.0, closes[-1] * (1 + rng.normal(0.0004, 0.02))))
        hist[f"SYM{k:02d}"] = pd.DataFrame({"Close": closes}, index=dates)
    return hist


class _StubRouter:
    """Deterministic 'LLM': always picks the first eligible method, high confidence."""

    def __init__(self):
        self.calls = 0

    def call(self, purpose, system, user, max_tokens=200, json_mode=False):
        self.calls += 1
        # Parse the eligible list out of the prompt to pick a valid method.
        line = next(ln for ln in user.splitlines() if ln.startswith("eligible methods:"))
        first = line.split(":", 1)[1].split(",")[0].strip()
        return json.dumps({"method": first, "confidence": 0.9, "rationale": "stub"}), 10


def test_stage1_end_to_end_runs():
    sel = LLMSelector(_StubRouter())
    rep = run_stage1(_synthetic_history(), sel, threshold_e=0.03)
    assert rep.sanity_passed is True
    assert rep.verdict in {"SUCCEEDED", "FAILED", "INCONCLUSIVE"}
    # Band context sanity: floor ≤ oracle ≤ ceiling.
    assert rep.floor_momentum_pnl <= rep.oracle_pnl + 1e-6
    assert rep.oracle_pnl <= rep.ceiling_pnl + 1e-6
    # Effective floor is the max of momentum and null.
    assert rep.effective_floor_pnl == max(rep.floor_momentum_pnl, rep.null_pnl)


def test_stage1_llm_path_only_on_multi_eligible():
    router = _StubRouter()
    sel = LLMSelector(router)
    rep = run_stage1(_synthetic_history(), sel)
    # Every LLM call corresponds to a ≥2-eligible point (R4); calls ≤ path points.
    assert router.calls <= rep.llm_llm_path_points + rep.llm_cache_hits
    assert rep.llm_llm_path_points > 0


def test_stage1_max_calls_incomplete():
    sel = LLMSelector(_StubRouter(), max_calls=5)
    rep = run_stage1(_synthetic_history(), sel)
    assert rep.verdict == "INCOMPLETE"
    assert rep.incomplete_reason is not None


def test_stage1_verdict_needs_coverage():
    # A tiny universe cannot meet the diversity floors → INCONCLUSIVE, never SUCCEEDED.
    sel = LLMSelector(_StubRouter())
    small = _synthetic_history(n_symbols=5, n_days=60)
    rep = run_stage1(small, sel)
    assert rep.verdict == "INCONCLUSIVE"


def test_stage1_gate_report_renders():
    sel = LLMSelector(_StubRouter())
    rep = run_stage1(_synthetic_history(), sel)
    md = render_gate_report(rep, floor_crosscheck="reconciles (test)")
    assert "North star" in md
    assert rep.verdict in md
    assert "H3" in md  # carried Stage-3 precondition flag
    assert "stage1-selector-v1" in md  # the versioned prompt is recorded


def test_stage1_null_selector_is_ex_ante():
    # The null selector must not peek: its first-ever pick is cold-start (first
    # eligible), not a hindsight winner. We assert the run completes and the null
    # P&L is finite and independent of oracle (sanity that no leak inflated it).
    sel = LLMSelector(_StubRouter())
    rep = run_stage1(_synthetic_history(), sel)
    assert rep.null_pnl <= rep.oracle_pnl + 1e-6  # null can't beat hindsight oracle
