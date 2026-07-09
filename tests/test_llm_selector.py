"""Stage 1 LLM selector (step 3): R4 gating, C1 floor, caching, max-calls, no leak."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from paper_trader.backtest.llm_selector import (
    CONFIDENCE_FLOOR,
    LLMSelector,
    MaxCallsExceededError,
    build_features,
    cache_key,
)
from paper_trader.backtest.methods import MethodForecast

D = datetime(2026, 3, 2, tzinfo=UTC)
CLOSES = [100.0 + i * 0.5 for i in range(30)]


class FakeRouter:
    """Deterministic selector router: returns a scripted JSON, counts calls."""

    def __init__(self, method="arima", confidence=0.9, tokens=42, raw=None):
        self.method, self.confidence, self.tokens, self.raw = method, confidence, tokens, raw
        self.calls = 0

    def call(self, purpose, system, user, max_tokens=200, json_mode=False):
        self.calls += 1
        assert purpose == "predict_selection"
        # The user prompt must NEVER contain a post-decision/realized field.
        assert "exit_price" not in user and "actual" not in user and "realized" not in user
        if self.raw is not None:
            return self.raw, self.tokens
        body = json.dumps({"method": self.method, "confidence": self.confidence,
                           "rationale": "test"})
        return body, self.tokens


def _fc(**elig):
    out = {}
    for name in ("momentum", "mean_reversion", "arima"):
        e = elig.get(name, False)
        out[name] = MethodForecast(direction="UP" if e else "HOLD", magnitude_pct=1.0, eligible=e)
    return out


# ─── R3/R4 gating: LLM fires only on ≥2 eligible ─────────────────────────

def test_no_llm_call_when_single_eligible():
    r = FakeRouter()
    sel = LLMSelector(r).select("AAPL", _fc(momentum=True), CLOSES, D)
    assert r.calls == 0
    assert sel.selection_mode == "rule" and sel.method == "momentum"


def test_no_llm_call_when_none_eligible():
    r = FakeRouter()
    sel = LLMSelector(r).select("AAPL", _fc(), CLOSES, D)
    assert r.calls == 0 and sel.method is None


def test_llm_fires_on_two_eligible():
    r = FakeRouter(method="arima")
    sel = LLMSelector(r).select("AAPL", _fc(momentum=True, arima=True), CLOSES, D)
    assert r.calls == 1
    assert sel.selection_mode == "llm" and sel.method == "arima"


# ─── C1 confidence floor ─────────────────────────────────────────────────

def test_below_confidence_floor_abstains():
    r = FakeRouter(method="arima", confidence=CONFIDENCE_FLOOR - 0.01)
    sel = LLMSelector(r).select("AAPL", _fc(momentum=True, arima=True), CLOSES, D)
    assert sel.method is None and "below_confidence_floor" in sel.rationale


def test_at_confidence_floor_enters():
    r = FakeRouter(method="arima", confidence=CONFIDENCE_FLOOR)
    sel = LLMSelector(r).select("AAPL", _fc(momentum=True, arima=True), CLOSES, D)
    assert sel.method == "arima"


# ─── off-menu / unparseable → abstain, never fabricate ───────────────────

def test_offmenu_pick_abstains():
    r = FakeRouter(method="lstm")  # not an eligible method
    sel = LLMSelector(r).select("AAPL", _fc(momentum=True, arima=True), CLOSES, D)
    assert sel.method is None


def test_unparseable_reply_abstains():
    r = FakeRouter(raw="I think momentum is nice, no JSON here")
    sel = LLMSelector(r).select("AAPL", _fc(momentum=True, arima=True), CLOSES, D)
    assert sel.method is None


# ─── caching ─────────────────────────────────────────────────────────────

def test_cache_prevents_second_call():
    r = FakeRouter()
    sel = LLMSelector(r)
    fc = _fc(momentum=True, arima=True)
    sel.select("AAPL", fc, CLOSES, D)
    sel.select("AAPL", fc, CLOSES, D)  # identical → cache hit
    assert r.calls == 1 and sel.stats.cache_hits == 1


def test_cache_key_stable_and_distinct():
    f = build_features(CLOSES)
    k1 = cache_key("AAPL", D, ["momentum", "arima"], f)
    k2 = cache_key("AAPL", D, ["momentum", "arima"], f)
    k3 = cache_key("MSFT", D, ["momentum", "arima"], f)
    assert k1 == k2 and k1 != k3


# ─── max-calls cap → INCOMPLETE ──────────────────────────────────────────

def test_max_calls_raises():
    r = FakeRouter()
    sel = LLMSelector(r, max_calls=1)
    sel.select("AAPL", _fc(momentum=True, arima=True), CLOSES, D)
    with pytest.raises(MaxCallsExceededError):
        sel.select("MSFT", _fc(momentum=True, arima=True), CLOSES, D)


# ─── no post-decision data in features (§2.3) ────────────────────────────

def test_features_use_only_given_closes():
    # Truncating the closes changes the features → they depend only on input bars,
    # never on any future/realized bar the harness holds separately.
    f_full = build_features(CLOSES)
    f_trunc = build_features(CLOSES[:-1])
    assert f_full != f_trunc
