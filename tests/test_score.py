"""The scoring tests are the tests that matter.

If any of these break, every backtest number in the repository is wrong and
every promotion decision made from one was made on a false premise.
"""

import numpy as np
import pandas as pd
import pytest

from alphalab.score import (
    daily_log_returns,
    daily_risk_free_rate,
    geometric_mean_return,
    score,
    volatility,
)


def test_matches_published_worked_example():
    """Pinned to the competition's own published figures.

    Their worked example reports, for a seven-day sample:
        GMRR      0.005848% / trading day
        rf        0.0001587% / trading day (from a 0.04% annual CMT rate)
        excess    0.005689% / trading day
        vol       0.0174% / trading day
        Sharpe    0.3270215

    Source figures are rounded on the page, so the tolerance here is loose on
    purpose -- the assertion is that our formulas agree with theirs, not that
    we can recover digits they never published.
    """
    gmrr = 0.005848 / 100
    vol = 0.0174 / 100
    rf = daily_risk_free_rate(0.04)

    assert rf == pytest.approx(0.0001587 / 100, rel=1e-3)
    assert gmrr - rf == pytest.approx(0.005689 / 100, rel=1e-3)
    assert (gmrr - rf) / vol == pytest.approx(0.3270215, rel=1e-3)


def test_single_day_log_return_matches_published_check():
    """Their published sanity check: 1,000,100 -> 1,000,050 on 18 Mar 2021.

    Worth noting what this test actually shows. The competition verifies its
    own return figure with ``V * (1 + r)``, which is the identity for a
    *simple* return -- but r here is a *log* return, for which the identity is
    ``V * exp(r)``. The two agree only to first order, so their check recovers
    1,000,050 to about nine significant figures rather than exactly.

    This is harmless at daily magnitudes and it is not a mistake worth
    raising with the organizers. It is recorded here because the same
    approximation reappears in their geometric-mean step, and score.py
    replicates it on purpose.
    """
    r = float(np.log(1_000_050.00 / 1_000_100.00))
    assert r == pytest.approx(-0.005 / 100, rel=1e-2)
    assert 1_000_100.00 * (1 + r) == pytest.approx(1_000_050.00, rel=1e-7)
    assert 1_000_100.00 * np.exp(r) == pytest.approx(1_000_050.00, rel=1e-12)


def test_n_minus_one_observations():
    """Day one has nothing to compare against and yields no return."""
    nav = pd.Series([100.0, 101.0, 102.0], index=pd.bdate_range("2024-01-01", periods=3))
    assert len(daily_log_returns(nav)) == 2
    assert score(nav, 4.0).n_observations == 2


def test_flat_nav_gives_zero_return_and_zero_vol():
    nav = pd.Series([100.0] * 10, index=pd.bdate_range("2024-01-01", periods=10))
    card = score(nav, 4.0)
    assert card.portfolio_return == pytest.approx(0.0)
    assert card.volatility == pytest.approx(0.0)
    assert np.isnan(card.sharpe)


def test_lower_volatility_wins_at_equal_return():
    """The whole premise of the competition, encoded as an assertion.

    Two accounts finish at the same NAV. The steadier path must score higher.
    """
    dates = pd.bdate_range("2024-01-01", periods=21)
    steady = pd.Series(100.0 * np.exp(np.linspace(0, 0.10, 21)), index=dates)

    jagged_returns = np.full(20, 0.10 / 20)
    jagged_returns[::2] += 0.05
    jagged_returns[1::2] -= 0.05
    jagged = pd.Series(100.0 * np.exp(np.concatenate([[0], np.cumsum(jagged_returns)])), index=dates)

    assert steady.iloc[-1] == pytest.approx(jagged.iloc[-1], rel=1e-6)
    assert score(steady, 4.0).sharpe > score(jagged, 4.0).sharpe


def test_geometric_mean_recovers_zero_for_offsetting_returns():
    """Their own illustration: +25, -25, +25, -25 characterizes as 0, not +2.5%."""
    r = pd.Series([0.25, -0.20, 0.25, -0.20])
    assert geometric_mean_return(r) == pytest.approx(0.0, abs=1e-9)


def test_volatility_uses_sample_stddev():
    """R's sd() is ddof=1. numpy's default is ddof=0. This is not cosmetic."""
    r = pd.Series([0.01, -0.01, 0.02, -0.02])
    assert volatility(r) == pytest.approx(float(r.std(ddof=1)))
    assert volatility(r) != pytest.approx(float(r.std(ddof=0)))


def test_rejects_non_positive_nav():
    nav = pd.Series([100.0, 0.0], index=pd.bdate_range("2024-01-01", periods=2))
    with pytest.raises(ValueError):
        daily_log_returns(nav)
