"""Daily entrypoint. Fires once, shortly after the close.

    python -m alphalab.run --config configs/live.yaml

No event loop, no daemon, no message bus. The competition observes end-of-day
NAV, so a process that runs once a day is not a simplification of the right
architecture -- it is the right architecture.
"""

from __future__ import annotations

import argparse
import csv
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from . import data as data_mod
from .config import Config
from .credentials import Credentials
from .engine import run_day
from .score import score
from .shadow import ShadowBook

LOG = logging.getLogger("alphalab")
NAV_LOG = Path("nav_history.csv")
SHADOW_PATH = Path("data/shadow_book.json")


def append_nav(asof: date, nav: float, path: Path = NAV_LOG) -> pd.Series:
    """Append today's NAV, then return the full committed history.

    This file is committed to git every day on purpose. It is a timestamped,
    append-only record of what the account was worth, written before anyone
    knows how the story ends -- which is what makes the final Sharpe credible
    to anyone reading the repository later.
    """
    existing: dict[str, float] = {}
    if path.exists():
        with path.open() as fh:
            for row in csv.DictReader(fh):
                existing[row["date"]] = float(row["nav"])
    existing[asof.isoformat()] = nav

    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "nav"])
        for key in sorted(existing):
            writer.writerow([key, f"{existing[key]:.2f}"])

    return pd.Series(
        {pd.Timestamp(k): v for k, v in existing.items()}
    ).sort_index()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one trading day.")
    parser.add_argument("--config", default="configs/live.yaml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print orders without sending them",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s"
    )
    config = Config.load(args.config)
    dry_run = args.dry_run or config.dry_run
    credentials = Credentials.load()

    from .brokers.ibkr import IBKRBroker

    LOG.info(
        "account %s | %s | gateway %s:%d",
        credentials.account,
        "DRY RUN (read-only connection)" if dry_run else "LIVE ORDERS",
        config.ibkr_host,
        config.ibkr_port,
    )

    with IBKRBroker(
        host=config.ibkr_host,
        port=config.ibkr_port,
        client_id=config.ibkr_client_id,
        account=credentials.account,
        read_only=dry_run,
    ) as broker:
        prices = data_mod.update_cache(
            data_mod.fetch_from_ibkr(broker, config.universe)
        )

        nav_history = append_nav(broker.today(), broker.net_asset_value())
        strategies = {s.name: s.build() for s in config.sleeves}

        result = run_day(
            broker, strategies, prices, config, nav_history, dry_run=dry_run
        )

        if result.halted:
            LOG.error("HALTED: %s", result.reason)
            return 1

        LOG.info("NAV %.2f on %s", result.nav, result.asof)
        for order in result.orders:
            LOG.info("  %s %s %+.0f", "DRY" if dry_run else "SEND", order.symbol, order.quantity)
        if not result.orders:
            LOG.info("  no rebalance required (inside no-trade band)")

        book = ShadowBook.load(SHADOW_PATH)
        for name, weights in result.sleeve_weights.items():
            if config.allocations.get(name, 0.0) == 0.0:
                book.mark(name, result.asof, weights, prices)
        book.save()

        card = score(nav_history, config.risk_free_annual_cmt_percent)
        LOG.info("scorecard\n%s", card)
        for sleeve in config.sleeves:
            if sleeve.allocation == 0.0:
                shadow_card = book.scorecard(
                    sleeve.name, config.risk_free_annual_cmt_percent
                )
                if shadow_card:
                    LOG.info(
                        "  shadow %-16s sharpe %+.4f over %d obs",
                        sleeve.name,
                        shadow_card.sharpe,
                        shadow_card.n_observations,
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
