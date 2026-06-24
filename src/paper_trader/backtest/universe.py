"""The default 50-stock universe for the thesis validation backtest.

Composition:
- 20 large-cap tech (broad coverage of the most analyst-covered names)
- 10 large-cap finance (different sector profile)
- 10 large-cap consumer (different again)
- 10 mid-cap mixed (smaller market cap, less efficient pricing maybe)

This is a reasonable default for testing whether the LLM has signal across
sectors. The operator can override with --universe-file.
"""

DEFAULT_UNIVERSE: list[str] = [
    # Large-cap tech (20)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "AMD", "INTC", "CSCO", "QCOM", "IBM",
    "TXN", "INTU", "NOW", "PLTR",

    # Large-cap finance (10)
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "C",

    # Large-cap consumer (10)
    "WMT", "HD", "PG", "KO", "PEP", "COST", "MCD", "NKE", "SBUX", "DIS",

    # Mid-cap mixed (10)
    "ROKU", "SNAP", "PINS", "ETSY", "BYND", "PTON", "RBLX", "SOFI",
    "AFRM", "OPEN",
]
