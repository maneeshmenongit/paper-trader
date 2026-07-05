"""Four-store connection discipline (DT-8.5, Steward Wave 1).

FRAMEWORK layer (DC-1). The lesson generalized from oracle-agents (reconcile
§, "four stores, four connection paths, never co-mingled"): each store lives in
its own SQLite file on its own connection path, and no two paths ever coincide.

The framework opens connections by INJECTED path; it never hardcodes where
instance data lives (spec §4.5 / DC-1). This factory therefore takes every path
as an argument — choosing the actual locations (env vars, data dir) is the
application's job, not the framework's.

Physical paths accounted for (five, per the DT-8.5 note plus the skill-version
registry as the fifth):

  1. checkpointer   — crash recovery (LangGraph checkpointer; app-owned)
  2. app_db         — paper_trader.sqlite domain history (app-owned)
  3. store_a        — execution trace (immutable)         -> StoreA
  4. store_b        — correction ledger (append-only)      -> StoreB
  5. skill_registry — skill-version table + currency pointer -> SkillVersionRegistry

The two governance record stores (A, B) and the skill-version registry are
framework record-shaped, so the factory constructs them. The checkpointer and
app db are application infrastructure — the factory holds their paths ONLY to
enforce the never-co-mingled invariant across all five, and hands the raw paths
back for the app to open with its own machinery.
"""

from __future__ import annotations

from pathlib import Path

from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB


class CoMingledStoreError(ValueError):
    """Raised when two stores are asked to share a physical path."""


class StoreConnections:
    """Opens each store on its own injected path; forbids co-mingling.

    Construct with five distinct paths. Governance stores (A, B, skill registry)
    are opened eagerly (schema applied on first construction). The checkpointer
    and app-db paths are validated for distinctness and exposed as ``Path``s for
    the application to open itself.
    """

    def __init__(
        self,
        *,
        checkpointer_path: Path,
        app_db_path: Path,
        store_a_path: Path,
        store_b_path: Path,
        skill_registry_path: Path,
    ):
        paths = {
            "checkpointer": Path(checkpointer_path),
            "app_db": Path(app_db_path),
            "store_a": Path(store_a_path),
            "store_b": Path(store_b_path),
            "skill_registry": Path(skill_registry_path),
        }
        self._assert_distinct(paths)

        # App-owned paths: held for the distinctness guarantee, opened by the app.
        self.checkpointer_path = paths["checkpointer"]
        self.app_db_path = paths["app_db"]

        # Framework governance stores: one connection path each, opened here.
        self.store_a = StoreA(paths["store_a"])
        self.store_b = StoreB(paths["store_b"])
        self.skill_registry = SkillVersionRegistry(paths["skill_registry"])

    @staticmethod
    def _assert_distinct(paths: dict[str, Path]) -> None:
        """Every store must have its own path. Never co-mingled."""
        seen: dict[Path, str] = {}
        for name, path in paths.items():
            resolved = path.resolve()
            if resolved in seen:
                raise CoMingledStoreError(
                    f"stores '{seen[resolved]}' and '{name}' share a path: {resolved}"
                )
            seen[resolved] = name

    @property
    def paths(self) -> dict[str, Path]:
        """The five physical paths, keyed by store name."""
        return {
            "checkpointer": self.checkpointer_path,
            "app_db": self.app_db_path,
            "store_a": self.store_a.path,
            "store_b": self.store_b.path,
            "skill_registry": self.skill_registry.path,
        }
