"""Stage 1 null selectors (step 2): ex-ante trailing pick + random baseline."""

from __future__ import annotations

import random
from datetime import UTC, datetime

from paper_trader.backtest.methods import MethodForecast
from paper_trader.backtest.null_selector import (
    Selection,
    TrailingScoreboard,
    eligible_methods,
    horizon_closed_before,
    null_select,
    random_select,
)


def _fc(**elig: bool) -> dict[str, MethodForecast]:
    out = {}
    for name in ("momentum", "mean_reversion", "arima"):
        e = elig.get(name, False)
        out[name] = MethodForecast(direction="UP" if e else "HOLD",
                                   magnitude_pct=1.0, eligible=e)
    return out


# ─── eligibility ─────────────────────────────────────────────────────────

def test_eligible_methods_fixed_order():
    fc = _fc(arima=True, momentum=True)
    assert eligible_methods(fc) == ["momentum", "arima"]


# ─── trailing scoreboard picks the best track record ─────────────────────

def test_null_picks_best_trailing_hit_rate():
    sb = TrailingScoreboard()
    # momentum: 1/2 hits; arima: 2/2 hits → arima wins when both eligible.
    sb.record_closed("momentum", entered=True, hit=True, pnl=10.0)
    sb.record_closed("momentum", entered=True, hit=False, pnl=-5.0)
    sb.record_closed("arima", entered=True, hit=True, pnl=3.0)
    sb.record_closed("arima", entered=True, hit=True, pnl=4.0)
    sel = null_select(_fc(momentum=True, arima=True), sb)
    assert sel.method == "arima" and sel.selection_mode == "rule"


def test_null_cold_start_is_first_eligible_not_hindsight():
    sel = null_select(_fc(mean_reversion=True, arima=True), TrailingScoreboard())
    assert sel.method == "mean_reversion"  # first in fixed order
    assert sel.selection_mode == "cold_start"


def test_null_abstains_when_none_eligible():
    sel = null_select(_fc(), TrailingScoreboard())
    assert sel.method is None


def test_scoreboard_ignores_not_entered():
    sb = TrailingScoreboard()
    sb.record_closed("momentum", entered=False, hit=False, pnl=0.0)
    # No entered trades → no evidence → cold start (first eligible).
    assert sb.best_among(["momentum"]) is None


# ─── random selector ─────────────────────────────────────────────────────

def test_random_picks_only_eligible():
    rng = random.Random(0)
    for _ in range(20):
        sel = random_select(_fc(momentum=True, arima=True), rng)
        assert sel.method in {"momentum", "arima"}


def test_random_is_seeded_deterministic():
    seq1 = [random_select(_fc(momentum=True, arima=True), random.Random(42)).method]
    seq2 = [random_select(_fc(momentum=True, arima=True), random.Random(42)).method]
    assert seq1 == seq2


# ─── ex-ante contract (§2.3 fusion-trap guard) ───────────────────────────

def test_horizon_closed_before_is_strict():
    d = datetime(2026, 1, 10, tzinfo=UTC)
    assert horizon_closed_before(datetime(2026, 1, 9, tzinfo=UTC), d) is True
    assert horizon_closed_before(datetime(2026, 1, 10, tzinfo=UTC), d) is False  # not strict-before
    assert horizon_closed_before(datetime(2026, 1, 11, tzinfo=UTC), d) is False


def test_selection_is_frozen():
    s = Selection(method="momentum", selection_mode="rule")
    try:
        s.method = "arima"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised
