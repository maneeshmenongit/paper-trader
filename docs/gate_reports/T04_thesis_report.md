# Thesis Validation Backtest — 20260623T223059

**Run command:** `python scripts/thesis_backtest.py --n-samples 500 --max-calls 500`
**Sample size:** 500
**Distinct symbols:** 50
**Distinct trading days:** 469
**Date range:** 2024-08-06 to 2026-06-18

## Summary

- Baseline hit rate: 51.6%
- LLM hit rate: 51.7%
- Edge (LLM − baseline): +0.1 percentage points
- Threshold: 3.0 percentage points
- Minimum points required: 200 (evaluated: 232)
- **Verdict: FAIL**

## Detail

### LLM behavior
- Total predictions made: 500
- UP: 145 (29.0%)
- DOWN: 87 (17.4%)
- HOLD: 268 (53.6%)  ← abstentions
- ERROR: 0 (0.0%)
- Mean confidence (UP/DOWN only): 0.66

### Baseline behavior
- Total predictions made: 500
- UP: 253 (50.6%)
- DOWN: 247 (49.4%)
- HOLD: 0 (baseline never abstains)
- ERROR: 0
- Mean confidence (UP/DOWN only): n/a (deterministic momentum rule)

### Head-to-head (only on points where both made a non-HOLD prediction)
- N overlapping: 232
- LLM correct, baseline wrong: 36
- Baseline correct, LLM wrong: 47
- Both correct: 84
- Both wrong: 65

### Per-symbol breakdown
| Symbol | LLM hits / N | Baseline hits / N | Edge (pp) |
|---|---|---|---|
| AAPL | 2/5 | 4/7 | -17.1 |
| ADBE | 4/5 | 8/9 | -8.9 |
| AFRM | 5/7 | 4/10 | +31.4 |
| AMD | 4/5 | 6/11 | +25.5 |
| AMZN | 1/6 | 5/9 | -38.9 |
| AVGO | 5/9 | 7/13 | +1.7 |
| AXP | 2/4 | 4/6 | -16.7 |
| BAC | 2/7 | 6/12 | -21.4 |
| BLK | 1/2 | 4/5 | -30.0 |
| BYND | 3/4 | 10/15 | +8.3 |
| C | 4/6 | 5/10 | +16.7 |
| COST | 4/4 | 5/9 | +44.4 |
| CRM | 3/7 | 5/12 | +1.2 |
| CSCO | 1/6 | 4/11 | -19.7 |
| DIS | 1/4 | 3/11 | -2.3 |
| ETSY | 1/2 | 4/6 | -16.7 |
| GOOGL | 1/3 | 3/9 | +0.0 |
| GS | 2/2 | 5/6 | +16.7 |
| HD | 2/6 | 6/11 | -21.2 |
| IBM | 3/10 | 8/16 | -20.0 |
| INTC | 1/1 | 5/7 | +28.6 |
| INTU | 3/3 | 5/6 | +16.7 |
| JPM | 1/4 | 5/8 | -37.5 |
| KO | 0/3 | 6/13 | -46.2 |
| MA | 1/4 | 6/9 | -41.7 |
| MCD | 3/5 | 7/14 | +10.0 |
| META | 4/4 | 4/8 | +50.0 |
| MS | 4/8 | 5/13 | +11.5 |
| MSFT | 2/5 | 5/12 | -1.7 |
| NKE | 1/2 | 8/11 | -22.7 |
| NOW | 3/6 | 8/14 | -7.1 |
| NVDA | 2/5 | 5/8 | -22.5 |
| OPEN | 2/2 | 5/8 | +37.5 |
| ORCL | 7/9 | 4/13 | +47.0 |
| PEP | 2/2 | 3/5 | +40.0 |
| PG | 0/2 | 4/7 | -57.1 |
| PINS | 2/4 | 4/11 | +13.6 |
| PLTR | 6/8 | 6/12 | +25.0 |
| PTON | 1/4 | 6/11 | -29.5 |
| QCOM | 3/4 | 6/11 | +20.5 |
| RBLX | 5/6 | 4/7 | +26.2 |
| ROKU | 3/7 | 7/14 | -7.1 |
| SBUX | 0/5 | 3/12 | -25.0 |
| SNAP | 1/4 | 8/12 | -41.7 |
| SOFI | 2/3 | 5/8 | +4.2 |
| TSLA | 2/3 | 1/8 | +54.2 |
| TXN | 1/1 | 5/9 | +44.4 |
| V | 1/5 | 0/9 | +20.0 |
| WFC | 3/4 | 4/9 | +30.6 |
| WMT | 3/5 | 8/13 | -1.5 |

## Recommendation

The LLM did NOT clear the threshold. Do NOT proceed to T05 without operator
review. Possible next steps: revise the prompt and re-run; revise the
universe; revise the threshold; or kill the project. The cost of stopping
here is small; the cost of building the full system on a broken thesis is
multiple weeks.

## Artifacts

- Sample hash: 3b697badade2298d
- LLM cache: `data/backtest/llm_predictions/3b697badade2298d.jsonl`
- OHLCV cache: `data/backtest/historical/`
