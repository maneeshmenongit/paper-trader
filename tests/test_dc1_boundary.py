"""DC-1 boundary test: the one-way import rule.

`steward/` (FRAMEWORK) MUST NOT import from `paper_trader/` (APPLICATION).
Only `paper_trader/` may import `steward/`. A violation is a build error.

This walks every .py file under the steward package, parses its imports with
the `ast` module, and fails if any import references the `paper_trader`
top-level package. An empty steward/ passes trivially.
"""

from __future__ import annotations

import ast
from pathlib import Path

# tests/ -> repo root -> src/steward
STEWARD_ROOT = Path(__file__).resolve().parent.parent / "src" / "steward"

FORBIDDEN_TOP_LEVEL = "paper_trader"


def _steward_py_files() -> list[Path]:
    return sorted(STEWARD_ROOT.rglob("*.py"))


def _imports_forbidden(tree: ast.AST) -> list[str]:
    """Return a list of offending import statements referencing paper_trader."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top == FORBIDDEN_TOP_LEVEL:
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            # Absolute `from paper_trader...` — module is set, level == 0.
            if node.level == 0 and node.module is not None:
                top = node.module.split(".")[0]
                if top == FORBIDDEN_TOP_LEVEL:
                    offenders.append(f"from {node.module} import ...")
    return offenders


def test_steward_does_not_import_paper_trader() -> None:
    violations: list[str] = []
    for py_file in _steward_py_files():
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for offending in _imports_forbidden(tree):
            violations.append(f"{py_file}: {offending}")

    assert not violations, (
        "DC-1 boundary violated — steward/ must not import paper_trader/:\n"
        + "\n".join(violations)
    )
