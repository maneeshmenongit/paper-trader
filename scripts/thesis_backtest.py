"""CLI: python scripts/thesis_backtest.py [--n-samples N] [--max-calls M]
                                          [--seed S] [--threshold-pp T]
                                          [--min-points P]

The Phase 0.5 GO/NO-GO gate. Runs the full backtest end-to-end:
1. Load cached OHLCV (run scripts/fetch_backtest_data.py first if missing)
2. Sample prediction points
3. Compute baseline predictions for each point
4. Call Gemini for each point (cached on disk)
5. Score both, compare
6. Print + save the GO/NO-GO report

Default thresholds (operator can override):
    --threshold-pp 3.0    # LLM must beat baseline by >= 3 percentage points
    --min-points 200      # need at least 200 evaluated predictions

Exit code:
    0 if PASS (proceed to T05)
    1 if FAIL (do not proceed without operator review)
    2 if RUN INCOMPLETE (cache populated, re-run to continue)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from paper_trader.backtest import evaluation, historical_fetch, llm_eval
from paper_trader.backtest.baseline import momentum_prediction
from paper_trader.backtest.sample import sample_prediction_points
from paper_trader.backtest.universe import DEFAULT_UNIVERSE

REPORTS_DIR = Path("data/backtest/reports")


def _pct(n: int, d: int) -> str:
    return f"{(100 * n / d):.1f}%" if d else "—"


def _build_report(
    *,
    args_str: str,
    cmp: evaluation.ComparisonResult,
    points,
    llm_records: list[dict],
    baseline_dirs: list[str],
    verdict: str,
    threshold_pp: float,
    min_points: int,
    sample_h: str,
    timestamp: str,
    incomplete_reason: str | None,
) -> str:
    dates = [p.prediction_date for p in points]
    earliest = min(dates).date() if dates else "—"
    latest = max(dates).date() if dates else "—"

    # LLM behavior breakdown (over all attempted records).
    llm_total = len(llm_records)
    counts = {"UP": 0, "DOWN": 0, "HOLD": 0, "ERROR": 0}
    conf_sum, conf_n = 0.0, 0
    for r in llm_records:
        d = r["direction"]
        counts[d] = counts.get(d, 0) + 1
        if d in ("UP", "DOWN"):
            conf_sum += float(r.get("confidence", 0.0))
            conf_n += 1
    mean_conf = (conf_sum / conf_n) if conf_n else 0.0

    # Baseline behavior (always UP or DOWN, never HOLD/ERROR).
    base_counts = {"UP": baseline_dirs.count("UP"), "DOWN": baseline_dirs.count("DOWN")}

    # Per-symbol breakdown over overlapping (both non-HOLD) points.
    by_symbol: dict[str, dict[str, int]] = {}
    llm_by_key = {(r["symbol"], r["prediction_date"]): r["direction"] for r in llm_records}
    for p, base_dir in zip(points, baseline_dirs, strict=False):
        key = (p.symbol, p.prediction_date.isoformat())
        llm_dir = llm_by_key.get(key)
        if llm_dir is None:
            continue
        s = by_symbol.setdefault(
            p.symbol, {"llm_n": 0, "llm_hit": 0, "base_n": 0, "base_hit": 0}
        )
        if llm_dir in ("UP", "DOWN"):
            s["llm_n"] += 1
            s["llm_hit"] += int(llm_dir == p.actual_direction)
        s["base_n"] += 1
        s["base_hit"] += int(base_dir == p.actual_direction)

    per_symbol_rows = []
    for sym in sorted(by_symbol):
        s = by_symbol[sym]
        llm_hr = (s["llm_hit"] / s["llm_n"]) if s["llm_n"] else 0.0
        base_hr = (s["base_hit"] / s["base_n"]) if s["base_n"] else 0.0
        edge = (llm_hr - base_hr) * 100
        per_symbol_rows.append(
            f"| {sym} | {s['llm_hit']}/{s['llm_n']} | {s['base_hit']}/{s['base_n']} | {edge:+.1f} |"
        )
    per_symbol_table = "\n".join(per_symbol_rows) if per_symbol_rows else "| (none) | | | |"

    if verdict == "PASS":
        recommendation = (
            "The LLM cleared the threshold. Recommend proceeding to T05 (domain models)\n"
            "and the full Phase 1 build."
        )
    elif verdict == "FAIL":
        recommendation = (
            "The LLM did NOT clear the threshold. Do NOT proceed to T05 without operator\n"
            "review. Possible next steps: revise the prompt and re-run; revise the\n"
            "universe; revise the threshold; or kill the project. The cost of stopping\n"
            "here is small; the cost of building the full system on a broken thesis is\n"
            "multiple weeks."
        )
    else:  # INCOMPLETE
        recommendation = (
            "Hit max_calls cap before evaluating the full sample. Re-run the same command\n"
            f"to continue from the cache. ({incomplete_reason})"
        )

    return f"""# Thesis Validation Backtest — {timestamp}

**Run command:** `{args_str}`
**Sample size:** {len(points)}
**Distinct symbols:** {len({p.symbol for p in points})}
**Distinct trading days:** {len({p.prediction_date.normalize() for p in points})}
**Date range:** {earliest} to {latest}

## Summary

- Baseline hit rate: {cmp.baseline.hit_rate * 100:.1f}%
- LLM hit rate: {cmp.llm.hit_rate * 100:.1f}%
- Edge (LLM − baseline): {cmp.edge_pp:+.1f} percentage points
- Threshold: {threshold_pp:.1f} percentage points
- Minimum points required: {min_points} (evaluated: {cmp.llm.n_predictions})
- **Verdict: {verdict}**

## Detail

### LLM behavior
- Total predictions made: {llm_total}
- UP: {counts['UP']} ({_pct(counts['UP'], llm_total)})
- DOWN: {counts['DOWN']} ({_pct(counts['DOWN'], llm_total)})
- HOLD: {counts['HOLD']} ({_pct(counts['HOLD'], llm_total)})  ← abstentions
- ERROR: {counts['ERROR']} ({_pct(counts['ERROR'], llm_total)})
- Mean confidence (UP/DOWN only): {mean_conf:.2f}

### Baseline behavior
- Total predictions made: {len(baseline_dirs)}
- UP: {base_counts['UP']} ({_pct(base_counts['UP'], len(baseline_dirs))})
- DOWN: {base_counts['DOWN']} ({_pct(base_counts['DOWN'], len(baseline_dirs))})
- HOLD: 0 (baseline never abstains)
- ERROR: 0
- Mean confidence (UP/DOWN only): n/a (deterministic momentum rule)

### Head-to-head (only on points where both made a non-HOLD prediction)
- N overlapping: {cmp.n_overlapping_predictions}
- LLM correct, baseline wrong: {cmp.n_llm_beat_baseline}
- Baseline correct, LLM wrong: {cmp.n_baseline_beat_llm}
- Both correct: {cmp.n_both_correct}
- Both wrong: {cmp.n_both_wrong}

### Per-symbol breakdown
| Symbol | LLM hits / N | Baseline hits / N | Edge (pp) |
|---|---|---|---|
{per_symbol_table}

## Recommendation

{recommendation}

## Artifacts

- Sample hash: {sample_h}
- LLM cache: `data/backtest/llm_predictions/{sample_h}.jsonl`
- OHLCV cache: `data/backtest/historical/`
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 0.5 thesis validation GO/NO-GO gate.")
    parser.add_argument("--n-samples", type=int, default=500)
    parser.add_argument("--max-calls", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threshold-pp", type=float, default=3.0)
    parser.add_argument("--min-points", type=int, default=200)
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set (.env or environment).", file=sys.stderr)
        return 1

    # 1. Load cached OHLCV.
    ohlcv = historical_fetch.load_cached(DEFAULT_UNIVERSE)
    if not ohlcv:
        print(
            "ERROR: no cached OHLCV found. Run `python scripts/fetch_backtest_data.py` first.",
            file=sys.stderr,
        )
        return 1
    logging.info("loaded OHLCV for %d symbols", len(ohlcv))

    # 2. Sample prediction points.
    points = sample_prediction_points(ohlcv, n_samples=args.n_samples, seed=args.seed)
    logging.info("sampled %d prediction points", len(points))

    # 3. Baseline predictions for each point.
    baseline_dirs: list[str] = []
    for p in points:
        df = ohlcv[p.symbol].sort_index()
        try:
            baseline_dirs.append(momentum_prediction(df, p.prediction_date))
        except ValueError:
            baseline_dirs.append("DOWN")  # 30-day window guarantees history; safety net

    # 4. LLM predictions (cached on disk).
    sample_h = llm_eval.sample_hash(points)
    llm_records = llm_eval.evaluate_sample(
        points, api_key=api_key, max_calls=args.max_calls, model_name=args.model
    )

    # Align LLM predictions to the sampled points; missing = not yet evaluated (cap hit).
    llm_by_key = {(r["symbol"], r["prediction_date"]): r["direction"] for r in llm_records}
    llm_dirs: list[str | None] = []
    n_unevaluated = 0
    for p in points:
        d = llm_by_key.get((p.symbol, p.prediction_date.isoformat()))
        if d is None:
            n_unevaluated += 1
            llm_dirs.append(None)
        else:
            # HOLD and ERROR drop out of the hit-rate denominator.
            llm_dirs.append(d if d in ("UP", "DOWN") else None)

    base_dirs_opt: list[str | None] = list(baseline_dirs)
    cmp = evaluation.compare(llm_dirs, base_dirs_opt, points)

    # 5/6. Verdict.
    incomplete_reason = None
    if n_unevaluated > 0:
        verdict = "INCOMPLETE"
        incomplete_reason = f"{n_unevaluated} of {len(points)} points not yet evaluated"
    elif cmp.llm.n_predictions < args.min_points:
        verdict = "FAIL"
    elif cmp.edge_pp >= args.threshold_pp:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    args_str = "python scripts/thesis_backtest.py " + " ".join(argv or sys.argv[1:])
    report = _build_report(
        args_str=args_str.strip(),
        cmp=cmp,
        points=points,
        llm_records=llm_records,
        baseline_dirs=baseline_dirs,
        verdict=verdict,
        threshold_pp=args.threshold_pp,
        min_points=args.min_points,
        sample_h=sample_h,
        timestamp=timestamp,
        incomplete_reason=incomplete_reason,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{timestamp}_thesis_report.md"
    report_path.write_text(report)

    print("\n" + "═" * 64)
    print(f"  VERDICT: {verdict}")
    print(f"  Baseline hit rate: {cmp.baseline.hit_rate * 100:.1f}%")
    print(f"  LLM hit rate:      {cmp.llm.hit_rate * 100:.1f}%")
    print(f"  Edge:              {cmp.edge_pp:+.1f} pp (threshold {args.threshold_pp:.1f} pp)")
    print(f"  Evaluated points:  {cmp.llm.n_predictions} (min {args.min_points})")
    if incomplete_reason:
        print(f"  Note:              {incomplete_reason}")
    print(f"  Report:            {report_path}")
    print("═" * 64 + "\n")

    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
