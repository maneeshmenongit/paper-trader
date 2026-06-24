"""Unit tests for the LLM eval loop: cache reuse and the hard call cap.

No real Gemini calls — the client factory and call function are monkeypatched.
"""

from __future__ import annotations

import pandas as pd
import pytest

from paper_trader.backtest import llm_eval
from paper_trader.backtest.sample import PredictionPoint


def _points(n: int) -> list[PredictionPoint]:
    pts = []
    for i in range(n):
        ts = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
        pts.append(
            PredictionPoint(
                symbol=f"SYM{i}",
                prediction_date=ts,
                target_date=ts + pd.Timedelta(days=1),
                history_window=pd.DataFrame(
                    {
                        "Open": [1.0],
                        "High": [1.0],
                        "Low": [1.0],
                        "Close": [1.0],
                        "Volume": [1],
                    },
                    index=pd.DatetimeIndex([ts], name="Date"),
                ),
                actual_direction="UP",
                actual_magnitude_pct=1.0,
            )
        )
    return pts


@pytest.fixture(autouse=True)
def _stub_gemini(monkeypatch):
    """Stub the client factory and call so no network happens; count calls."""
    calls = {"n": 0}

    def fake_make_client(api_key):
        return object()

    def fake_call(client, model_name, prompt):
        calls["n"] += 1
        return '{"direction": "UP", "confidence": 0.8, "reasoning": "stub"}'

    monkeypatch.setattr(llm_eval, "_make_client", fake_make_client)
    monkeypatch.setattr(llm_eval, "_call_gemini", fake_call)
    return calls


def test_evaluates_all_points_when_under_cap(tmp_path, _stub_gemini):
    pts = _points(5)
    results = llm_eval.evaluate_sample(
        pts, api_key="x", max_calls=100, cache_dir=tmp_path, delay_seconds=0.0
    )
    assert len(results) == 5
    assert all(r["direction"] == "UP" for r in results)
    assert _stub_gemini["n"] == 5


def test_cache_reused_on_second_run_no_new_calls(tmp_path, _stub_gemini):
    pts = _points(5)
    llm_eval.evaluate_sample(pts, api_key="x", max_calls=100, cache_dir=tmp_path, delay_seconds=0.0)
    assert _stub_gemini["n"] == 5
    # Second run: identical sample → all from cache, zero new calls.
    results = llm_eval.evaluate_sample(
        pts, api_key="x", max_calls=100, cache_dir=tmp_path, delay_seconds=0.0
    )
    assert len(results) == 5
    assert _stub_gemini["n"] == 5  # unchanged


def test_hard_cap_stops_and_saves_partial(tmp_path, _stub_gemini):
    pts = _points(10)
    results = llm_eval.evaluate_sample(
        pts, api_key="x", max_calls=4, cache_dir=tmp_path, delay_seconds=0.0
    )
    assert len(results) == 4
    assert _stub_gemini["n"] == 4
    # Partial progress persisted; resuming evaluates only the remaining 6.
    results2 = llm_eval.evaluate_sample(
        pts, api_key="x", max_calls=100, cache_dir=tmp_path, delay_seconds=0.0
    )
    assert len(results2) == 10
    assert _stub_gemini["n"] == 10  # 4 + 6 new


def test_sample_hash_stable_and_content_sensitive():
    # Same sample (same points, same order) → same hash; different sample → different.
    # Order matters: the hash is over the ordered list, and sample_prediction_points
    # is deterministic for a given seed, so the order is stable across runs.
    assert llm_eval.sample_hash(_points(3)) == llm_eval.sample_hash(_points(3))
    assert llm_eval.sample_hash(_points(3)) != llm_eval.sample_hash(_points(4))
    assert llm_eval.sample_hash(_points(3)) != llm_eval.sample_hash(list(reversed(_points(3))))
