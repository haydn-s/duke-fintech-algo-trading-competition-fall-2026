"""Equal-weight buy and hold.

The benchmark sleeve. Every idea in the repository has to justify itself
against this, and it doubles as a smoke test for the whole pipeline: if the
daily run cannot hold a static basket correctly, nothing else is trustworthy.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .base import Weights


class BuyAndHold:
    def __init__(
        self, universe: list[str], gross: float = 1.0, name: str = "buy_and_hold"
    ) -> None:
        self.name = name
        self._universe = list(universe)
        self.gross = gross

    @property
    def universe(self) -> list[str]:
        return self._universe

    @property
    def lookback_days(self) -> int:
        return 1

    def target_weights(self, prices: pd.DataFrame, asof: date) -> Weights:
        available = [s for s in self._universe if s in prices.columns]
        if not available:
            return {}
        w = self.gross / len(available)
        return {s: w for s in available}
