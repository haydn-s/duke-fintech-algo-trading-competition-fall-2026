"""The one function that runs a trading day.

Shared by the live run and the backtest. That sharing is the point: there is
no separate "backtest engine" that could drift from the live path and quietly
invalidate every result you have.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from . import portfolio, rebalance, risk
from .brokers.base import Broker, Order
from .config import Config
from .strategies.base import Strategy, Weights


@dataclass
class DayResult:
    asof: date
    nav: float
    sleeve_weights: dict[str, Weights]
    final_weights: Weights
    orders: list[Order]
    halted: bool = False
    reason: str = ""


def run_day(
    broker: Broker,
    strategies: dict[str, Strategy],
    prices: pd.DataFrame,
    config: Config,
    nav_history: pd.Series,
    dry_run: bool = False,
) -> DayResult:
    """Compute targets, apply risk, and rebalance. One trading day."""
    asof = broker.today()
    nav = broker.net_asset_value()
    visible = prices.loc[: pd.Timestamp(asof)]

    sleeve_weights = {
        name: strategy.target_weights(visible, asof)
        for name, strategy in strategies.items()
    }

    combined = portfolio.combine(sleeve_weights, config.allocations)

    returns = (
        pd.Series(dtype="float64")
        if len(nav_history) < 2
        else (nav_history / nav_history.shift(1) - 1.0).dropna()
    )
    scaled = portfolio.vol_scaled(
        combined, returns, target_annual_vol=config.target_annual_vol
    )

    try:
        final = risk.check(scaled, nav_history, config.limits)
    except risk.RiskViolation as exc:
        return DayResult(asof, nav, sleeve_weights, {}, [], halted=True, reason=str(exc))

    orders = rebalance.orders_from_weights(
        broker, final, no_trade_band=config.no_trade_band
    )
    if not dry_run:
        rebalance.execute(broker, orders)

    return DayResult(asof, nav, sleeve_weights, final, orders)
