"""Gemini-driven evaluation loop with cache + progress checkpointing.

Cost discipline (see PAPER_TRADER_T02_T04 §"Critical: Cost Discipline"):
- The caller samples first and only evaluates the sample — never the full grid.
- Predictions are cached to disk keyed by a stable hash of the sample.
- A hard cap (`max_calls`) stops a run cleanly and saves partial progress.
- Progress is checkpointed to the cache file every CHECKPOINT_EVERY calls.
- Calls are sequential with a fixed delay, well under Gemini's rate limit.

SDK note: this module uses the new `google-genai` SDK (`google.genai`), matching
the copied llm/gemini_client.py, rather than the legacy `google-generativeai`
named in the task prompt. See the T04 gate report deviations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

from paper_trader.backtest.llm_prompt import build_prompt
from paper_trader.backtest.sample import PredictionPoint

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/backtest/llm_predictions")
CHECKPOINT_EVERY = 25
DELAY_BETWEEN_CALLS_SECONDS = 1.0

VALID_DIRECTIONS = {"UP", "DOWN", "HOLD"}


def sample_hash(points: list[PredictionPoint]) -> str:
    """Stable hash of the sample so cached results are reused only when the
    sample is identical."""
    payload = json.dumps(
        [(p.symbol, p.prediction_date.isoformat()) for p in points],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _cache_path(points: list[PredictionPoint], cache_dir: Path) -> Path:
    return cache_dir / f"{sample_hash(points)}.jsonl"


def _load_cache(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _append_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _parse_response(text: str) -> tuple[str, float, str]:
    """Parse a Gemini JSON response into (direction, confidence, reasoning).

    Tolerant of stray markdown fences. Returns ('ERROR', 0.0, msg) on failure.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return "ERROR", 0.0, f"unparseable response: {text[:120]!r}"

    direction = str(data.get("direction", "")).upper()
    if direction not in VALID_DIRECTIONS:
        return "ERROR", 0.0, f"invalid direction: {direction!r}"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(data.get("reasoning", ""))[:300]
    return direction, confidence, reasoning


def _make_client(api_key: str):  # noqa: ANN202 — google-genai types are dynamic
    from google import genai

    return genai.Client(api_key=api_key)


def _call_gemini(client, model_name: str, prompt: str) -> str:  # noqa: ANN001
    from google.genai import types

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=300,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    text = ""
    if response.candidates:
        content = response.candidates[0].content
        if content and content.parts:
            for part in content.parts:
                if not getattr(part, "thought", False):
                    text += part.text or ""
    if not text:
        text = response.text or ""
    return text


def evaluate_sample(
    points: list[PredictionPoint],
    api_key: str,
    max_calls: int = 500,
    model_name: str = "gemini-2.5-flash",
    cache_dir: Path = CACHE_DIR,
    delay_seconds: float = DELAY_BETWEEN_CALLS_SECONDS,
) -> list[dict]:
    """For each prediction point, call Gemini and record direction + confidence
    + reasoning.

    Returns one dict per point, in the same order as `points`:
        {"symbol", "prediction_date", "direction", "confidence", "reasoning"}
    where direction is "UP" | "DOWN" | "HOLD" | "ERROR".

    Behavior:
    - Cache hit: load records keyed by (symbol, prediction_date) from disk; only
      points not already cached trigger an LLM call.
    - Cache miss: iterate, checkpointing every CHECKPOINT_EVERY calls, with
      `delay_seconds` between calls.
    - Hard cap: stop after `max_calls` new calls, save partial, return what we have
      (points that were neither cached nor reached are omitted from the result).
    - Per-call errors: record direction="ERROR", continue.
    """
    path = _cache_path(points, cache_dir)
    cached_records = _load_cache(path)
    cached_by_key = {(r["symbol"], r["prediction_date"]): r for r in cached_records}

    results: list[dict] = []
    pending: list[PredictionPoint] = []
    for p in points:
        key = (p.symbol, p.prediction_date.isoformat())
        if key in cached_by_key:
            results.append(cached_by_key[key])
        else:
            pending.append(p)

    if not pending:
        logger.info("cache hit: all %d predictions loaded from %s", len(points), path.name)
        return results

    logger.info(
        "%d cached, %d pending; calling Gemini (cap=%d, delay=%.1fs)",
        len(results),
        len(pending),
        max_calls,
        delay_seconds,
    )

    client = _make_client(api_key)
    calls_made = 0
    new_records: list[dict] = []

    for p in pending:
        if calls_made >= max_calls:
            logger.warning("hit max_calls cap (%d) — saving partial and stopping", max_calls)
            break

        prompt = build_prompt(p.symbol, p.prediction_date, p.history_window)
        try:
            text = _call_gemini(client, model_name, prompt)
            direction, confidence, reasoning = _parse_response(text)
        except Exception as exc:  # noqa: BLE001 — one bad call must not kill the run
            direction, confidence, reasoning = "ERROR", 0.0, f"call failed: {exc}"

        record = {
            "symbol": p.symbol,
            "prediction_date": p.prediction_date.isoformat(),
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
        }
        results.append(record)
        new_records.append(record)
        calls_made += 1

        if len(new_records) >= CHECKPOINT_EVERY:
            _append_records(path, new_records)
            logger.info(
                "checkpoint: %d new records flushed (%d calls so far)",
                len(new_records),
                calls_made,
            )
            new_records = []

        if calls_made < max_calls:
            time.sleep(delay_seconds)

    if new_records:
        _append_records(path, new_records)
        logger.info("final flush: %d new records (%d calls total)", len(new_records), calls_made)

    return results
