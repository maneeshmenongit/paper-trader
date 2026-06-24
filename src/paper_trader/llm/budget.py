"""Per-cycle token budget tracker.

The budget is the cost-discipline mechanism that makes free-tier LLM usage
sustainable. When the budget is exhausted, the supervisor degrades to
deterministic routing — the cycle still completes, it just gets dumber.
"""

# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────


class TokenBudget:
    def __init__(self, per_cycle_limit: int):
        self.per_cycle_limit = per_cycle_limit
        self._used = 0

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self.per_cycle_limit - self._used)

    def has_capacity(self, estimate: int) -> bool:
        return (self._used + estimate) <= self.per_cycle_limit

    def consume(self, tokens: int) -> None:
        self._used += tokens

    def reset(self) -> None:
        self._used = 0
