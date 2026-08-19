import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def prices() -> pd.DataFrame:
    """Deterministic synthetic prices with a clear momentum ordering."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=300)
    drifts = {"AAA": 0.0008, "BBB": 0.0004, "CCC": 0.0, "DDD": -0.0004, "EEE": -0.0008, "FFF": 0.0002}
    frame = {}
    for symbol, drift in drifts.items():
        # Noise is deliberately small relative to drift so the momentum
        # ordering is deterministic rather than a coin flip on the seed.
        shocks = rng.normal(drift, 0.004, len(dates))
        frame[symbol] = 100.0 * np.exp(np.cumsum(shocks))
    return pd.DataFrame(frame, index=dates)
