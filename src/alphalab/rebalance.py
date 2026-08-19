"""Turn target weights into orders.

The only place in the codebase that knows what a share is. Strategies speak
in weights; this module diffs those weights against what the account actually
holds and emits the difference.

The no-trade band is the quiet workhorse here: without it, a strategy whose
weights drift by a fraction of a percent generates churn every single day,
and commission plus slippage grind down the numerator of the Sharpe for no
change in exposure.
"""

from __future__ import annotations

from .brokers.base import Broker, Order
from .strategies.base import Weights


def orders_from_weights(
    broker: Broker,
    target_weights: Weights,
    no_trade_band: float = 0.005,
    whole_shares: bool = True,
) -> list[Order]:
    """Diff desired weights against current positions.

    Args:
        no_trade_band: Skip any rebalance smaller than this fraction of NAV.
    """
    nav = broker.net_asset_value()
    positions = broker.positions()
    symbols = set(target_weights) | set(positions)

    orders: list[Order] = []
    for symbol in sorted(symbols):
        price = broker.last_price(symbol)
        if price <= 0:
            continue
        target_value = target_weights.get(symbol, 0.0) * nav
        held = positions.get(symbol)
        current_value = (held.quantity if held else 0.0) * price

        drift = abs(target_value - current_value) / nav if nav else 0.0
        if drift < no_trade_band:
            continue

        delta_shares = (target_value - current_value) / price
        if whole_shares:
            delta_shares = float(int(delta_shares))
        if abs(delta_shares) < 1:
            continue
        orders.append(Order(symbol, delta_shares))
    return orders


def execute(broker: Broker, orders: list[Order]) -> None:
    for order in orders:
        broker.place_order(order)
