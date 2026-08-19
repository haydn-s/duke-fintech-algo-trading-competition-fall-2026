"""Daily price data with a local parquet cache.

Daily bars only. The competition observes end-of-day NAV and nothing else, so
intraday data would add cost, complexity, and storage for information that
cannot show up in the score.

The cache is append-only and lives outside git. Refetching a full history on
every run is slow and, on some vendors, rate-limited into failure right when
you need the run to succeed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_CACHE = Path("data/prices.parquet")


def load_cache(path: Path = DEFAULT_CACHE) -> pd.DataFrame:
    """Adjusted closes: dates on the index, symbols on the columns."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path).sort_index()


def save_cache(prices: pd.DataFrame, path: Path = DEFAULT_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prices.sort_index().to_parquet(path)


def update_cache(new_rows: pd.DataFrame, path: Path = DEFAULT_CACHE) -> pd.DataFrame:
    """Merge freshly fetched bars into the cache, newest values winning."""
    existing = load_cache(path)
    merged = (
        new_rows
        if existing.empty
        else pd.concat([existing, new_rows]).groupby(level=0).last()
    )
    merged = merged.sort_index()
    save_cache(merged, path)
    return merged


def fetch_from_ibkr(broker, symbols: list[str], days: int = 400) -> pd.DataFrame:
    """Pull daily bars from IBKR so the project needs no second data vendor.

    Args:
        broker: A connected ``IBKRBroker``.
        symbols: Symbols to fetch.
        days: Calendar days of history.
    """
    frames: dict[str, pd.Series] = {}
    for symbol in symbols:
        bars = broker.ib.reqHistoricalData(
            broker._contract(symbol),
            endDateTime="",
            durationStr=f"{days} D",
            barSizeSetting="1 day",
            whatToShow="ADJUSTED_LAST",
            useRTH=True,
        )
        if not bars:
            continue
        frames[symbol] = pd.Series(
            {pd.Timestamp(b.date): float(b.close) for b in bars}
        )
    return pd.DataFrame(frames).sort_index()


def require_history(prices: pd.DataFrame, symbols: list[str], min_days: int) -> None:
    missing = [s for s in symbols if s not in prices.columns]
    if missing:
        raise ValueError(f"no price history for {missing}")
    if len(prices) < min_days:
        raise ValueError(
            f"need {min_days} days of history, cache holds {len(prices)}"
        )
