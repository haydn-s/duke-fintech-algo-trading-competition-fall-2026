import pandas as pd
import pytest

from alphalab.strategies import BuyAndHold, CrossSectionalMomentum, Strategy


def test_both_satisfy_the_protocol():
    assert isinstance(BuyAndHold(["AAA"]), Strategy)
    assert isinstance(CrossSectionalMomentum(["AAA", "BBB"], n_long=1), Strategy)


def test_buy_and_hold_is_equal_weighted(prices):
    w = BuyAndHold(["AAA", "BBB", "CCC"]).target_weights(prices, prices.index[-1].date())
    assert w == pytest.approx({"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3})


def test_momentum_is_dollar_neutral(prices):
    strat = CrossSectionalMomentum(list(prices.columns), lookback=60, skip=5, n_long=2)
    w = strat.target_weights(prices, prices.index[-1].date())
    assert sum(w.values()) == pytest.approx(0.0, abs=1e-12)
    assert sum(abs(v) for v in w.values()) == pytest.approx(1.0)


def test_momentum_returns_nothing_before_lookback_is_satisfied(prices):
    strat = CrossSectionalMomentum(list(prices.columns), lookback=60, skip=5, n_long=2)
    assert strat.target_weights(prices.head(10), prices.index[9].date()) == {}


def test_strategy_cannot_see_the_future(prices):
    """The engine slices ``prices`` at asof, so a mid-history call must match
    the same call made when only that much history existed."""
    strat = CrossSectionalMomentum(list(prices.columns), lookback=60, skip=5, n_long=2)
    cutoff = prices.index[200]
    full = strat.target_weights(prices.loc[:cutoff], cutoff.date())
    truncated = strat.target_weights(prices.loc[:cutoff].copy(), cutoff.date())
    assert full == truncated


def test_momentum_ranks_winners_long(prices):
    """AAA has the strongest drift and EEE the weakest, by construction."""
    strat = CrossSectionalMomentum(list(prices.columns), lookback=200, skip=5, n_long=1)
    w = strat.target_weights(prices, prices.index[-1].date())
    assert max(w, key=lambda s: w[s]) == "AAA"
    assert min(w, key=lambda s: w[s]) == "EEE"
