"""Typed config loading. One YAML file is the entire control surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .risk import RiskLimits
from .strategies import BuyAndHold, CrossSectionalMomentum
from .strategies.base import Strategy

STRATEGY_REGISTRY: dict[str, type] = {
    "buy_and_hold": BuyAndHold,
    "xsec_momentum": CrossSectionalMomentum,
}


@dataclass
class SleeveConfig:
    name: str
    strategy: str
    allocation: float
    params: dict[str, Any] = field(default_factory=dict)

    def build(self) -> Strategy:
        try:
            cls = STRATEGY_REGISTRY[self.strategy]
        except KeyError:
            raise KeyError(
                f"unknown strategy '{self.strategy}'. "
                f"Registered: {sorted(STRATEGY_REGISTRY)}"
            ) from None
        return cls(name=self.name, **self.params)


@dataclass
class Config:
    risk_free_annual_cmt_percent: float
    target_annual_vol: float
    sleeves: list[SleeveConfig]
    limits: RiskLimits
    broker: str = "sim"
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 4002
    ibkr_client_id: int = 17
    no_trade_band: float = 0.005
    dry_run: bool = True

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text())
        sleeves = [
            SleeveConfig(
                name=s["name"],
                strategy=s["strategy"],
                allocation=float(s.get("allocation", 0.0)),
                params=s.get("params", {}) or {},
            )
            for s in raw.get("sleeves", [])
        ]
        total = sum(s.allocation for s in sleeves)
        if total > 1.0 + 1e-9:
            raise ValueError(f"sleeve allocations sum to {total:.3f}, above 1.0")

        return cls(
            risk_free_annual_cmt_percent=float(raw["risk_free_annual_cmt_percent"]),
            target_annual_vol=float(raw.get("target_annual_vol", 0.08)),
            sleeves=sleeves,
            limits=RiskLimits(**(raw.get("risk_limits") or {})),
            broker=raw.get("broker", "sim"),
            ibkr_host=raw.get("ibkr", {}).get("host", "127.0.0.1"),
            ibkr_port=int(raw.get("ibkr", {}).get("port", 4002)),
            ibkr_client_id=int(raw.get("ibkr", {}).get("client_id", 17)),
            no_trade_band=float(raw.get("no_trade_band", 0.005)),
            dry_run=bool(raw.get("dry_run", True)),
        )

    @property
    def allocations(self) -> dict[str, float]:
        return {s.name: s.allocation for s in self.sleeves}

    @property
    def universe(self) -> list[str]:
        symbols: set[str] = set()
        for sleeve in self.sleeves:
            symbols.update(sleeve.build().universe)
        return sorted(symbols)
