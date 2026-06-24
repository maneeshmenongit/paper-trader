"""LLM-layer error types."""

# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# NOTE: Not listed in the T01 copy table, but router.py (which IS listed)
# imports BudgetExhaustedError from here. Copied as a required dependency
# so router.py imports cleanly. See T01 gate report deviations.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────


class BudgetExhaustedError(Exception):
    """Raised when a call would exceed the per-cycle token budget."""
