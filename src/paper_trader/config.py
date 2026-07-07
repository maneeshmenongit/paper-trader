"""Application config.

Governance-store paths wired here:
- SKILL-VERSION REGISTRY (Wave 2.5) — opened READ-ONLY for skill loading.
- STORE A (Wave 3) — the execution-trace file, opened for orchestrator-level
  emission (cycle headers + agent invocations). Emission is non-blocking.
- STORE B (Wave 4) — the correction ledger. The observer half of the officer is
  the ONLY writer (append-only INSERT; no UPDATE/DELETE ever). Wired here so the
  observer can open it by injected path; the proposer opens it READ-ONLY.

The app db + checkpointer paths remain the existing PAPER_TRADER_DB_PATH /
CHECKPOINTER_DB_PATH env vars (unchanged). Five+ stores, five+ paths, never
co-mingled.
"""

from __future__ import annotations

import os
from pathlib import Path

from steward.storage.proposals import ProposalStore
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB

# Env var naming mirrors the existing PAPER_TRADER_DB_PATH / CHECKPOINTER_DB_PATH.
PAPER_TRADER_DB_PATH_ENV = "PAPER_TRADER_DB_PATH"
DEFAULT_PAPER_TRADER_DB_PATH = "./data/paper_trader.sqlite"

SKILL_REGISTRY_PATH_ENV = "SKILL_REGISTRY_DB_PATH"
DEFAULT_SKILL_REGISTRY_PATH = "./data/skills.sqlite"

STORE_A_PATH_ENV = "STORE_A_DB_PATH"
DEFAULT_STORE_A_PATH = "./data/store_a.sqlite"

STORE_B_PATH_ENV = "STORE_B_DB_PATH"
DEFAULT_STORE_B_PATH = "./data/store_b.sqlite"

PROPOSALS_PATH_ENV = "PROPOSALS_DB_PATH"
DEFAULT_PROPOSALS_PATH = "./data/proposals.sqlite"

# The DC-1 application/instance identifier stamped on every governance record.
APPLICATION_ID = "paper-trader"


def paper_trader_db_path() -> Path:
    """Resolve the app-db (domain history) file path from env (with a default).

    The app db is a DISTINCT file from Store A/B, the skill registry, proposals,
    and the checkpointer — five+ stores, five+ paths, never co-mingled.
    """
    return Path(os.environ.get(PAPER_TRADER_DB_PATH_ENV, DEFAULT_PAPER_TRADER_DB_PATH))


def skill_registry_path() -> Path:
    """Resolve the skill-registry file path from env (with a default)."""
    return Path(os.environ.get(SKILL_REGISTRY_PATH_ENV, DEFAULT_SKILL_REGISTRY_PATH))


def open_skill_registry(path: Path | None = None) -> SkillVersionRegistry:
    """Open the skill-version registry for READ-ONLY skill loading.

    The registry object is the framework's; agents use it only to obtain a
    connection for ``steward.storage.skill_loader.load_skill``. No writes occur
    from the application in this wave.
    """
    return SkillVersionRegistry(path or skill_registry_path())


def store_a_path() -> Path:
    """Resolve the Store A (execution-trace) file path from env (with a default)."""
    return Path(os.environ.get(STORE_A_PATH_ENV, DEFAULT_STORE_A_PATH))


def open_store_a(path: Path | None = None) -> StoreA:
    """Open the Store A execution-trace store by injected path.

    The framework helper (steward.storage.store_a.StoreA) creates the file if
    absent and applies the schema. Emission through it is non-blocking (a write
    failure never aborts a cycle). Store A is a DISTINCT file from the app db,
    the checkpointer, the skill registry, and Store B.
    """
    return StoreA(path or store_a_path())


def store_b_path() -> Path:
    """Resolve the Store B (correction ledger) file path from env (with a default)."""
    return Path(os.environ.get(STORE_B_PATH_ENV, DEFAULT_STORE_B_PATH))


def open_store_b(path: Path | None = None) -> StoreB:
    """Open the Store B correction-ledger store by injected path.

    The frozen framework helper (steward.storage.store_b.StoreB) creates the file
    if absent and applies the Wave 1 DDL (append-only + no-mutation triggers). The
    observer is the only writer; the proposer reads. Store B is a DISTINCT file
    from Store A, the app db, the checkpointer, and the skill registry.
    """
    return StoreB(path or store_b_path())


def proposals_path() -> Path:
    """Resolve the proposal-store file path from env (with a default)."""
    return Path(os.environ.get(PROPOSALS_PATH_ENV, DEFAULT_PROPOSALS_PATH))


def open_proposal_store(path: Path | None = None) -> ProposalStore:
    """Open the proposal store by injected path (its own DISTINCT file).

    The proposer writes PROPOSED records here (Wave 4). The APPROVE executor
    (fork + pointer flip + window) is Wave 5 and is not built.
    """
    return ProposalStore(path or proposals_path())
