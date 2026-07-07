"""Local scheduled run harness (Live-Operation T5).

Assembles everything Waves 1–6 + T1–T4 built into a runner that triggers cycles
on a schedule, settles between them, and produces per-cycle observability (logs,
replay markdown, observer findings). Local-first — the operator's machine, no VPS.

- assembly.py     — compose a fully-wired, governed Supervisor from LiveConfig +
                    the provider bundle (the one place the full graph is built for
                    production; the tests were the only prior assembly site).
- observability.py — write per-cycle artifacts (replay markdown, observer
                    findings, a run-summary line) to a run directory.
- runner.py       — the scheduled loop: settle → run cycle → persist → observe,
                    on an interval, bounded and injectable for tests.
"""

from __future__ import annotations

from paper_trader.harness.assembly import GovernedCycle, build_governed_cycle
from paper_trader.harness.observability import CycleObservability, write_cycle_artifacts
from paper_trader.harness.runner import RunResult, ScheduledRunner
from paper_trader.harness.summary import RunSummary, summarize_run

__all__ = [
    "CycleObservability",
    "GovernedCycle",
    "RunResult",
    "RunSummary",
    "ScheduledRunner",
    "build_governed_cycle",
    "summarize_run",
    "write_cycle_artifacts",
]
