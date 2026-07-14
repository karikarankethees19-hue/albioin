"""Tests for the fee-shredder autopsy + rolling-window machinery."""
from __future__ import annotations

import numpy as np
import pandas as pd

from gsf import engine as eng
from gsf import metrics, windows
from gsf.costs import CryptoCost


def _frame(n, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="5min"),
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.abs(rng.normal(100, 10, n)),
        }
    )


def test_zero_cost_gross_equals_net():
    df = _frame(2000)
    desired = pd.Series(np.where(df["close"].diff().fillna(0) > 0, 1.0, 0.0), index=df.index)
    res = eng.run(df, desired, CryptoCost(0.0), execution="next_open")
    assert abs(res.gross_equity.iloc[-1] - res.equity.iloc[-1]) < 1e-9
    a = metrics.autopsy(res)
    assert abs(a["gross_return"] - a["net_return"]) < 1e-9
    assert a["cost_drag"] < 1e-9


def test_costs_only_reduce_net_and_scale_with_turnover():
    df = _frame(3000, seed=3)
    # a whippy signal: flip on every up/down bar -> maximum turnover
    flips = np.where(df["close"].diff().fillna(0) > 0, 1.0, 0.0)
    desired = pd.Series(flips, index=df.index)
    cheap = eng.run(df, desired, CryptoCost(0.0004), execution="next_open")
    dear = eng.run(df, desired, CryptoCost(0.001), execution="next_open")
    # higher fee => strictly lower net, same gross
    assert dear.equity.iloc[-1] < cheap.equity.iloc[-1]
    assert abs(dear.gross_equity.iloc[-1] - cheap.gross_equity.iloc[-1]) < 1e-9
    assert metrics.autopsy(dear)["cost_drag"] > metrics.autopsy(cheap)["cost_drag"]


def test_rolling_produces_windows_with_autopsy_fields():
    df = _frame(6000, seed=5)
    desired = pd.Series(np.where(df["close"].diff().fillna(0) > 0, 1.0, 0.0), index=df.index)
    r = windows.rolling(df, desired, CryptoCost(0.001), window_days=5, step_days=2)
    assert len(r) >= 2
    for col in ["excess", "cost_share_of_gross", "trades_per_day", "gross_ret"]:
        assert col in r.columns


if __name__ == "__main__":
    import pytest, sys

    sys.exit(pytest.main([__file__, "-q"]))
