"""Live-operation wiring (Live-Operation T3).

The layer that turns the momentum skeleton LIVE: env-sourced config, the
fakes→live provider swap, and the config-authored watchlist. Everything the
run harness (T5) needs to assemble a live cycle without any agent knowing which
implementation it got.

Nothing here enters the immutable trace: keys and endpoints are secrets/config
(DT-4.2 MUST-NOT-freeze). Agents stay protocol-bound; this module chooses the
implementation.
"""

from __future__ import annotations

from paper_trader.live.config import LiveConfig, load_live_config
from paper_trader.live.providers import DataProviders, build_data_providers, build_llm_router
from paper_trader.live.trading import LiveTradingClient
from paper_trader.live.watchlist import load_watchlist

__all__ = [
    "DataProviders",
    "LiveConfig",
    "LiveTradingClient",
    "build_data_providers",
    "build_llm_router",
    "load_live_config",
    "load_watchlist",
]
