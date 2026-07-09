"""Stage 0 settlement adapter (step 4).

Verifies the adapter drives the REAL math (imported, not re-coded), enters
long-only on UP, prices from real cached closes, and returns 0 for don't-enter.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from paper_trader.analytics.pnl import realized_pnl
from paper_trader.backtest.methods import MethodForecast
from paper_trader.backtest.stage0_settlement import Stage0Settlement
from paper_trader.data.offline import OfflineMarketData, OfflineQuoteError

D1 = datetime(2026, 1, 5, tzinfo=UTC)
D2 = datetime(2026, 1, 6, tzinfo=UTC)


def _md():
    idx = pd.to_datetime(["2026-01-05", "2026-01-06"])
    return OfflineMarketData({"AAPL": pd.DataFrame({"Close": [100.0, 110.0]}, index=idx)})


def _up():
    return MethodForecast(direction="UP", magnitude_pct=5.0, eligible=True)


def _down():
    return MethodForecast(direction="DOWN", magnitude_pct=5.0, eligible=True)


# ─── long-only: enter iff UP ─────────────────────────────────────────────

def test_up_forecast_enters_and_scores_via_real_math():
    out = Stage0Settlement(_md(), notional=1000.0).settle("AAPL", _up(), D1, D2)
    assert out.entered is True
    assert out.entry_price == 100.0 and out.exit_price == 110.0
    # P&L must equal the real analytics.pnl function, not a re-coded copy.
    expected = realized_pnl(100.0, 110.0, 1000.0 / 100.0)
    assert out.pnl == pytest.approx(expected) == pytest.approx(100.0)
    assert out.direction_hit is True
    assert out.actual_move_pct == pytest.approx(10.0)


def test_down_forecast_does_not_enter():
    out = Stage0Settlement(_md()).settle("AAPL", _down(), D1, D2)
    assert out.entered is False
    assert out.pnl == 0.0
    assert out.entry_price is None and out.direction_hit is None


def test_ineligible_forecast_does_not_enter():
    out = Stage0Settlement(_md()).settle("AAPL", MethodForecast.ineligible(), D1, D2)
    assert out.entered is False and out.pnl == 0.0


# ─── prices are real cached closes, never fabricated ─────────────────────

def test_missing_close_raises_not_fabricated():
    md = _md()
    with pytest.raises(OfflineQuoteError):
        Stage0Settlement(md).settle("AAPL", _up(), D1, datetime(2026, 1, 9, tzinfo=UTC))


def test_loss_when_price_fell():
    idx = pd.to_datetime(["2026-01-05", "2026-01-06"])
    md = OfflineMarketData({"X": pd.DataFrame({"Close": [100.0, 90.0]}, index=idx)})
    out = Stage0Settlement(md, notional=1000.0).settle("X", _up(), D1, D2)
    assert out.pnl == pytest.approx(-100.0)
    assert out.direction_hit is False


def test_fixed_notional_identical_across_symbols():
    # Sizing does not depend on the method — same notional deploys the same way.
    out = Stage0Settlement(_md(), notional=2000.0).settle("AAPL", _up(), D1, D2)
    assert out.quantity == pytest.approx(2000.0 / 100.0)
