"""Live TradingClient (Live-Operation T3).

The live counterpart of ``tests.fixtures.fakes.FakeTradingClient`` — the simulated
exchange seam (ARCH_002: "the exchange is a SQLite table"). It is deliberately
THIN:

- ``submit_paper_trade`` returns a fill at the quoted price (v1 fill model, same
  as the fake). Persisting the ``paper_trades`` row is Execute's job via the
  Repository — this seam only answers "what price did you get".
- ``get_liquidity_metric`` is REAL: it derives Filter R2's figure from the T1
  data clients — 20-day average daily dollar volume for stocks (from yfinance
  OHLCV), 24h dollar volume for crypto (from CoinGecko). This is what makes the
  ratified $10M/$50M floors bind on real data.

No DB writes here (app-db persistence stays in Execute/Repository), no Store A/B.
"""

from __future__ import annotations

from paper_trader.data.interfaces import CryptoDataProvider, MarketDataProvider

# 20 trading days is the ratified stock liquidity window (filter@v1 R2).
_STOCK_LIQUIDITY_DAYS = 20


class LiveTradingClient:
    """Live simulated exchange. Fill = quoted price; liquidity = real derived figure."""

    def __init__(
        self,
        *,
        market_data: MarketDataProvider,
        crypto_data: CryptoDataProvider,
    ):
        self.market_data = market_data
        self.crypto_data = crypto_data

    async def submit_paper_trade(
        self, symbol: str, quantity: float, price: float
    ) -> float:
        # v1 fill model: fills exactly at the quoted price (no slippage model yet).
        # Slippage/market-impact is a later refinement gated on a demonstrated need.
        return price

    async def get_liquidity_metric(self, symbol: str, asset_type: str) -> float:
        """Real liquidity figure for Filter R2.

        Stocks: mean(close * volume) over the last ~20 bars (avg daily dollar
        volume). Crypto: CoinGecko 24h dollar volume. A data gap returns 0.0 —
        Filter R2 then rejects for insufficient liquidity rather than trading
        blind, which is the conservative choice.
        """
        if asset_type == "crypto":
            md = await self.crypto_data.get_market_data(symbol)
            vol = md.get("volume_24h")
            return float(vol) if isinstance(vol, (int, float)) else 0.0

        bars = await self.market_data.get_ohlcv(symbol, period_days=_STOCK_LIQUIDITY_DAYS)
        if not bars:
            return 0.0
        dollar_volumes = [b.close * b.volume for b in bars]
        return sum(dollar_volumes) / len(dollar_volumes)
