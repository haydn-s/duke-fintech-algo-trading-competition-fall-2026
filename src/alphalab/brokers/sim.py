"""Backtest broker: replays a price history with a simple cost model.

Deliberately simple. It models the two frictions that actually matter at
daily rebalance frequency on liquid names -- commission and a fixed slippage
haircut -- and nothing else. A more elaborate fill model would add precision
we have no way to validate and would invite over-fitting to its own quirks.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .base import Order, Position


class SimBroker:
    def __init__(
        self,
        prices: pd.DataFrame,
        starting_cash: float = 1_000_000.0,
        commission_per_share: float = 0.005,
        slippage_bps: float = 2.0,
    ) -> None:
        self.prices = prices.sort_index()
        self.cash = starting_cash
        self.commission_per_share = commission_per_share
        self.slippage_bps = slippage_bps
        self._positions: dict[str, Position] = {}
        self._cursor = 0
        self.nav_history: dict[date, float] = {}

    def today(self) -> date:
        return self.prices.index[self._cursor].date()

    def advance(self) -> bool:
        """Record NAV, then step forward. Returns False at the end of history."""
        self.nav_history[self.today()] = self.net_asset_value()
        if self._cursor >= len(self.prices) - 1:
            return False
        self._cursor += 1
        return True

    def last_price(self, symbol: str) -> float:
        return float(self.prices.iloc[self._cursor][symbol])

    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    def net_asset_value(self) -> float:
        marked = sum(
            p.quantity * self.last_price(sym) for sym, p in self._positions.items()
        )
        return self.cash + marked

    def place_order(self, order: Order) -> None:
        if order.quantity == 0:
            return
        mid = self.last_price(order.symbol)
        direction = 1.0 if order.quantity > 0 else -1.0
        fill = mid * (1.0 + direction * self.slippage_bps / 10_000.0)
        commission = abs(order.quantity) * self.commission_per_share

        self.cash -= order.quantity * fill + commission
        existing = self._positions.get(order.symbol)
        prior_qty = existing.quantity if existing else 0.0
        new_qty = prior_qty + order.quantity

        if abs(new_qty) < 1e-9:
            self._positions.pop(order.symbol, None)
            return
        if existing and prior_qty * order.quantity > 0:
            avg = (prior_qty * existing.avg_cost + order.quantity * fill) / new_qty
        else:
            avg = fill
        self._positions[order.symbol] = Position(order.symbol, new_qty, avg)

    def nav_series(self) -> pd.Series:
        return pd.Series(self.nav_history).sort_index()
