"""Live data-client implementations (Live-Operation T1).

The real counterparts of the Wave 2.5 seam fakes, one per external provider,
each implementing an existing ``paper_trader.data.interfaces`` protocol verbatim:

- ``YFinanceMarketData``  -> MarketDataProvider (stocks + crypto; no key)
- ``FinnhubCompanyNews``  -> CompanyNewsProvider (stock news; needs a key)
- ``CoinGeckoCryptoData`` -> CryptoDataProvider  (crypto market data; no key)

Agents are unchanged — they depend on the protocols, not these classes. The
fakes→live swap is wired by config (T3), never inside an agent. All three share
the ``retry_with_backoff`` seam; per-provider concurrency politeness stays owned
by the Research agent's semaphores.
"""

from __future__ import annotations

from paper_trader.data.live.coingecko_client import CoinGeckoCryptoData
from paper_trader.data.live.finnhub_client import FinnhubCompanyNews
from paper_trader.data.live.retry import retry_with_backoff
from paper_trader.data.live.yfinance_client import YFinanceMarketData

__all__ = [
    "CoinGeckoCryptoData",
    "FinnhubCompanyNews",
    "YFinanceMarketData",
    "retry_with_backoff",
]
