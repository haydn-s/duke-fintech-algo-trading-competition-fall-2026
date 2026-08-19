"""The Broker contract.

Two implementations satisfy this: SimBroker replays history, IBKRBroker talks
to a running IB Gateway. The daily run script is byte-identical against both.
Flipping one config flag is the entire difference between a backtest and a
live paper-trading session, which means the code path you validate is the
code path you deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    avg_cost: float


@dataclass(frozen=True)
class Order:
    symbol: str
    quantity: float  # signed: positive buys, negative sells

    @property
    def side(self) -> str:
        return "BUY" if self.quantity > 0 else "SELL"


class Broker(Protocol):
    def today(self) -> date:
        """The date being traded. Sim returns the replay cursor."""
        ...

    def net_asset_value(self) -> float:
        """Total account value: positions marked to market, plus cash."""
        ...

    def positions(self) -> dict[str, Position]: ...

    def last_price(self, symbol: str) -> float: ...

    def place_order(self, order: Order) -> None: ...
