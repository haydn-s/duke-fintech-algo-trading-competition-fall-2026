import pytest

from alphalab.config import Config


CONFIG = """
risk_free_annual_cmt_percent: 4.25
target_annual_vol: 0.08
broker: sim
sleeves:
  - name: core
    strategy: buy_and_hold
    allocation: 0.6
    params:
      universe: [AAA, BBB]
  - name: shadow_mom
    strategy: xsec_momentum
    allocation: 0.0
    params:
      universe: [AAA, BBB, CCC, DDD]
      n_long: 1
risk_limits:
  max_gross_exposure: 1.2
"""


def test_loads_and_builds_strategies(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(CONFIG)
    cfg = Config.load(path)
    assert cfg.allocations == {"core": 0.6, "shadow_mom": 0.0}
    assert cfg.universe == ["AAA", "BBB", "CCC", "DDD"]
    assert cfg.limits.max_gross_exposure == 1.2
    assert cfg.sleeves[0].build().name == "core"


def test_rejects_over_allocation(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(CONFIG.replace("allocation: 0.6", "allocation: 1.6"))
    with pytest.raises(ValueError, match="above 1.0"):
        Config.load(path)


def test_unknown_strategy_names_are_caught_at_build(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(CONFIG.replace("buy_and_hold", "nonexistent"))
    with pytest.raises(KeyError, match="unknown strategy"):
        Config.load(path).sleeves[0].build()
