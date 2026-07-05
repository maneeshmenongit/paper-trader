"""Parse effective parameters out of loaded @v1 skill content (Wave 2.5).

The agents are born registry-loading and must drive behavior from the loaded
skill — NO inline thresholds. Skill content in v1 stores thresholds in the rule
PROSE (e.g. "≥ $10M (stocks); 24h volume ≥ $50M (crypto)"), so these helpers
extract the effective numbers from that text. This keeps the skill the single
source of the values; changing a threshold is a gated fork, and the agent picks
up the forked value automatically because it reads it here.

(When rules gain structured params via the slow loop, these parsers are where a
structured lookup would replace the regex — the call sites do not change.)
"""

from __future__ import annotations

import re
from typing import Any


def rule_text(skill: Any, rule_id: str) -> str:
    for r in skill["rules"]:
        if r["id"] == rule_id:
            return str(r["text"])
    raise KeyError(f"rule {rule_id} not in skill")


def _dollar_amount(token: str) -> float:
    """'$10M' -> 10_000_000.0 ; '$50M' -> 50_000_000.0 ; '$100' -> 100.0."""
    m = re.match(r"\$?([\d.]+)\s*([MKB]?)", token.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"cannot parse dollar amount from {token!r}")
    value = float(m.group(1))
    return value * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2).upper()]


def filter_liquidity_floors(skill: Any) -> tuple[float, float]:
    """Return (stock_floor, crypto_floor) in dollars, parsed from Filter R2."""
    text = rule_text(skill, "R2")
    dollars = re.findall(r"\$[\d.]+\s*[MKB]?", text)
    if len(dollars) < 2:
        raise ValueError(f"expected two dollar floors in R2, got {dollars!r}")
    return _dollar_amount(dollars[0]), _dollar_amount(dollars[1])


def filter_quote_freshness_minutes(skill: Any) -> int:
    """Return the max quote age in minutes, parsed from Filter R4."""
    text = rule_text(skill, "R4")
    m = re.search(r"(\d+)\s*minutes?", text)
    if not m:
        raise ValueError(f"no freshness minutes in R4: {text!r}")
    return int(m.group(1))
