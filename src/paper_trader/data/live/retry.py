"""Retry-with-backoff seam for the live data clients (Live-Operation T1).

The Wave 2.5 fakes never needed this — an in-memory dict never rate-limits or
drops a connection. The authority (STEWARD_PAPER_TRADER_LIVE_OPERATION_001 §3 T1)
names a "retry-with-backoff seam" the live clients honor; this is it, made
concrete: one small async helper the three live clients share.

Design constraints (mirroring the rest of the app):
- Clock-free: backoff sleeps a *duration*, it never reads wall-clock time, so it
  introduces no un-injected time dependency into an agent path.
- Politeness bounds stay where they already are — the Research agent owns the
  per-provider ``asyncio.Semaphore`` (yfinance 2; finnhub/coingecko 4). This
  helper adds RETRY, not concurrency; it must not fight the agent's semaphores.
- Deterministic in tests: ``sleep`` is injectable so tests exercise the retry
  path with zero real delay and never touch the network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

# Politeness/backoff defaults. Conservative: a handful of tries with exponential
# spacing, capped, so a flaky provider is ridden out but a hard outage surfaces
# quickly rather than hanging a cycle.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 0.5
DEFAULT_MAX_DELAY_S = 8.0


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Call ``fn`` with exponential backoff, re-raising the last error on give-up.

    ``fn`` is a zero-arg coroutine factory (a thunk) so it can be re-invoked on
    each attempt. Exponential delay: ``base_delay_s * 2**(attempt-1)``, clamped to
    ``max_delay_s``. Only exceptions in ``retry_on`` are retried; anything else
    propagates immediately (a programming error should not be silently retried).

    ``sleep`` is injected so tests drive the retry loop with no real wait. The
    final failure re-raises the original exception — callers decide whether a
    provider miss degrades to empty (Research R1/R2) or aborts.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except retry_on as exc:  # noqa: PERF203 — retry loop, not a hot path
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = min(base_delay_s * (2 ** (attempt - 1)), max_delay_s)
            await sleep(delay)
    assert last_exc is not None  # unreachable: loop ran >= 1 time and did not return
    raise last_exc
