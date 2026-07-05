"""Unit tests for the backtest humble prompt template. No real Gemini calls."""

from __future__ import annotations

import json

import pandas as pd

from paper_trader.backtest.llm_eval import _parse_response
from paper_trader.backtest.llm_prompt import build_prompt


def _history(n: int = 35) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=n, name="Date")
    return pd.DataFrame(
        {
            "Open": [float(i) for i in range(n)],
            "High": [float(i) + 1 for i in range(n)],
            "Low": [float(i) - 1 for i in range(n)],
            "Close": [float(i) + 0.5 for i in range(n)],
            "Volume": [1_000_000 + i for i in range(n)],
        },
        index=idx,
    )


def test_prompt_includes_symbol_and_date():
    prompt = build_prompt("AAPL", pd.Timestamp("2024-02-15"), _history())
    assert "Symbol: AAPL" in prompt
    assert "As-of date: 2024-02-15" in prompt
    assert "UP" in prompt and "DOWN" in prompt and "HOLD" in prompt


def test_prompt_caps_history_at_30_rows():
    prompt = build_prompt("AAPL", pd.Timestamp("2024-02-15"), _history(35))
    # Header line + 30 data rows (the table is limited to the last 30 days).
    table_lines = [ln for ln in prompt.splitlines() if "|" in ln]
    data_rows = [ln for ln in table_lines if ln.startswith("2024-")]
    assert len(data_rows) == 30


def test_prompt_table_has_expected_columns():
    prompt = build_prompt("AAPL", pd.Timestamp("2024-02-15"), _history())
    assert "date | open | high | low | close | volume" in prompt


def test_prompt_is_valid_format_string_no_stray_braces():
    # The template uses {{ }} for the literal JSON braces; build_prompt must not raise.
    prompt = build_prompt("MSFT", pd.Timestamp("2024-03-01"), _history())
    assert '"direction"' in prompt
    assert '"confidence"' in prompt


def test_parse_response_valid_json():
    text = json.dumps({"direction": "up", "confidence": 0.7, "reasoning": "momentum"})
    direction, conf, reason = _parse_response(text)
    assert direction == "UP"
    assert conf == 0.7
    assert reason == "momentum"


def test_parse_response_strips_markdown_fence():
    text = "```json\n{\"direction\": \"DOWN\", \"confidence\": 0.6, \"reasoning\": \"x\"}\n```"
    direction, conf, _ = _parse_response(text)
    assert direction == "DOWN"
    assert conf == 0.6


def test_parse_response_invalid_direction_is_error():
    text = json.dumps({"direction": "SIDEWAYS", "confidence": 0.5, "reasoning": "x"})
    direction, _, _ = _parse_response(text)
    assert direction == "ERROR"


def test_parse_response_unparseable_is_error():
    direction, conf, _ = _parse_response("not json at all")
    assert direction == "ERROR"
    assert conf == 0.0
