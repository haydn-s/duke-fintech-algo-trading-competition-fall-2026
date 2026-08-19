import numpy as np
import pandas as pd
import pytest

from alphalab import portfolio, risk


def test_combine_respects_allocations():
    combined = portfolio.combine(
        {"a": {"AAA": 1.0}, "b": {"AAA": -1.0, "BBB": 1.0}},
        {"a": 0.6, "b": 0.4},
    )
    assert combined["AAA"] == pytest.approx(0.2)
    assert combined["BBB"] == pytest.approx(0.4)


def test_zero_allocation_sleeves_contribute_nothing():
    combined = portfolio.combine({"shadow": {"AAA": 1.0}}, {"shadow": 0.0})
    assert combined == {}


def test_vol_scaling_reduces_exposure_when_too_volatile():
    loud = pd.Series(np.random.default_rng(0).normal(0, 0.03, 120))
    scaled = portfolio.vol_scaled({"AAA": 1.0}, loud, target_annual_vol=0.08)
    assert scaled["AAA"] < 1.0


def test_vol_scaling_is_a_noop_without_enough_history():
    assert portfolio.vol_scaled({"AAA": 1.0}, pd.Series(dtype=float)) == {"AAA": 1.0}


def test_vol_scaling_respects_max_leverage():
    quiet = pd.Series(np.full(120, 0.00001))
    scaled = portfolio.vol_scaled(
        {"AAA": 1.0}, quiet, target_annual_vol=0.08, max_leverage=1.5
    )
    assert scaled["AAA"] == pytest.approx(1.5)


def test_inverse_vol_favors_the_quieter_sleeve():
    df = pd.DataFrame({
        "quiet": np.random.default_rng(1).normal(0, 0.002, 200),
        "loud": np.random.default_rng(2).normal(0, 0.02, 200),
    })
    alloc = portfolio.inverse_vol_allocations(df)
    assert alloc["quiet"] > alloc["loud"]
    assert sum(alloc.values()) == pytest.approx(1.0)


def test_position_cap_is_enforced():
    limits = risk.RiskLimits(max_position_weight=0.25, max_gross_exposure=10.0)
    capped = risk.clamp_positions({"AAA": 0.9, "BBB": -0.9}, limits)
    assert capped == pytest.approx({"AAA": 0.25, "BBB": -0.25})


def test_gross_exposure_is_scaled_into_range():
    limits = risk.RiskLimits(max_gross_exposure=1.0, max_position_weight=1.0)
    capped = risk.clamp_positions({"AAA": 1.0, "BBB": 1.0}, limits)
    assert sum(abs(v) for v in capped.values()) == pytest.approx(1.0)


def test_drawdown_kill_switch_halts_trading():
    nav = pd.Series([100.0, 90.0, 80.0], index=pd.bdate_range("2024-01-01", periods=3))
    with pytest.raises(risk.RiskViolation, match="drawdown"):
        risk.check({"AAA": 0.1}, nav, risk.RiskLimits(max_drawdown=0.15))


def test_drawdown_is_measured_from_the_peak():
    nav = pd.Series([100.0, 120.0, 108.0], index=pd.bdate_range("2024-01-01", periods=3))
    assert risk.current_drawdown(nav) == pytest.approx(0.10)
