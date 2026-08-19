"""Live broker: Interactive Brokers via a running IB Gateway.

Uses ib_async, the maintained community fork of ib_insync. The import is
deliberately deferred to call time so that the test suite, CI, and every
backtest run without the dependency installed or a gateway reachable.

Expects IB Gateway (or TWS) already authenticated and listening. The paper
account default port is 4002 for Gateway, 7497 for TWS.
"""

from __future__ import annotations

from datetime import date

from .base import Order, Position


class IBKRBroker:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 17,
        account: str | None = None,
        read_only: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self.read_only = read_only
        self._ib = None
        self._contracts: dict[str, object] = {}

    def __enter__(self) -> "IBKRBroker":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.disconnect()

    def connect(self) -> None:
        from ib_async import IB

        self._ib = IB()
        self._ib.connect(
            self.host, self.port, clientId=self.client_id, readonly=self.read_only
        )

    def disconnect(self) -> None:
        if self._ib is not None:
            self._ib.disconnect()
            self._ib = None

    @property
    def ib(self):
        if self._ib is None:
            raise RuntimeError("not connected -- call connect() first")
        return self._ib

    def _contract(self, symbol: str):
        from ib_async import Stock

        if symbol not in self._contracts:
            c = Stock(symbol, "SMART", "USD")
            self.ib.qualifyContracts(c)
            self._contracts[symbol] = c
        return self._contracts[symbol]

    def today(self) -> date:
        return date.today()

    def net_asset_value(self) -> float:
        for row in self.ib.accountSummary(self.account or ""):
            if row.tag == "NetLiquidation":
                return float(row.value)
        raise RuntimeError("NetLiquidation not reported by IBKR")

    def positions(self) -> dict[str, Position]:
        out: dict[str, Position] = {}
        for p in self.ib.positions(self.account or ""):
            sym = p.contract.symbol
            out[sym] = Position(sym, float(p.position), float(p.avgCost))
        return out

    def last_price(self, symbol: str) -> float:
        ticker = self.ib.reqMktData(self._contract(symbol), snapshot=True)
        self.ib.sleep(2)
        for candidate in (ticker.marketPrice(), ticker.close, ticker.last):
            if candidate and candidate == candidate:  # excludes NaN
                return float(candidate)
        raise RuntimeError(f"no usable price for {symbol}")

    def place_order(self, order: Order) -> None:
        from ib_async import MarketOrder

        qty = int(round(order.quantity))
        if qty == 0:
            return
        self.ib.placeOrder(
            self._contract(order.symbol), MarketOrder(order.side, abs(qty))
        )
