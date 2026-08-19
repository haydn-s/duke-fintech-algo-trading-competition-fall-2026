import pandas as pd
import pytest

from alphalab import rebalance
from alphalab.brokers import Order, SimBroker


@pytest.fixture
def broker(prices):
    b = SimBroker(prices, starting_cash=1_000_000.0, commission_per_share=0.0, slippage_bps=0.0)
    b.advance()
    return b


def test_nav_is_conserved_by_a_frictionless_trade(broker):
    before = broker.net_asset_value()
    broker.place_order(Order("AAA", 100))
    assert broker.net_asset_value() == pytest.approx(before, rel=1e-9)


def test_costs_reduce_nav(prices):
    b = SimBroker(prices, commission_per_share=0.01, slippage_bps=5.0)
    b.advance()
    before = b.net_asset_value()
    b.place_order(Order("AAA", 100))
    assert b.net_asset_value() < before


def test_orders_move_toward_target_weights(broker):
    orders = rebalance.orders_from_weights(broker, {"AAA": 0.5})
    rebalance.execute(broker, orders)
    nav = broker.net_asset_value()
    held = broker.positions()["AAA"].quantity * broker.last_price("AAA")
    assert held / nav == pytest.approx(0.5, abs=0.01)


def test_no_trade_band_suppresses_churn(broker):
    rebalance.execute(broker, rebalance.orders_from_weights(broker, {"AAA": 0.5}))
    again = rebalance.orders_from_weights(broker, {"AAA": 0.5005}, no_trade_band=0.005)
    assert again == []


def test_closing_a_position_removes_it(broker):
    broker.place_order(Order("AAA", 100))
    broker.place_order(Order("AAA", -100))
    assert "AAA" not in broker.positions()


def test_shorting_is_supported(broker):
    rebalance.execute(broker, rebalance.orders_from_weights(broker, {"AAA": -0.3}))
    assert broker.positions()["AAA"].quantity < 0
