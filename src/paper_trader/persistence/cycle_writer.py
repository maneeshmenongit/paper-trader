"""Persist a completed cycle's domain outputs to the app db (Wave 2.5 Task 9).

Writes ONLY the app db (predictions, trade_decisions, paper_trades, post_mortems)
— never Store A/B. This is the domain-history write that closes a cycle; the
governance-trace emission (Store A/B) is a later wave and is NOT done here.
"""

from __future__ import annotations

from paper_trader.domain import Asset, View
from paper_trader.graph.state import CycleState
from paper_trader.persistence.repository import Repository


def persist_cycle(repo: Repository, state: CycleState) -> None:
    """Persist predictions, trade decisions, and paper trades from a cycle."""
    created_at = (state.ended_at or state.started_at).isoformat()

    # symbol -> app-db prediction id, so decisions/trades can FK to it.
    prediction_ids: dict[str, int] = {}

    for symbol, pred in state.predictions.items():
        if not isinstance(pred, View):
            continue  # NoView is a valid terminal answer; not persisted as a row
        repo.upsert_asset(_asset_for(symbol, state))
        last_close = pred.method_inputs_summary.get("last_close", 0.0)
        entry_price = float(last_close) if isinstance(last_close, (int, float)) else 0.0
        prediction_ids[symbol] = repo.insert_prediction(
            cycle_id=state.cycle_id,
            symbol=symbol,
            entry_price=entry_price,
            method_selected=pred.method_selected,
            selection_mode=pred.selection_mode,
            selection_rationale=pred.selection_rationale,
            direction=pred.direction,
            confidence=pred.confidence,
            magnitude_pct=pred.magnitude_pct,
            time_horizon_hours=pred.horizon,
            calibration_version=state.calibration_version,
            is_baseline=pred.is_baseline,
            created_at=created_at,
        )

    for symbol, decision in state.trade_decisions.items():
        pid = prediction_ids.get(symbol)
        if pid is None:
            continue
        repo.insert_trade_decision(
            cycle_id=state.cycle_id, prediction_id=pid,
            decision=decision, created_at=created_at,
        )

    for trade in state.new_paper_trades:
        pid = prediction_ids.get(trade.symbol)
        if pid is None:
            continue
        repo.insert_paper_trade(cycle_id=state.cycle_id, prediction_id=pid, trade=trade)


def _asset_for(symbol: str, state: CycleState) -> Asset:
    for a in state.watchlist + state.tradeable_assets:
        if a.symbol == symbol:
            return a
    return Asset(symbol=symbol, kind="stock")
