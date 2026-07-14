"""Strategy-level tests: signal sanity, no-repaint, intraday session logic."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gsf.strategies import get as get_strategy
from gsf.strategies.supertrend import Supertrend
from gsf.strategies.intraday import VwapBounce, OpeningRangeBreakout


def _daily(closes, highs=None, lows=None):
    n = len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=n, freq="D"),
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1.0] * n,
        }
    )


def _intraday(prices, vols=None, minutes=5, start="2024-01-01 00:00"):
    n = len(prices)
    vols = vols or [1.0] * n
    ts = pd.date_range(start, periods=n, freq=f"{minutes}min")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": prices,
            "high": [p * 1.001 for p in prices],
            "low": [p * 0.999 for p in prices],
            "close": prices,
            "volume": vols,
        }
    )


def test_positions_are_ternary():
    df = _daily(list(np.linspace(100, 120, 60)))
    for name in ["ema_cross", "rsi", "supertrend"]:
        pos = get_strategy(name)().positions(df)
        assert set(np.unique(pos.values)).issubset({-1.0, 0.0, 1.0})


def test_supertrend_goes_long_in_clean_uptrend():
    df = _daily(list(np.linspace(100, 200, 80)))
    pos = Supertrend(period=10, multiplier=3.0).positions(df)
    # after warmup a persistent uptrend should be held long most of the time
    assert pos.iloc[20:].mean() > 0.8


def test_supertrend_no_repaint_prefix_stable():
    # Extending the series with future bars must not change past positions
    # (causal indicator). Compare a prefix computed alone vs within the full run.
    full = _daily(list(np.linspace(100, 160, 90)) + list(np.linspace(160, 120, 30)))
    pos_full = Supertrend().positions(full)
    prefix = full.iloc[:90].reset_index(drop=True)
    pos_prefix = Supertrend().positions(prefix)
    # first 90 positions must match (Supertrend at t uses only <= t)
    assert np.allclose(pos_full.iloc[:90].values, pos_prefix.values)


def test_intraday_strategies_reject_daily():
    df = _daily(list(np.linspace(100, 120, 40)))
    with pytest.raises(ValueError):
        VwapBounce().positions(df)
    with pytest.raises(ValueError):
        OpeningRangeBreakout().positions(df)


def test_vwap_long_above_flat_below():
    # Rising then falling within one session: long while above VWAP, flat below.
    prices = [100, 101, 102, 103, 104, 103, 100, 98, 96, 95, 94, 93]
    df = _intraday(prices)
    pos = VwapBounce().positions(df)
    assert set(np.unique(pos.values)).issubset({0.0, 1.0})
    assert pos.iloc[3] == 1.0  # clearly above session VWAP early
    assert pos.iloc[-1] == 0.0  # below VWAP late


def test_orb_breakout_and_flat_at_session_end():
    # Opening range = first 15 min = first three 5-min bars. Then a break up.
    prices = [100, 100.5, 100.2, 101.5, 102, 102.5, 101.8, 103]
    df = _intraday(prices, minutes=5)
    pos = OpeningRangeBreakout(or_minutes=15).positions(df)
    assert (pos.iloc[:3] == 0.0).all()  # no trading during the opening range
    assert pos.iloc[3] == 1.0  # broke above OR high
    assert pos.iloc[-1] == 0.0  # flat at session end


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
