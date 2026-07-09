"""Offline market-data seam (Stage 0 step 2).

The Stage-0 hard constraint: the backtest seam must serve REAL cached closes,
never a round-number fallback. Stub mode (no history) preserves the offline
runner's legacy flat-quote behavior so the frozen live/offline runner path is
untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from paper_trader.data.offline import OfflineMarketData, OfflineQuoteError


def _frame(rows: dict[str, float]) -> pd.DataFrame:
    idx = pd.to_datetime(list(rows.keys()))
    return pd.DataFrame({"Close": list(rows.values())}, index=idx)


HISTORY = {
    "AAPL": _frame({"2026-01-05": 150.0, "2026-01-06": 155.0, "2026-01-07": 148.0}),
}


# ─── stub mode: legacy behavior preserved (offline runner path) ──────────

async def test_stub_mode_flat_quote_no_history():
    md = OfflineMarketData()
    assert await md.get_current_quote("AAPL") == 100.0


async def test_stub_mode_custom_flat_quote():
    md = OfflineMarketData(stub_quote=42.0)
    assert await md.get_current_quote("ANY") == 42.0


# ─── history mode: real cached close served by (symbol, timestamp) ───────

async def test_history_mode_returns_real_close():
    md = OfflineMarketData(HISTORY)
    price = await md.get_current_quote("AAPL", datetime(2026, 1, 6, 20, 0, tzinfo=UTC))
    assert price == pytest.approx(155.0)


def test_close_on_normalizes_intraday_timestamp():
    md = OfflineMarketData(HISTORY)
    # Any time on the 7th resolves to that trading day's close.
    assert md.close_on("AAPL", datetime(2026, 1, 7, 9, 30, tzinfo=UTC)) == pytest.approx(148.0)


# ─── refusal: never fabricate (sanity check #3) ──────────────────────────

async def test_history_mode_missing_symbol_raises():
    md = OfflineMarketData(HISTORY)
    with pytest.raises(OfflineQuoteError):
        await md.get_current_quote("MSFT", datetime(2026, 1, 6, tzinfo=UTC))


async def test_history_mode_missing_day_raises():
    md = OfflineMarketData(HISTORY)
    with pytest.raises(OfflineQuoteError):
        await md.get_current_quote("AAPL", datetime(2026, 1, 8, tzinfo=UTC))


async def test_history_mode_requires_timestamp():
    md = OfflineMarketData(HISTORY)
    with pytest.raises(OfflineQuoteError):
        await md.get_current_quote("AAPL")  # history present but no timestamp


# ─── guard: >0 and isfinite ──────────────────────────────────────────────

def test_zero_close_is_refused():
    md = OfflineMarketData({"BAD": _frame({"2026-01-05": 0.0})})
    assert md.has_close_on("BAD", datetime(2026, 1, 5, tzinfo=UTC)) is False
    with pytest.raises(OfflineQuoteError):
        md.close_on("BAD", datetime(2026, 1, 5, tzinfo=UTC))


def test_nan_close_is_refused():
    md = OfflineMarketData({"BAD": _frame({"2026-01-05": float("nan")})})
    with pytest.raises(OfflineQuoteError):
        md.close_on("BAD", datetime(2026, 1, 5, tzinfo=UTC))


def test_has_close_on_true_for_real_close():
    md = OfflineMarketData(HISTORY)
    assert md.has_close_on("AAPL", datetime(2026, 1, 5, tzinfo=UTC)) is True
