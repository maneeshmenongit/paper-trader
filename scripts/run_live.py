"""CLI: python scripts/run_live.py [--cycles N] [--interval-seconds S]

The local scheduled run harness (Live-Operation T5). Assembles the governed
momentum paper-trader from live config and runs it for a bounded number of cycles,
settling due trades between cycles and writing per-cycle observability (replay
markdown + observer findings) to a run directory.

Local-first — runs on the operator's machine, no VPS. Honors PAPER_TRADER_LIVE_MODE
(off → fakes, fully offline). Secrets/endpoints come from the environment and never
enter the frozen trace.

    --cycles 4               # how many cycles to run (bounded; default 1)
    --interval-seconds 3600  # sleep between cycles (default 1h)
    --run-dir ./data/runs/<ts>   # where artifacts land (default under ./data/runs)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from paper_trader import config as appcfg
from paper_trader.data.clock import LiveClock
from paper_trader.harness.runner import ScheduledRunner
from paper_trader.live.config import load_live_config
from paper_trader.live.providers import build_data_providers, build_llm_router
from paper_trader.live.watchlist import load_watchlist
from paper_trader.llm.budget import TokenBudget
from paper_trader.persistence.db import Database
from paper_trader.persistence.repository import Repository
from steward.storage.seed_skills import seed_v1_skills


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local scheduled paper-trader run harness (T5).")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval-seconds", type=float, default=3600.0)
    p.add_argument("--horizon-hours", type=int, default=24)
    p.add_argument("--token-budget", type=int, default=15000)
    p.add_argument("--starting-cash", type=float, default=100_000.0)
    p.add_argument("--run-dir", type=Path, default=None)
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log = logging.getLogger("paper_trader.run_live")

    cfg = load_live_config()
    log.info("live config: %s", cfg.redacted())

    providers = build_data_providers(cfg)
    clock = providers.clock if cfg.live_mode else LiveClock()

    # A real per-cycle LLM budget the router enforces. In live mode this is the
    # config-selected open-source router; otherwise a fake would be injected in
    # tests (this CLI always builds the real router).
    router = build_llm_router(cfg, TokenBudget(per_cycle_limit=args.token_budget))

    store_a_path = appcfg.store_a_path()
    store_b_path = appcfg.store_b_path()
    registry = appcfg.open_skill_registry()
    # Bootstrap a fresh registry with the five @v1 skills (idempotent — existing
    # versions are skipped). initial-authoring; the gate governs everything after.
    seeded = seed_v1_skills(registry, created_at=clock.now().isoformat())
    if seeded:
        log.info("seeded @v1 skills: %s", seeded)
    store_a = appcfg.open_store_a(store_a_path)
    store_b = appcfg.open_store_b(store_b_path)
    repo = Repository(Database(appcfg.store_a_path().parent / "paper_trader.sqlite"))

    watchlist = load_watchlist(cfg.watchlist_path)
    log.info("watchlist: %s", [a.symbol for a in watchlist])

    run_dir = args.run_dir or (Path("./data/runs") / clock.now().strftime("%Y%m%dT%H%M%S"))

    runner = ScheduledRunner(
        config=cfg, providers=providers, registry=registry, llm_router=router,
        store_a=store_a, store_b=store_b, repo=repo, clock=clock,
        run_dir=run_dir,
        store_a_path=store_a_path, store_b_path=store_b_path, registry_path=registry.path,
        watchlist=watchlist,
        horizon_hours=args.horizon_hours, token_budget=args.token_budget,
        starting_cash=args.starting_cash, interval_seconds=args.interval_seconds,
    )

    log.info("starting run: %d cycle(s), artifacts → %s", args.cycles, run_dir)
    result = await runner.run(max_cycles=args.cycles)
    log.info("run complete: %d cycle(s)", result.count)
    for c in result.cycles:
        log.info(
            "  %s: settlements=%d trades=%d findings=%d pins_ok=%s",
            c.cycle_id, c.settlements, c.trades_executed, c.findings, c.all_pins_verified,
        )
    if result.final_portfolio is not None:
        log.info("final cash=%.2f realized_pnl=%.2f",
                 result.final_portfolio.cash_balance, result.final_portfolio.realized_pnl)


if __name__ == "__main__":
    asyncio.run(_main())
