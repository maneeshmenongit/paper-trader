"""Frozen, de-correlated Stage-0 universe (step 6).

STAGE0_BUILD_PROMPT §4: fix the universe up front (no survivorship bias) and
verify it is DE-CORRELATED before running — do NOT merely inherit the predecessor's
tech-heavy 50-symbol set, because a homogeneous universe makes methods agree,
shrinks apparent headroom, and can produce a FALSE NO-GO (killing the thesis for the
wrong reason).

This set deliberately balances sectors and caps tech exposure. Every symbol here is
already in the cached backtest data (``data/backtest/historical/``). Crypto is
in-scope per §3 but no crypto history was fetched into the cache, so it is a
documented gap (the harness supports crypto symbols; the DATA does not yet include
them) — recorded in the gate report, not silently dropped.

Sector spread (30 symbols, tech capped at 20%):
- Tech (6): AAPL, MSFT, NVDA, ORCL, CSCO, IBM
- Financials (6): JPM, V, MA, GS, AXP, BLK
- Consumer staples/discretionary (6): WMT, PG, KO, MCD, COST, NKE
- Communication/media (4): META, GOOGL, DIS, PINS
- Industrials-ish / payments / semis-adjacent (4): TXN, QCOM, INTU, ADBE
- Higher-beta mid/small (4): SOFI, ROKU, SNAP, AFRM
"""

STAGE0_UNIVERSE: list[str] = [
    # Tech (6) — deliberately capped, NOT the 20-name tech block.
    "AAPL", "MSFT", "NVDA", "ORCL", "CSCO", "IBM",
    # Financials (6)
    "JPM", "V", "MA", "GS", "AXP", "BLK",
    # Consumer (6)
    "WMT", "PG", "KO", "MCD", "COST", "NKE",
    # Communication / media (4)
    "META", "GOOGL", "DIS", "PINS",
    # Payments / semis / software (4)
    "TXN", "QCOM", "INTU", "ADBE",
    # Higher-beta mid/small (4)
    "SOFI", "ROKU", "SNAP", "AFRM",
]

# Sector labels for the gate report's de-correlation statement.
STAGE0_SECTORS: dict[str, str] = {
    **{s: "tech" for s in ("AAPL", "MSFT", "NVDA", "ORCL", "CSCO", "IBM")},
    **{s: "financials" for s in ("JPM", "V", "MA", "GS", "AXP", "BLK")},
    **{s: "consumer" for s in ("WMT", "PG", "KO", "MCD", "COST", "NKE")},
    **{s: "comm_media" for s in ("META", "GOOGL", "DIS", "PINS")},
    **{s: "payments_semis_sw" for s in ("TXN", "QCOM", "INTU", "ADBE")},
    **{s: "high_beta" for s in ("SOFI", "ROKU", "SNAP", "AFRM")},
}


def sector_spread() -> dict[str, int]:
    """Count of symbols per sector — for the gate report's §3 discharge."""
    spread: dict[str, int] = {}
    for sector in STAGE0_SECTORS.values():
        spread[sector] = spread.get(sector, 0) + 1
    return spread
