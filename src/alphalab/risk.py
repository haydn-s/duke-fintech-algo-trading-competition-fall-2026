"""Pre-trade guardrails.

Every order passes through here before it reaches a broker. The checks are
intentionally blunt and intentionally few: a limit you understand and never
breach is worth more than a sophisticated one you disable the first time it
gets in your way.

The drawdown kill switch is the one that matters most. A blown-up account
does not just lose the return you gave back -- the volatility of the blow-up
is baked into sigma_p for the rest of the competition.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .strategies.base import Weights


class RiskViolation(Exception):
    """Raised when a proposed portfolio breaches a hard limit."""


@dataclass(frozen=True)
class RiskLimits:
    max_gross_exposure: float = 1.5  # sum of |weight|
    max_net_exposure: float = 1.0  # sum of weight
    max_position_weight: float = 0.25
    max_drawdown: float = 0.15  # peak-to-trough NAV, halts trading
    min_nav: float = 0.0


def clamp_positions(weights: Weights, limits: RiskLimits) -> Weights:
    """Cap individual position sizes, then scale gross exposure into range."""
    capped = {
        s: max(-limits.max_position_weight, min(limits.max_position_weight, w))
        for s, w in weights.items()
    }
    gross = sum(abs(w) for w in capped.values())
    if gross > limits.max_gross_exposure and gross > 0:
        scale = limits.max_gross_exposure / gross
        capped = {s: w * scale for s, w in capped.items()}
    return capped


def current_drawdown(nav_history: pd.Series) -> float:
    """Peak-to-current drawdown as a positive fraction."""
    if len(nav_history) < 2:
        return 0.0
    peak = nav_history.cummax().iloc[-1]
    return float(max(0.0, 1.0 - nav_history.iloc[-1] / peak))


def check(weights: Weights, nav_history: pd.Series, limits: RiskLimits) -> Weights:
    """Validate and adjust a proposed portfolio. Raises on hard breaches."""
    if not nav_history.empty and nav_history.iloc[-1] < limits.min_nav:
        raise RiskViolation(f"NAV {nav_history.iloc[-1]:.2f} below floor")

    dd = current_drawdown(nav_history)
    if dd > limits.max_drawdown:
        raise RiskViolation(
            f"drawdown {dd:.2%} exceeds limit {limits.max_drawdown:.2%} -- "
            "trading halted, flatten manually and review before resuming"
        )

    adjusted = clamp_positions(weights, limits)
    net = sum(adjusted.values())
    if abs(net) > limits.max_net_exposure:
        scale = limits.max_net_exposure / abs(net)
        adjusted = {s: w * scale for s, w in adjusted.items()}
    return adjusted
