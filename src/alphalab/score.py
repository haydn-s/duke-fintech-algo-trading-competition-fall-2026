"""Replication of the Duke FinTech Trading Competition scoring math.

This is the most important module in the repository. The competition grades
risk-adjusted return, not return, so this is the objective function -- and it
is therefore also the metric used by every backtest, every nightly report, and
every decision to promote a shadow sleeve to live capital.

Method, per the competition's published rules:

  1. Daily portfolio return is the *log* return of end-of-day NAV:
         R_n = ln(V_n / V_{n-1})
     With N days of NAV you get N-1 observations.
  2. Portfolio return R_p is the geometric mean of those returns:
         R_p = (prod(1 + R_i)) ** (1/n) - 1
  3. Volatility sigma_p is the standard deviation of those returns.
  4. The risk-free rate is fixed for the entire competition at the 3-month
     CMT rate published on day one, converted to a per-trading-day figure by
     dividing by 252.
  5. Sharpe = (R_p - r_f) / sigma_p

Note the quirk in step 2: the geometric-mean formula is applied to returns
that are already logarithmic. Compounding log returns is unusual -- the
mathematically conventional choice would be an arithmetic mean of the logs.
We replicate the published method rather than the conventional one, because
the published method is what determines our rank. The difference is tiny at
daily magnitudes but it is not zero, and being scored on something you did
not optimize is an avoidable way to lose.

Reference:
https://fintechtradingcompetition.com/articles/excess_rtn_vol_and_sharpe.html
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def daily_log_returns(nav: pd.Series) -> pd.Series:
    """Daily log returns from a NAV series indexed by date.

    The first observation is dropped: there is nothing to compare day one to.
    """
    if len(nav) < 2:
        return pd.Series(dtype="float64")
    nav = nav.sort_index().astype("float64")
    if (nav <= 0).any():
        raise ValueError("NAV series contains non-positive values")
    return np.log(nav / nav.shift(1)).dropna()


def geometric_mean_return(returns: pd.Series) -> float:
    """Geometric mean rate of return, exactly as the competition computes it."""
    r = returns.dropna()
    if r.empty:
        return float("nan")
    return float(np.prod(1.0 + r.to_numpy()) ** (1.0 / len(r)) - 1.0)


def volatility(returns: pd.Series) -> float:
    """Standard deviation of daily returns.

    Uses the sample standard deviation (ddof=1) to match R's ``sd()``, which
    is what the competition's scoring script uses.
    """
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    return float(r.std(ddof=1))


def daily_risk_free_rate(annual_cmt_percent: float) -> float:
    """Convert the annualized 3-month CMT rate (in percent) to per-trading-day.

    e.g. a published rate of 4.25 becomes 0.0425 / 252.
    """
    return annual_cmt_percent / 100.0 / TRADING_DAYS_PER_YEAR


@dataclass(frozen=True)
class Scorecard:
    """Everything the competition's leaderboard is built from."""

    n_observations: int
    portfolio_return: float  # R_p, per trading day
    risk_free_rate: float  # r_f, per trading day
    excess_return: float  # R_p - r_f
    volatility: float  # sigma_p, per trading day
    sharpe: float
    total_return: float  # cumulative, for context only -- not scored directly

    def __str__(self) -> str:
        def pct(x: float) -> str:
            return f"{x * 100:.6f}%"

        return (
            f"observations   {self.n_observations}\n"
            f"return  (R_p)  {pct(self.portfolio_return)} / trading day\n"
            f"risk-free (rf) {pct(self.risk_free_rate)} / trading day\n"
            f"excess return  {pct(self.excess_return)} / trading day\n"
            f"volatility     {pct(self.volatility)} / trading day\n"
            f"SHARPE         {self.sharpe:.6f}\n"
            f"total return   {pct(self.total_return)} (context only)"
        )


def score(nav: pd.Series, annual_cmt_percent: float) -> Scorecard:
    """Score a NAV series the way the competition will score it.

    Args:
        nav: End-of-day net asset value, indexed by date.
        annual_cmt_percent: The 3-month CMT rate fixed on competition day one,
            expressed in percent (e.g. ``4.25``).
    """
    returns = daily_log_returns(nav)
    r_p = geometric_mean_return(returns)
    r_f = daily_risk_free_rate(annual_cmt_percent)
    sigma = volatility(returns)
    nav_sorted = nav.sort_index()

    return Scorecard(
        n_observations=len(returns),
        portfolio_return=r_p,
        risk_free_rate=r_f,
        excess_return=r_p - r_f,
        volatility=sigma,
        sharpe=(r_p - r_f) / sigma if sigma else float("nan"),
        total_return=float(nav_sorted.iloc[-1] / nav_sorted.iloc[0] - 1.0)
        if len(nav_sorted) >= 2
        else 0.0,
    )
