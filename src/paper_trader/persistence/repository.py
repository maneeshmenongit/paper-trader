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

    # ─── settlement (Live-Operation T4) ──────────────────────────────────
    # App-db only. The paper_trades table is a DOMAIN table (mutable), NOT a
    # governance store — settling a trade is an ordinary domain UPDATE, never a
    # Store A/B write.

    def open_trades_due(self, now_iso: str) -> list[dict[str, object]]:
        """Open (unexited) paper trades whose horizon has arrived (<= now).

        Returns plain dicts (id, symbol, entry_price, quantity, prediction_id,
        expected_exit_time) so the settlement module stays free of DB row types.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, prediction_id, symbol, entry_price, quantity,
                       notional_value, entry_time, expected_exit_time
                FROM paper_trades
                WHERE exited = 0 AND expected_exit_time <= ?
                ORDER BY id
                """,
                (now_iso,),
            ).fetchall()
        return [dict(r) for r in rows]

    def baseline_magnitude_for_prediction(self, prediction_id: int) -> float | None:
        """The momentum baseline shadow's magnitude for a traded prediction.

        The baseline is a separate ``is_baseline=1`` predictions row for the same
        symbol/cycle. Returns its ``magnitude_pct`` (signed by direction) so
        settlement can score the baseline P&L shadow, or None if absent.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT symbol, cycle_id FROM predictions WHERE id = ?",
                (prediction_id,),
            ).fetchone()
            if row is None:
                return None
            baseline = conn.execute(
                """
                SELECT direction, magnitude_pct FROM predictions
                WHERE symbol = ? AND cycle_id = ? AND is_baseline = 1
                ORDER BY id LIMIT 1
                """,
                (row["symbol"], row["cycle_id"]),
            ).fetchone()
        if baseline is None:
            return None
        signed = float(baseline["magnitude_pct"])
        return -signed if baseline["direction"] == "DOWN" else signed

    def predicted_magnitude_for_prediction(self, prediction_id: int) -> float | None:
        """The traded View's own predicted magnitude_pct (for magnitude_error)."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT magnitude_pct FROM predictions WHERE id = ?",
                (prediction_id,),
            ).fetchone()
        return float(row["magnitude_pct"]) if row is not None else None

    def mark_trade_settled(
        self, *, trade_id: int, exit_price: float, exit_time_iso: str
    ) -> None:
        """Close one paper trade at the given price/time (domain UPDATE)."""
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE paper_trades
                SET exited = 1, exit_price = ?, exit_time = ?
                WHERE id = ? AND exited = 0
                """,
                (exit_price, exit_time_iso, trade_id),
            )

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
