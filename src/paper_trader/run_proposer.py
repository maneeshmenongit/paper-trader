"""Proposer entry point (DT-11.3, Wave 4).

A SEPARATE, slow-cadence entry point (manual/weekly — "weeks, not cycles"),
NOT part of any trading cycle. Wires app config to the framework proposer:
reads Store B + current skill versions, drafts ONE PROPOSED record, enforcing the
one-proposal-at-a-time guard and cite-never-assert.

It NEVER approves, forks, or flips anything (Wave 5). Reads only Store B + the
skill registry; never touches the fast loop or the app db.

Usage (illustrative): a human runs this on the slow cadence to draft a proposal
against a skill for which the ledger has accumulated evidence.
"""

from __future__ import annotations

from typing import Any

from paper_trader.config import (
    APPLICATION_ID,
    open_proposal_store,
    open_store_b,
)
from steward.officer.proposer import Proposer


def make_proposer(*, clock: Any, narrator: Any | None = None) -> Proposer:
    """Build a Proposer wired to the app-configured Store B + proposal store."""
    return Proposer(
        store_b=open_store_b(),
        proposal_store=open_proposal_store(),
        application_id=APPLICATION_ID,
        clock=clock,
        narrator=narrator,
    )
