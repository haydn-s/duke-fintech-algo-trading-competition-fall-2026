"""The shadow book: paper trading inside a paper-trading account.

Every sleeve in the config computes target weights daily, including sleeves
allocated zero capital. Zero-allocation sleeves are marked against real
subsequent prices into their own simulated NAV series.

The point is the promotion decision. After six weeks of the competition, a
shadow sleeve has genuine out-of-sample evidence behind it -- forty days of
signals generated before the prices that scored them existed. Promoting on
that basis is a defensible decision. Promoting on a backtest is a guess
dressed up in a chart.

Cost: about forty lines, and no capital at risk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from .score import Scorecard, score
from .strategies.base import Weights


@dataclass
class ShadowBook:
    """Tracks simulated NAV for sleeves that hold no real capital."""

    path: Path
    starting_nav: float = 1_000_000.0
    weights_by_date: dict[str, dict[str, Weights]] = field(default_factory=dict)
    nav_by_sleeve: dict[str, dict[str, float]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path, starting_nav: float = 1_000_000.0) -> "ShadowBook":
        if not path.exists():
            return cls(path=path, starting_nav=starting_nav)
        raw = json.loads(path.read_text())
        return cls(
            path=path,
            starting_nav=raw.get("starting_nav", starting_nav),
            weights_by_date=raw.get("weights_by_date", {}),
            nav_by_sleeve=raw.get("nav_by_sleeve", {}),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "starting_nav": self.starting_nav,
                    "weights_by_date": self.weights_by_date,
                    "nav_by_sleeve": self.nav_by_sleeve,
                },
                indent=2,
                sort_keys=True,
            )
        )

    def mark(self, sleeve: str, asof: date, weights: Weights, prices: pd.DataFrame) -> None:
        """Mark yesterday's weights against today's prices, then record today's."""
        key = asof.isoformat()
        history = self.nav_by_sleeve.setdefault(sleeve, {})
        prior_weights = self.weights_by_date.setdefault(sleeve, {})

        if history:
            last_date = max(history)
            last_nav = history[last_date]
            held = prior_weights.get(last_date, {})
            try:
                px_then = prices.loc[pd.Timestamp(last_date)]
                px_now = prices.loc[pd.Timestamp(asof)]
            except KeyError:
                return
            ret = sum(
                w * float(px_now[s] / px_then[s] - 1.0)
                for s, w in held.items()
                if s in px_now.index and s in px_then.index
            )
            history[key] = last_nav * (1.0 + ret)
        else:
            history[key] = self.starting_nav

        prior_weights[key] = dict(weights)

    def scorecard(self, sleeve: str, annual_cmt_percent: float) -> Scorecard | None:
        history = self.nav_by_sleeve.get(sleeve, {})
        if len(history) < 3:
            return None
        nav = pd.Series(
            {pd.Timestamp(k): v for k, v in history.items()}
        ).sort_index()
        return score(nav, annual_cmt_percent)
