"""Backtest-specific humble prompt for next-day direction prediction.

The production Predict agent (T12) will use a more elaborate prompt that
includes the research bundle (news, sentiment, technicals). For the backtest,
we deliberately give the LLM only the price history — this tests whether
the LLM has signal from price patterns alone, which is the weakest case.

If the LLM beats the baseline using price history alone, adding news and
sentiment in the production system can only help.
"""

from __future__ import annotations

from textwrap import dedent

import pandas as pd

HISTORY_ROWS = 30

HUMBLE_PROMPT_TEMPLATE = dedent("""
    You are evaluating a stock for a directional prediction.

    Symbol: {symbol}
    As-of date: {prediction_date}
    Recent 30-day price history (oldest first):
    {price_history_table}

    Your task: predict whether the closing price on the NEXT trading day
    will be HIGHER (UP) or LOWER (DOWN) than today's close.

    IMPORTANT GUIDANCE:
    - Markets are mostly efficient. Most price moves are noise.
    - Only predict UP or DOWN if the recent price action shows specific,
      strong evidence in one direction.
    - If the evidence is mixed, weak, or you'd be guessing, respond HOLD.
    - It is much better to abstain than to guess.

    Respond in this exact JSON format with no other text:
    {{
      "direction": "UP" | "DOWN" | "HOLD",
      "confidence": 0.0 to 1.0,
      "reasoning": "one sentence"
    }}
""").strip()


def _format_history_table(history: pd.DataFrame) -> str:
    """Render the last 30 rows as a compact pipe-delimited table.

    Columns: date | open | high | low | close | volume. Oldest first.
    """
    rows = history.tail(HISTORY_ROWS)
    lines = ["date | open | high | low | close | volume"]
    for ts, row in rows.iterrows():
        date_str = pd.Timestamp(ts).date().isoformat()
        lines.append(
            f"{date_str} | {row['Open']:.2f} | {row['High']:.2f} | "
            f"{row['Low']:.2f} | {row['Close']:.2f} | {int(row['Volume'])}"
        )
    return "\n".join(lines)


def build_prompt(symbol: str, prediction_date: pd.Timestamp, history: pd.DataFrame) -> str:
    """Format the prompt for one prediction point."""
    table = _format_history_table(history)
    return HUMBLE_PROMPT_TEMPLATE.format(
        symbol=symbol,
        prediction_date=pd.Timestamp(prediction_date).date().isoformat(),
        price_history_table=table,
    )
