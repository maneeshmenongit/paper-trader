"""App-db read/write layer for domain history (Wave 2.5 Task 2).

Thin repository over the existing `Database` (persistence/db.py). Writes ONLY the
app db (paper_trader.sqlite) — never Store A/B, never the checkpointer. Used by
Execute (trade_decisions, paper_trades) and PostMortem (post_mortems, portfolio),
and by the supervisor to load cross-cycle state at cycle start.
"""

from __future__ import annotations

from paper_trader.domain import Asset, PaperTrade, PostMortem, TradeDecision
from paper_trader.persistence.db import Database


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ─── assets ──────────────────────────────────────────────────────────

    def upsert_asset(self, asset: Asset) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO assets (symbol, kind, sector) VALUES (?, ?, ?)
                ON CONFLICT (symbol) DO UPDATE SET kind=excluded.kind, sector=excluded.sector
                """,
                (asset.symbol, asset.kind, asset.sector),
            )

    # ─── predictions ─────────────────────────────────────────────────────

    def insert_prediction(
        self,
        *,
        cycle_id: str,
        symbol: str,
        entry_price: float,
        method_selected: str | None,
        selection_mode: str | None,
        selection_rationale: str | None,
        direction: str,
        confidence: float,
        magnitude_pct: float,
        time_horizon_hours: int,
        calibration_version: str,
        is_baseline: bool,
        created_at: str,
    ) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO predictions
                  (cycle_id, symbol, entry_price, method_selected, selection_mode,
                   selection_rationale, direction, confidence, magnitude_pct,
                   time_horizon_hours, calibration_version, is_baseline, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id, symbol, entry_price, method_selected, selection_mode,
                    selection_rationale, direction, confidence, magnitude_pct,
                    time_horizon_hours, calibration_version, int(is_baseline), created_at,
                ),
            )
            return int(cur.lastrowid or 0)

    # ─── trade decisions / trades ────────────────────────────────────────

    def insert_trade_decision(
        self, *, cycle_id: str, prediction_id: int, decision: TradeDecision, created_at: str
    ) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO trade_decisions
                  (cycle_id, prediction_id, executed, risk_reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cycle_id, prediction_id, int(decision.executed),
                 decision.risk_reason, created_at),
            )

    def insert_paper_trade(self, *, cycle_id: str, prediction_id: int, trade: PaperTrade) -> int:
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO paper_trades
                  (cycle_id, prediction_id, symbol, direction, entry_price, quantity,
                   notional_value, entry_time, expected_exit_time, exited)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cycle_id, prediction_id, trade.symbol, trade.direction, trade.entry_price,
                 trade.quantity, trade.notional_value, trade.entry_time.isoformat(),
                 trade.expected_exit_time.isoformat(), int(trade.exited)),
            )
            return int(cur.lastrowid or 0)

    def count_trade_decisions_for_prediction(self, prediction_id: int) -> int:
        """Idempotency support (Execute): has a decision already been written?"""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) c FROM trade_decisions WHERE prediction_id = ?",
                (prediction_id,),
            ).fetchone()
        return int(row["c"])

    # ─── post-mortems ────────────────────────────────────────────────────

    def insert_post_mortem(self, *, pm: PostMortem, created_at: str) -> None:
        import json

        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO post_mortems
                  (paper_trade_id, direction_correct, predicted_magnitude_pct,
                   actual_magnitude_pct, magnitude_error, simulated_pnl, baseline_pnl,
                   bias_tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(pm.paper_trade_id), int(pm.direction_correct),
                 pm.predicted_magnitude_pct, pm.actual_magnitude_pct, pm.magnitude_error,
                 pm.simulated_pnl, pm.baseline_pnl,
                 json.dumps(pm.bias_tags) if pm.bias_tags is not None else None,
                 created_at),
            )
