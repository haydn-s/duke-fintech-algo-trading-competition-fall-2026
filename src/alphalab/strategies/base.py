"""The Strategy contract.

A strategy is a pure function of market data and a date, returning desired
portfolio weights. It does not know its capital, does not talk to a broker,
does not place orders, and holds no mutable state between calls.

That constraint is the whole design. Because a strategy is
``(prices, asof) -> weights``:

  * it is trivially unit-testable with a hand-built DataFrame,
  * it behaves identically in backtest and in live trading,
  * sizing, leverage, and risk limits live in exactly one place instead of
    being reimplemented (and mis-implemented) inside every idea,
  * adding a new idea means adding one file and one config entry.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd

Weights = dict[str, float]
"""Symbol -> fraction of this sleeve's capital. Negative means short.

Weights are *gross* intent, before any risk scaling. ``sum(abs(w))`` may
exceed 1.0; the risk layer decides whether that survives.
"""


@runtime_checkable
class Strategy(Protocol):
    """A single trading idea."""

    name: str

    @property
    def universe(self) -> list[str]:
        """Symbols this strategy needs price history for."""
        ...

    @property
    def lookback_days(self) -> int:
        """Trading days of history required before the first valid signal."""
        ...

    def target_weights(self, prices: pd.DataFrame, asof: date) -> Weights:
        """Desired weights as of the close on ``asof``.

        Args:
            prices: Adjusted closes, dates on the index, symbols on the
                columns. Guaranteed to contain no rows after ``asof``, so a
                strategy physically cannot see the future.
            asof: The date being traded on.

        Returns:
            Symbol -> weight. Omitted symbols are treated as zero. An empty
            dict means "hold nothing" and is a legitimate answer.
        """
        ...
