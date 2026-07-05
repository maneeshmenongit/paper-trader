"""Reconstructive replay — the read-only reader (DT-13.x, Steward Wave 6).

FRAMEWORK machinery. Replay is a READER, not a runner: it never executes agent
code, never calls an LLM, never touches a provider, never writes or mutates a
record. It reconstructs a cycle from FROZEN records only (G5).

Four-source join on cycle_id:
  (1) the cycle_header               (Store A)
  (2) all agent_invocations, ordered (Store A)
  (3) the pinned skill content per invocation — resolved by the invocation
      record's skill_version_id (NEVER the current currency pointer), so a cycle
      replays under the version it ACTUALLY ran (pre-fork cycles under @v1 even
      after @v2 ships).
  (4) Store B entries for the cycle  (including meaningful silence).

Hash verification (I-8, DT-13.2): each pin's stored content is re-hashed with the
single canonical compute_content_hash and compared to the stored content_hash. A
mismatch marks the pin UNTRUSTED and CONTINUES — never raises. This is
deliberately SOFTER than the Wave 2 runtime loader (which raises): replay is a
human-facing reader, not a trade path. A corrupted row is evidence to see, not an
exception to hide behind.

READ-ONLY BY CONSTRUCTION: every connection is opened at the SQLite connection
level in read-only mode (mode=ro), so a stray write raises.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steward.storage.content_hash import compute_content_hash

VERIFIED = "VERIFIED"
UNTRUSTED = "UNTRUSTED"
MISSING = "MISSING"  # the pinned version row is absent from the registry


def _ro_connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite file strictly READ-ONLY (writes raise). Reconstruction only."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@dataclass(frozen=True)
class ReconstructedInvocation:
    invocation_id: str
    agent_name: str
    skill_version_id: str
    agent_input: Any
    agent_output: Any
    started_at: str
    ended_at: str
    status: str
    # source (3): the pinned skill content + its trust status.
    skill_content: str | None
    trust: str                       # VERIFIED | UNTRUSTED | MISSING
    stored_hash: str | None
    recomputed_hash: str | None


@dataclass(frozen=True)
class Reconstruction:
    cycle_id: str
    header: dict[str, Any] | None                    # source (1)
    invocations: list[ReconstructedInvocation]        # sources (2)+(3)
    ledger_entries: list[dict[str, Any]]              # source (4)
    untrusted_pins: list[str] = field(default_factory=list)

    @property
    def all_verified(self) -> bool:
        return all(i.trust == VERIFIED for i in self.invocations)


class Replay:
    """Read-only reconstructive reader over the frozen governance records."""

    def __init__(self, *, store_a_path: Path, store_b_path: Path, registry_path: Path):
        self.store_a_path = Path(store_a_path)
        self.store_b_path = Path(store_b_path)
        self.registry_path = Path(registry_path)

    def reconstruct(self, cycle_id: str) -> Reconstruction:
        header = self._header(cycle_id)
        invocation_rows = self._invocations(cycle_id)
        ledger = self._ledger(cycle_id)

        # source (3): resolve each pin by the RECORD's skill_version_id, soft-hash.
        with _ro_connect(self.registry_path) as reg:
            invocations = [self._reconstruct_invocation(r, reg) for r in invocation_rows]

        untrusted = [i.skill_version_id for i in invocations if i.trust != VERIFIED]
        return Reconstruction(
            cycle_id=cycle_id, header=header, invocations=invocations,
            ledger_entries=ledger, untrusted_pins=untrusted,
        )

    # ─── the four sources ────────────────────────────────────────────────

    def _header(self, cycle_id: str) -> dict[str, Any] | None:
        with _ro_connect(self.store_a_path) as conn:
            row = conn.execute(
                "SELECT * FROM cycle_headers WHERE cycle_id = ?", (cycle_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def _invocations(self, cycle_id: str) -> list[dict[str, Any]]:
        with _ro_connect(self.store_a_path) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_invocations WHERE cycle_id = ? "
                "ORDER BY invocation_id",
                (cycle_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _ledger(self, cycle_id: str) -> list[dict[str, Any]]:
        with _ro_connect(self.store_b_path) as conn:
            rows = conn.execute(
                "SELECT * FROM ledger_entries WHERE cycle_id = ? ORDER BY entry_id",
                (cycle_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _reconstruct_invocation(
        self, row: dict[str, Any], reg: sqlite3.Connection
    ) -> ReconstructedInvocation:
        version_id = row["skill_version_id"]
        skill_row = reg.execute(
            "SELECT content, content_hash FROM skill_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()

        if skill_row is None:
            content, stored_hash, recomputed, trust = None, None, None, MISSING
        else:
            content = skill_row["content"]
            stored_hash = skill_row["content_hash"]
            recomputed = compute_content_hash(content)
            # I-8: mismatch -> UNTRUSTED + CONTINUE (never raise).
            trust = VERIFIED if recomputed == stored_hash else UNTRUSTED

        return ReconstructedInvocation(
            invocation_id=row["invocation_id"],
            agent_name=row["agent_name"],
            skill_version_id=version_id,
            agent_input=_maybe_json(row["agent_input"]),
            agent_output=_maybe_json(row["agent_output"]),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            status=row["status"],
            skill_content=content,
            trust=trust,
            stored_hash=stored_hash,
            recomputed_hash=recomputed,
        )


def _maybe_json(value: Any) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
