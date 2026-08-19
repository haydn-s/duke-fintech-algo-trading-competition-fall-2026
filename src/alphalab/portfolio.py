"""Allocation and volatility targeting.

This module exists because of one property of the competition's scoring:
sigma_p is computed over the *whole* competition, not a rolling window. A
single violent week in September permanently inflates the denominator of the
December Sharpe. There is no recovering from it -- you cannot un-observe a
return. Volatility control is therefore not a refinement, it is the load-
bearing piece.

The second property that matters: scaling every position by k scales both the
numerator and the denominator of the Sharpe ratio, so leverage is very nearly
Sharpe-neutral. What is *not* neutral is correlation. Combining sleeves whose
returns move independently raises Sharpe without touching either sleeve's own
performance. Hence inverse-volatility allocation across sleeves as the default.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .strategies.base import Weights


def combine(sleeve_weights: dict[str, Weights], allocations: dict[str, float]) -> Weights:
    """Merge per-sleeve weights into one portfolio using capital allocations.

    Args:
        sleeve_weights: sleeve name -> that sleeve's internal weights.
        allocations: sleeve name -> fraction of account capital. Sleeves
            allocated 0.0 contribute nothing here but are still tracked by the
            shadow book, which is how a new idea earns its way to real money.
    """
    combined: Weights = {}
    for sleeve, weights in sleeve_weights.items():
        share = allocations.get(sleeve, 0.0)
        if share == 0.0:
            continue
        for symbol, w in weights.items():
            combined[symbol] = combined.get(symbol, 0.0) + w * share
    return {s: w for s, w in combined.items() if abs(w) > 1e-9}


def inverse_vol_allocations(
    sleeve_returns: pd.DataFrame, floor: float = 1e-6
) -> dict[str, float]:
    """Allocate across sleeves inversely to their realized volatility.

    Equalizes each sleeve's risk contribution rather than its dollar
    contribution, so a quiet sleeve is not drowned out by a loud one.
    """
    vols = sleeve_returns.std(ddof=1).clip(lower=floor)
    inv = 1.0 / vols
    normalized = inv / inv.sum()
    return {str(k): float(v) for k, v in normalized.items()}


def realized_vol(returns: pd.Series, window: int = 60, annualize: bool = True) -> float:
    """Trailing realized volatility of a return series."""
    r = returns.dropna().tail(window)
    if len(r) < 2:
        return float("nan")
    vol = float(r.std(ddof=1))
    return vol * np.sqrt(252) if annualize else vol


def vol_scaled(
    weights: Weights,
    portfolio_returns: pd.Series,
    target_annual_vol: float = 0.08,
    max_leverage: float = 1.5,
    min_leverage: float = 0.0,
    window: int = 60,
) -> Weights:
    """Scale weights so trailing realized vol lands near the target.

    Returns the weights unchanged when there is not yet enough history to
    estimate volatility -- the sensible failure mode early in the competition,
    when the risk layer has the least information and the most leverage over
    the final score.
    """
    current = realized_vol(portfolio_returns, window=window, annualize=True)
    if not np.isfinite(current) or current <= 0:
        return dict(weights)
    k = float(np.clip(target_annual_vol / current, min_leverage, max_leverage))
    return {s: w * k for s, w in weights.items()}
