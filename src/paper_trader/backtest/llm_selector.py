"""LLM method-selector — the R4 path for the Stage 1 backtest (step 3).

STAGE1_BUILD_PROMPT §4.B: given ≥ 2 eligible methods and point-in-time context, ask
the LLM to pick ONE method. Records ``selection_mode`` (``rule`` when 0/1 eligible,
``llm`` when ≥ 2 — matching live R1–R4) and ``selection_rationale``. Enforces the C1
confidence floor (≥ 0.60 → View, else abstain / don't-enter).

Hard constraints honored:
- **Equal-information, no news (§2.2).** The context is reconstructable from cached
  daily bars ONLY: the three methods' forecasts + eligibility, plus price-derived
  features (recent return, volatility, RSI-ish). No Research/news bundle — that is a
  known Stage-3 delta, flagged in the gate report, never smuggled in here.
- **No post-decision data (§2.3).** The feature builder is fed only
  ``closes_through_decision`` (bars strictly before the exit). The realized outcome
  is structurally unreachable from this module.
- **Fixed, versioned prompt (§5).** ``SELECTION_PROMPT_VERSION`` + the frozen system
  prompt below; iterating the prompt to flip a verdict is forbidden (§2.4).
- **Caching (§5).** Keyed on (symbol, decision_date, eligible-set, feature-hash);
  re-runs are free and stable.

The router seam: this module calls ``router.call("predict_selection", ...)``. The
purpose string is passed as-is; the ``ConfigurableLLMRouter`` routes any unmapped
purpose to its ``default`` chain (point the stronger model there — §4.B). We do NOT
edit the frozen ``LLMPurpose`` Literal (oracle provenance); a local Protocol types
the seam instead.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from paper_trader.backtest.methods import MethodForecast
from paper_trader.backtest.null_selector import Selection, eligible_methods

SELECTION_PROMPT_VERSION = "stage1-selector-v1"
PREDICT_SELECTION_PURPOSE = "predict_selection"
CONFIDENCE_FLOOR = 0.60  # C1: below → abstain (NoView / don't-enter)

_SELECTION_SYSTEM_PROMPT = (
    "You are a forecasting-method selector for a long-only paper trader. You do NOT "
    "predict prices. Given several eligible mechanical methods (momentum, "
    "mean_reversion, arima) and point-in-time price features, choose the ONE method "
    "most likely to be correct for the next trading day. Reply with ONLY compact JSON: "
    '{\"method\": \"<name>\", \"confidence\": <0..1>, \"rationale\": \"<short>\"}. '
    "Choose only from the eligible methods listed. No prose outside the JSON."
)


class SelectorRouter(Protocol):
    """The minimal router surface the selector needs (structural match to both
    ``ConfigurableLLMRouter`` and the test fake). Avoids importing/extending the
    frozen ``LLMPurpose`` Literal."""

    def call(
        self, purpose: str, system: str, user: str,
        max_tokens: int = ..., json_mode: bool = ...,
    ) -> tuple[str, int]: ...


class MaxCallsExceededError(RuntimeError):
    """The ``--max-calls`` budget was hit → the run is INCOMPLETE (first-class)."""


class LLMUnavailableError(RuntimeError):
    """The LLM provider could not be reached / all providers failed on a call.

    Distinct from a low-confidence abstention: this is an INFRASTRUCTURE failure
    (endpoint down, every provider in the chain errored), so the run halts cleanly
    rather than fabricating a pick or dumping a transport traceback.
    """


@dataclass
class LLMSelectorStats:
    calls: int = 0
    cache_hits: int = 0
    tokens: int = 0
    abstained_low_confidence: int = 0


def build_features(closes: list[float]) -> dict[str, float]:
    """Point-in-time, price-derived features from PRE-DECISION closes only.

    No news, no post-decision bar. Deterministic; also the cache-key input.
    """
    last = closes[-1]
    ret_1 = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 and closes[-2] else 0.0
    window = closes[-20:]
    sma20 = sum(window) / len(window)
    vol = statistics.pstdev(closes[-20:]) if len(closes) >= 2 else 0.0
    ret_5 = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 and closes[-6] else 0.0
    return {
        "last_close": round(last, 4),
        "return_1d_pct": round(ret_1 * 100, 4),
        "return_5d_pct": round(ret_5 * 100, 4),
        "gap_to_sma20_pct": round(((last - sma20) / sma20 * 100) if sma20 else 0.0, 4),
        "volatility_20d": round(vol, 4),
    }


def _feature_hash(features: dict[str, float], eligible: list[str]) -> str:
    payload = json.dumps({"f": features, "e": eligible}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def cache_key(symbol: str, decision_date: datetime, eligible: list[str],
              features: dict[str, float]) -> str:
    fh = _feature_hash(features, eligible)
    return f"{symbol}|{decision_date.date()}|{'+'.join(eligible)}|{fh}"


def _build_user_prompt(
    symbol: str, forecasts: dict[str, MethodForecast],
    eligible: list[str], features: dict[str, float],
) -> str:
    method_lines = [
        f"  {m}: direction={forecasts[m].direction}, "
        f"magnitude_pct={forecasts[m].magnitude_pct:.3f}"
        for m in eligible
    ]
    return (
        f"symbol: {symbol}\n"
        f"eligible methods: {', '.join(eligible)}\n"
        "method forecasts:\n" + "\n".join(method_lines) + "\n"
        f"price features (point-in-time): {json.dumps(features, sort_keys=True)}\n"
        "Pick the single best method."
    )


def _parse_selection(text: str, eligible: list[str]) -> tuple[str | None, float, str | None]:
    """Parse the JSON reply; tolerate stray prose around it. Returns
    (method or None, confidence, rationale). An unparseable/off-menu pick → None."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None, 0.0, None
    method = data.get("method")
    if method not in eligible:
        return None, 0.0, None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    rationale = data.get("rationale")
    return method, conf, (str(rationale) if rationale is not None else None)


class LLMSelector:
    """Selects among eligible methods; LLM only on the R4 (≥2 eligible) path."""

    def __init__(
        self,
        router: SelectorRouter,
        *,
        max_calls: int | None = None,
        cache: dict[str, tuple[str | None, float, str | None]] | None = None,
    ):
        self.router = router
        self.max_calls = max_calls
        self.cache = cache if cache is not None else {}
        self.stats = LLMSelectorStats()

    def select(
        self,
        symbol: str,
        forecasts: dict[str, MethodForecast],
        closes: list[float],
        decision_date: datetime,
    ) -> Selection:
        elig = eligible_methods(forecasts)
        # R1/R2: zero eligible → abstain. R3: exactly one → rule-select it (no LLM).
        if not elig:
            return Selection(method=None, selection_mode="rule", rationale="no_eligible")
        if len(elig) == 1:
            return Selection(method=elig[0], selection_mode="rule", rationale="single_eligible")

        # R4: ≥ 2 eligible → LLM selection.
        features = build_features(closes)
        key = cache_key(symbol, decision_date, elig, features)
        if key in self.cache:
            self.stats.cache_hits += 1
            method, conf, rationale = self.cache[key]
        else:
            if self.max_calls is not None and self.stats.calls >= self.max_calls:
                raise MaxCallsExceededError(
                    f"max-calls cap {self.max_calls} reached — run is INCOMPLETE"
                )
            user = _build_user_prompt(symbol, forecasts, elig, features)
            try:
                text, tokens = self.router.call(
                    PREDICT_SELECTION_PURPOSE, _SELECTION_SYSTEM_PROMPT, user,
                    max_tokens=200, json_mode=True,
                )
            except (MaxCallsExceededError, LLMUnavailableError):
                raise
            except Exception as exc:  # noqa: BLE001 — infra failure → clean halt
                raise LLMUnavailableError(
                    f"LLM provider call failed ({type(exc).__name__}: {exc})"
                ) from exc
            self.stats.calls += 1
            self.stats.tokens += tokens
            method, conf, rationale = _parse_selection(text, elig)
            self.cache[key] = (method, conf, rationale)

        # Unparseable / off-menu → abstain (don't-enter), never a fabricated pick.
        if method is None:
            return Selection(method=None, selection_mode="llm", rationale="unparseable_or_offmenu")
        # C1 confidence floor: below → NoView / don't-enter.
        if conf < CONFIDENCE_FLOOR:
            self.stats.abstained_low_confidence += 1
            return Selection(method=None, selection_mode="llm",
                             rationale=f"below_confidence_floor({conf:.2f})")
        return Selection(method=method, selection_mode="llm", rationale=rationale)
