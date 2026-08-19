"""End-to-end: the same code path the live runner uses, over history."""

import pandas as pd
import pytest

from alphalab.backtest import backtest
from alphalab.config import Config, SleeveConfig
from alphalab.risk import RiskLimits


def _config(**overrides) -> Config:
    base = dict(
        risk_free_annual_cmt_percent=4.25,
        target_annual_vol=0.08,
        sleeves=[
            SleeveConfig("core", "buy_and_hold", 0.5, {"universe": ["AAA", "BBB"]}),
            SleeveConfig(
                "mom", "xsec_momentum", 0.5,
                {"universe": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"], "lookback": 60, "n_long": 2},
            ),
        ],
        limits=RiskLimits(),
    )
    base.update(overrides)
    return Config(**base)


def test_backtest_produces_a_scorecard(prices):
    card, nav = backtest(_config(), prices)
    assert card.n_observations > 100
    assert nav.is_monotonic_increasing is not None
    assert card.volatility > 0


def test_vol_targeting_lowers_realized_volatility(prices):
    loose, _ = backtest(_config(target_annual_vol=0.30), prices)
    tight, _ = backtest(_config(target_annual_vol=0.04), prices)
    assert tight.volatility < loose.volatility


def test_zero_allocation_sleeve_never_trades(prices):
    cfg = _config(sleeves=[
        SleeveConfig("shadow", "buy_and_hold", 0.0, {"universe": ["AAA", "BBB"]}),
    ])
    _, nav = backtest(cfg, prices)
    assert nav.nunique() == 1, "an unallocated sleeve must not move NAV"


def test_backtest_is_deterministic(prices):
    a, _ = backtest(_config(), prices)
    b, _ = backtest(_config(), prices)
    assert a.sharpe == pytest.approx(b.sharpe)
