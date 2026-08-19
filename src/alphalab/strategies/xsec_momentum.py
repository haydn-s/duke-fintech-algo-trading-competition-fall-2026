"""Cross-sectional momentum: long recent winners, short recent losers.

Included as a worked reference implementation of the Strategy protocol, not
as a claim that it makes money. It is here because it exercises every part of
the contract: a multi-symbol universe, a lookback requirement, dollar-neutral
weights, and a skip period.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .base import Weights


class CrossSectionalMomentum:
    """Rank the universe by trailing return, go long the top and short the bottom.

    Args:
        universe: Symbols to rank against each other.
        lookback: Trading days of return used to form the ranking.
        skip: Most recent days excluded from the lookback. Standard practice
            in the momentum literature -- the last week or so tends to mean
            revert, which pollutes the signal.
        n_long: How many names to hold long. The same count is held short.
    """

    def __init__(
        self,
        universe: list[str],
        lookback: int = 126,
        skip: int = 5,
        n_long: int = 3,
        name: str = "xsec_momentum",
    ) -> None:
        if n_long * 2 > len(universe):
            raise ValueError("universe too small for the requested leg size")
        self.name = name
        self._universe = list(universe)
        self.lookback = lookback
        self.skip = skip
        self.n_long = n_long

    @property
    def universe(self) -> list[str]:
        return self._universe

    @property
    def lookback_days(self) -> int:
        return self.lookback + self.skip + 1

    def target_weights(self, prices: pd.DataFrame, asof: date) -> Weights:
        cols = [s for s in self._universe if s in prices.columns]
        window = prices.loc[: pd.Timestamp(asof), cols]
        if len(window) < self.lookback_days:
            return {}

        end = window.iloc[-(self.skip + 1)]
        start = window.iloc[-(self.skip + self.lookback + 1)]
        trailing = (end / start - 1.0).dropna()
        if len(trailing) < self.n_long * 2:
            return {}

        ranked = trailing.sort_values(ascending=False)
        longs = ranked.index[: self.n_long]
        shorts = ranked.index[-self.n_long :]

        leg = 0.5 / self.n_long
        weights: Weights = {s: leg for s in longs}
        weights.update({s: -leg for s in shorts})
        return weights
