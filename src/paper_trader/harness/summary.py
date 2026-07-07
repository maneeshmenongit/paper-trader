"""Post-run summary for the T6 run report (Live-Operation T6).

Reads a completed run's app db (READ-ONLY) and its observability directory and
returns grounded totals — trades executed, trades settled + scored, momentum's
realized P&L vs the baseline shadow, observer findings, replay trust. The T6 run
report is written from THIS, so every number traces to a real record.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunSummary:
    cycles: int = 0
    trades_executed: int = 0
    trades_settled: int = 0
    post_mortems: int = 0
    hits: int = 0
    realized_pnl: float = 0.0
    baseline_pnl: float = 0.0
    findings: int = 0
    replay_cycles: int = 0
    all_pins_verified: bool = True
    symbols_traded: list[str] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.post_mortems if self.post_mortems else 0.0


def summarize_run(*, app_db_path: Path, run_dir: Path) -> RunSummary:
    """Assemble a RunSummary from the app db + the run's replay artifacts."""
    s = RunSummary()

    uri = f"file:{app_db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        s.cycles = _scalar(conn, "SELECT COUNT(DISTINCT cycle_id) c FROM paper_trades")
        s.trades_executed = _scalar(conn, "SELECT COUNT(*) c FROM paper_trades")
        s.trades_settled = _scalar(conn, "SELECT COUNT(*) c FROM paper_trades WHERE exited=1")
        s.post_mortems = _scalar(conn, "SELECT COUNT(*) c FROM post_mortems")
        s.hits = _scalar(conn, "SELECT COUNT(*) c FROM post_mortems WHERE direction_correct=1")
        s.realized_pnl = _scalar_f(
            conn, "SELECT COALESCE(SUM(simulated_pnl),0) v FROM post_mortems"
        )
        s.baseline_pnl = _scalar_f(
            conn, "SELECT COALESCE(SUM(baseline_pnl),0) v FROM post_mortems"
        )
        s.symbols_traded = [
            r["symbol"] for r in conn.execute(
                "SELECT DISTINCT symbol FROM paper_trades ORDER BY symbol"
            ).fetchall()
        ]
    finally:
        conn.close()

    # Replay artifacts: count reconstructions + confirm every pin verified.
    replays = sorted(run_dir.glob("*.replay.md")) if run_dir.exists() else []
    s.replay_cycles = len(replays)
    s.all_pins_verified = all(
        "All skill pins hash-VERIFIED" in p.read_text() for p in replays
    ) if replays else True

    findings = sorted(run_dir.glob("*.findings.json")) if run_dir.exists() else []
    s.findings = sum(_json_len(p) for p in findings)
    return s


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0


def _scalar_f(conn: sqlite3.Connection, sql: str) -> float:
    row = conn.execute(sql).fetchone()
    return float(row[0]) if row else 0.0


def _json_len(path: Path) -> int:
    import json

    try:
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0
