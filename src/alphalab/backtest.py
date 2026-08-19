"""Replay a config over historical prices and score it exactly as the judges will."""

from __future__ import annotations

import pandas as pd

from .brokers.sim import SimBroker
from .config import Config
from .engine import run_day
from .score import Scorecard, score


def backtest(
    config: Config,
    prices: pd.DataFrame,
    starting_cash: float = 1_000_000.0,
    warmup_days: int = 0,
) -> tuple[Scorecard, pd.Series]:
    """Run the live code path against history.

    Returns the scorecard and the NAV series. The scorecard comes from
    ``score.py`` -- the same function the competition uses -- so a backtest
    result and a leaderboard position are directly comparable numbers.
    """
    strategies = {s.name: s.build() for s in config.sleeves}
    warmup = warmup_days or max(
        (s.lookback_days for s in strategies.values()), default=1
    )

    broker = SimBroker(prices, starting_cash=starting_cash)
    for _ in range(min(warmup, len(prices) - 1)):
        broker.advance()

    while True:
        nav_history = broker.nav_series()
        run_day(broker, strategies, prices, config, nav_history, dry_run=False)
        if not broker.advance():
            break

    nav = broker.nav_series()
    nav.index = pd.to_datetime(nav.index)
    return score(nav, config.risk_free_annual_cmt_percent), nav
