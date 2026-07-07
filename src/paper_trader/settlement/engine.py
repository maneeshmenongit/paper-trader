"""Settlement engine (Live-Operation T4).

``settle_due_trades`` runs between cycles (T5 harness): find open trades whose
horizon has arrived, price them at the current quote, close them in the app db,
and return the settling ``PaperTrade`` objects plus per-trade context (predicted
magnitude, baseline-shadow magnitude) for PostMortem to score.

App-db only. No Store A/B. Clock is injected (never ``datetime.now()``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from paper_trader.data.interfaces import Clock, MarketDataProvider
from paper_trader.domain import PaperTrade
from paper_trader.persistence.repository import Repository


@dataclass(frozen=True)
class SettlementContext:
    """Per-trade extras PostMortem needs to score against the ORIGINAL forecast.

    ``predicted_magnitude_pct`` is the traded View's own forecast magnitude (for
    magnitude_error). ``baseline_magnitude_pct`` is the momentum baseline shadow's
    magnitude for the same symbol/cycle — the selector's independent measuring
    stick. Either may be None when the app-db lacks the row (older trades).
    """

    prediction_id: str
    predicted_magnitude_pct: float | None
    baseline_magnitude_pct: float | None


@dataclass
class SettlementResult:
    settled_trades: list[PaperTrade] = field(default_factory=list)
    contexts: dict[str, SettlementContext] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.settled_trades)


async def settle_due_trades(
    *,
    repo: Repository,
    market_data: MarketDataProvider,
    clock: Clock,
) -> SettlementResult:
    """Close every open trade past horizon; return them for scoring.

    For each due trade: fetch the current quote, UPDATE the app-db row to
    exited/exit_price/exit_time, and build a settling ``PaperTrade`` (with
    exit fields populated) + its ``SettlementContext``. A per-trade pricing
    failure is skipped (left open to retry next pass), never aborting the batch.
    """
    now = clock.now()
    result = SettlementResult()

    for row in repo.open_trades_due(now.isoformat()):
        trade_id = int(_num(row["id"]))
        symbol = str(row["symbol"])
        prediction_id = int(_num(row["prediction_id"]))
        try:
            exit_price = await market_data.get_current_quote(symbol)
        except Exception:
            continue  # transient pricing miss → leave open, settle next pass

        repo.mark_trade_settled(
            trade_id=trade_id, exit_price=exit_price, exit_time_iso=now.isoformat()
        )

        settled = PaperTrade(
            prediction_id=str(prediction_id),
            symbol=symbol,
            direction="LONG",
            entry_price=_num(row["entry_price"]),
            quantity=_num(row["quantity"]),
            notional_value=_num(row["notional_value"]),
            entry_time=_parse_iso(str(row["entry_time"])),
            expected_exit_time=_parse_iso(str(row["expected_exit_time"])),
            exited=True,
            exit_price=exit_price,
            exit_time=now,
        )
        result.settled_trades.append(settled)
        result.contexts[str(prediction_id)] = SettlementContext(
            prediction_id=str(prediction_id),
            predicted_magnitude_pct=repo.predicted_magnitude_for_prediction(prediction_id),
            baseline_magnitude_pct=repo.baseline_magnitude_for_prediction(prediction_id),
        )

    return result


def horizon_exit_time(entry_time: datetime, horizon_hours: int) -> datetime:
    """The expected exit time for a trade: entry + the cycle horizon."""
    return entry_time + timedelta(hours=horizon_hours)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _num(value: object) -> float:
    """Coerce a SQLite row value (typed ``object``) to float."""
    assert isinstance(value, (int, float)), f"expected numeric, got {value!r}"
    return float(value)
