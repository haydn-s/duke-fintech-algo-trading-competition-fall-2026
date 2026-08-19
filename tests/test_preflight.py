from typing import ClassVar

import pytest

from alphalab import preflight

CONFIG = """
risk_free_annual_cmt_percent: 4.25
broker: ibkr
dry_run: true
ibkr:
  host: 127.0.0.1
  port: 4002
  client_id: 17
sleeves:
  - name: core
    strategy: buy_and_hold
    allocation: 1.0
    params:
      universe: [AAA, BBB]
"""


class FakeIB:
    def __init__(self, served):
        self._served = served

    def managedAccounts(self):
        return self._served


class FakeBroker:
    """Stands in for IBKRBroker. Records what preflight asked it to do."""

    served: ClassVar[list[str]] = ["DU1234567"]
    prices: ClassVar[dict[str, float]] = {"AAA": 101.5, "BBB": 22.0}
    instances: ClassVar[list["FakeBroker"]] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connected = False
        self.disconnected = False
        self.ib = FakeIB(self.served)
        FakeBroker.instances.append(self)

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.disconnected = True

    def net_asset_value(self):
        return 1_000_000.0

    def positions(self):
        return {}

    def last_price(self, symbol):
        if symbol not in self.prices:
            raise RuntimeError(f"no usable price for {symbol}")
        return self.prices[symbol]


@pytest.fixture
def run_preflight(tmp_path, monkeypatch):
    """Run preflight against a fake broker in an isolated working directory."""
    config_path = tmp_path / "live.yaml"
    config_path.write_text(CONFIG)
    monkeypatch.chdir(tmp_path)  # no stray .env from the repo root
    monkeypatch.setattr("alphalab.brokers.ibkr.IBKRBroker", FakeBroker)
    monkeypatch.setattr("sys.argv", ["preflight", "--config", str(config_path)])

    def go(account="DU1234567"):
        FakeBroker.instances.clear()
        monkeypatch.setenv("IBKR_ACCOUNT", account)
        return preflight.main()

    return go


def test_healthy_setup_passes(run_preflight):
    assert run_preflight() == 0


def test_connects_read_only_with_the_configured_account(run_preflight):
    """Preflight must never be able to trade, whatever else is misconfigured."""
    run_preflight()
    kwargs = FakeBroker.instances[0].kwargs
    assert kwargs["read_only"] is True
    assert kwargs["account"] == "DU1234567"
    assert (kwargs["host"], kwargs["port"], kwargs["client_id"]) == (
        "127.0.0.1",
        4002,
        17,
    )


def test_account_not_served_by_the_gateway_fails(run_preflight, caplog):
    """A typo'd id otherwise surfaces as an empty portfolio, not an error."""
    assert run_preflight(account="DU7654321") == 1
    assert "not served by this gateway" in caplog.text


def test_live_account_fails_before_any_connection(run_preflight):
    assert run_preflight(account="U1234567") == 1
    assert FakeBroker.instances == []


def test_missing_market_data_fails(run_preflight, monkeypatch, caplog):
    """Every rebalance prices every symbol, so no quote means no trading day."""
    monkeypatch.setattr(FakeBroker, "prices", {})
    assert run_preflight() == 1
    assert "market data" in caplog.text.lower() or "no quote" in caplog.text.lower()


def test_always_disconnects(run_preflight, monkeypatch):
    monkeypatch.setattr(FakeBroker, "prices", {})
    run_preflight()
    assert FakeBroker.instances[0].disconnected
