"""Verify the IBKR setup without placing anything. Read-only, safe to rerun.

    python -m alphalab.preflight

Run this after creating the paper account and writing .env, and again any
morning the gateway looks unhappy. It answers the four questions that account
for essentially every failed first live run, in the order they fail:

1. Is .env present and does it name a paper account?
2. Is a gateway actually listening on the configured port?
3. Does that gateway serve the account id in .env? (A typo here otherwise
   surfaces as a mysteriously empty portfolio rather than an error.)
4. Does market data come back for the configured universe?

The connection is opened read-only, so this cannot place an order even if
something is misconfigured.
"""

from __future__ import annotations

import argparse
import logging

from .config import Config
from .credentials import Credentials, CredentialsError

LOG = logging.getLogger("alphalab")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the IBKR paper setup.")
    parser.add_argument("--config", default="configs/live.yaml")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    config = Config.load(args.config)

    try:
        credentials = Credentials.load()
    except CredentialsError as exc:
        LOG.error("%s", exc)
        return 1
    LOG.info("credentials  %s", credentials)
    if not credentials.can_automate_login:
        LOG.info("             (no stored login -- start the gateway by hand)")

    from .brokers.ibkr import IBKRBroker

    broker = IBKRBroker(
        host=config.ibkr_host,
        port=config.ibkr_port,
        client_id=config.ibkr_client_id,
        account=credentials.account,
        read_only=True,
    )

    try:
        broker.connect()
    except ImportError:
        # ib_async is in the optional 'live' extra, so a dev install lands here.
        LOG.error(
            "ib_async is not installed. Run: pip install -e \".[dev,live]\""
        )
        return 1
    except (OSError, TimeoutError) as exc:
        LOG.error(
            "no gateway on %s:%d (%s). Start IB Gateway, log into the PAPER "
            "session, and enable API access. See docs/IBKR_SETUP.md.",
            config.ibkr_host,
            config.ibkr_port,
            exc,
        )
        return 1

    try:
        served = list(broker.ib.managedAccounts())
        LOG.info("gateway      %s:%d serves %s", config.ibkr_host, config.ibkr_port, served)
        if credentials.account not in served:
            LOG.error(
                "IBKR_ACCOUNT=%s is not served by this gateway. Either it is a "
                "typo or the gateway is logged into a different session.",
                credentials.account,
            )
            return 1

        LOG.info("NAV          %.2f", broker.net_asset_value())
        positions = broker.positions()
        LOG.info("positions    %d open", len(positions))
        for symbol, position in sorted(positions.items()):
            LOG.info("             %-6s %+.0f", symbol, position.quantity)

        symbol = config.universe[0]
        try:
            LOG.info("market data  %s last %.2f", symbol, broker.last_price(symbol))
        except RuntimeError:
            # Not cosmetic: rebalance.orders_from_weights prices every symbol,
            # so a run without quotes dies partway through instead of trading.
            LOG.error(
                "no quote for %s. Every rebalance prices each symbol, so the "
                "daily run cannot proceed. A standalone paper account carries no "
                "market data subscription -- either subscribe under Client Portal "
                "-> Settings -> Market Data Subscriptions, or switch the session "
                "to delayed data. See docs/IBKR_SETUP.md.",
                symbol,
            )
            return 1
    except Exception as exc:  # the point is to report the failure, not to raise it
        LOG.error("connected, but a check failed: %s", exc)
        return 1
    finally:
        broker.disconnect()

    LOG.info("all checks passed -- dry_run is %s in %s", config.dry_run, args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
