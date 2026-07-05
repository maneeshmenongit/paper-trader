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


def _pct(token: str) -> float:
    """'5%' -> 0.05 ; '0.5%' -> 0.005."""
    return float(token.rstrip("%")) / 100.0


def _grp(pattern: str, text: str, group: int = 1) -> str:
    """Search and return a capture group, raising if the skill text lacks it."""
    m = re.search(pattern, text)
    if m is None:
        raise ValueError(f"pattern {pattern!r} not found in skill text: {text!r}")
    return m.group(group)


class ExecuteParams:
    """Effective Execute risk parameters, all parsed from the loaded skill.

    Every value is skill content (G1) — none is hardcoded. Attribute-per-value so
    the agent reads them by name; the mirror-contract (Task 9) checks these equal
    the ratified skill values.
    """

    def __init__(self, skill: Any):
        sizing = rule_text(skill, "sizing")
        exposure = rule_text(skill, "exposure")
        loss_halt = rule_text(skill, "loss_halt")
        gates = rule_text(skill, "execution_gates")

        self.kelly_fraction = float(_grp(r"Kelly\s+([\d.]+)", sizing))
        self.max_position_pct = _pct(_grp(r"max position\s+([\d.]+%)", sizing))
        self.min_notional = _dollar_amount(_grp(r"min notional\s+(\$[\d.]+)", sizing))

        self.max_total_exposure_pct = _pct(_grp(r"max total exposure\s+([\d.]+%)", exposure))
        self.max_same_sector = int(_grp(r"max\s+(\d+)\s+same-sector", exposure))
        self.max_open_positions = int(_grp(r"max\s+(\d+)\s+open positions", exposure))

        self.daily_loss_halt_pct = _pct(_grp(r"daily simulated loss\s*>\s*([\d.]+%)", loss_halt))

        # The FIRST "confidence ≥ X" in the gates rule is the effective floor
        # (the bracketed annotation repeats it, but the operative value is first).
        self.min_confidence = float(_grp(r"confidence\s*≥\s*([\d.]+)", gates))
        self.min_magnitude_pct = _pct(_grp(r"expected magnitude\s*≥\s*([\d.]+%)", gates))
