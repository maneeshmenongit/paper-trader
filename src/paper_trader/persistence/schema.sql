-- paper_trader app database (domain history) — Wave 2.5 Task 1.
-- Shape from PAPER_TRADER_ARCH_002 §8, with the predictions table reconciled to
-- the G6 output union (DT-8.3): method_selected + selection_mode added; direction
-- carries the View's forecast call. This is the app db (cross-cycle history), NOT
-- Store A/B (governance) and NOT the checkpointer.

CREATE TABLE IF NOT EXISTS assets (
    symbol   TEXT PRIMARY KEY,
    kind     TEXT NOT NULL CHECK (kind IN ('stock', 'crypto')),
    sector   TEXT
);

-- Predictions: reconciled to the method-selector union (DT-8.3).
CREATE TABLE IF NOT EXISTS predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id            TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    entry_price         REAL NOT NULL,
    -- DT-8.3 reconciliation: method-selector provenance replaces the dead-thesis
    -- UP/DOWN/HOLD-as-whole-story shape. method_selected NULL only for a NoView.
    method_selected     TEXT CHECK (method_selected IN ('momentum','mean_reversion','arima')),
    selection_mode      TEXT CHECK (selection_mode IN ('rule','llm')),
    selection_rationale TEXT,                 -- present iff selection_mode = 'llm'
    direction           TEXT NOT NULL CHECK (direction IN ('UP','DOWN','HOLD')),
    confidence          REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    magnitude_pct       REAL NOT NULL,
    time_horizon_hours  INTEGER NOT NULL,
    calibration_version TEXT NOT NULL,
    is_baseline         BOOLEAN NOT NULL DEFAULT 0,
    -- skill_version_id is canonical in Store A; mirrored here only as query
    -- convenience (DT-8.3). Nullable in this wave (no emission yet).
    skill_version_id    TEXT,
    created_at          TIMESTAMP NOT NULL,
    FOREIGN KEY (symbol) REFERENCES assets(symbol)
);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol_created
    ON predictions(symbol, created_at);

-- Every Execute decision, executed or skipped — symmetric for post-mortem.
CREATE TABLE IF NOT EXISTS trade_decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id      TEXT NOT NULL,
    prediction_id INTEGER NOT NULL,
    executed      BOOLEAN NOT NULL,
    risk_reason   TEXT,
    created_at    TIMESTAMP NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id          TEXT NOT NULL,
    prediction_id     INTEGER NOT NULL,
    symbol            TEXT NOT NULL,
    direction         TEXT NOT NULL CHECK (direction IN ('LONG','SHORT')),  -- v1: LONG only
    entry_price       REAL NOT NULL,
    quantity          REAL NOT NULL,
    notional_value    REAL NOT NULL,
    entry_time        TIMESTAMP NOT NULL,
    expected_exit_time TIMESTAMP NOT NULL,
    exited            BOOLEAN NOT NULL DEFAULT 0,
    exit_price        REAL,
    exit_time         TIMESTAMP,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id),
    FOREIGN KEY (symbol) REFERENCES assets(symbol)
);
CREATE INDEX IF NOT EXISTS idx_paper_trades_open
    ON paper_trades(exited, expected_exit_time);

CREATE TABLE IF NOT EXISTS post_mortems (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id         INTEGER NOT NULL,
    direction_correct      BOOLEAN NOT NULL,
    predicted_magnitude_pct REAL NOT NULL,
    actual_magnitude_pct   REAL NOT NULL,
    magnitude_error        REAL NOT NULL,
    simulated_pnl          REAL NOT NULL,
    baseline_pnl           REAL NOT NULL,
    bias_tags              TEXT,   -- JSON array; nullable (PostMortem C3)
    created_at             TIMESTAMP NOT NULL,
    FOREIGN KEY (paper_trade_id) REFERENCES paper_trades(id)
);

-- One row per cycle: ops + cost bookkeeping. Kept DISTINCT from the Store A
-- cycle header (DT-8.4) — this is domain bookkeeping, not the governance trace.
CREATE TABLE IF NOT EXISTS cycle_runs (
    cycle_id             TEXT PRIMARY KEY,
    started_at           TIMESTAMP NOT NULL,
    ended_at             TIMESTAMP,
    cycle_kind           TEXT NOT NULL CHECK (cycle_kind IN ('live','backtest')),
    llm_calls_made       INTEGER NOT NULL DEFAULT 0,
    llm_tokens_consumed  INTEGER NOT NULL DEFAULT 0,
    settlements_processed INTEGER NOT NULL DEFAULT 0,
    new_predictions      INTEGER NOT NULL DEFAULT 0,
    new_trades           INTEGER NOT NULL DEFAULT 0,
    errors               TEXT   -- JSON array
);
