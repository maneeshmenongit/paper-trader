"""Sanity test that the package imports and basic infra works."""


def test_package_imports():
    import paper_trader
    assert paper_trader.__version__ == "0.1.0"


def test_llm_budget_imports():
    """The copied LLM budget module should import cleanly."""
    from paper_trader.llm import budget
    # Don't instantiate — just confirm the module loads.
    # whichever name oracle-agents used
    assert hasattr(budget, "TokenBudget") or hasattr(budget, "Budget")


def test_agents_base_imports():
    """The copied enforce_writes decorator should import cleanly."""
    from paper_trader.agents import base
    assert hasattr(base, "enforce_writes")
