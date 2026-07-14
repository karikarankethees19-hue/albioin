"""Engine correctness tests — the properties that make a backtest honest.

Run: python -m pytest -q   (or: python tests/test_engine.py)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from gsf import engine as eng
from gsf.costs import CryptoCost, FxCost


def _frame(closes, opens=None):
    n = len(closes)
    opens = closes if opens is None else opens
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=n, freq="D"),
            "open": opens,
            "high": [max(o, c) for o, c in zip(opens, closes)],
            "low": [min(o, c) for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [1.0] * n,
        }
    )


def test_always_long_equals_buy_and_hold_minus_one_entry_cost():
    # A constant long position never turns over after entry, so strategy equity
    # must equal buy-and-hold except for the single entry cost.
    closes = [100, 101, 102, 99, 105, 110]
    df = _frame(closes)
    desired = pd.Series(1.0, index=df.index)
    cost = CryptoCost(taker_per_side=0.001)
    res = eng.run(df, desired, cost, execution="close_to_close")
    # buy&hold final / strategy final ~= (1 + one entry cost)
    ratio = res.bh_equity.iloc[-1] / res.equity.iloc[-1]
    assert abs(ratio - 1.0) < 0.0011 + 1e-9  # one side of 0.1%


def test_no_lookahead_signal_uses_only_past():
    # If the engine leaked the future, a "buy the bar that goes up" oracle using
    # desired[t] tied to bar t's own close-to-next move would be free money at
    # zero cost. With correct one-bar delay, a signal known only at close[t] can
    # act no earlier than the next bar — so a *shift-invariant* check holds:
    # feeding desired vs desired shifted must change results (delay is real).
    closes = [100, 102, 101, 105, 103, 108, 107]
    df = _frame(closes)
    desired = pd.Series([0, 1, 1, 1, 0, 1, 1], index=df.index, dtype=float)
    cost = CryptoCost(0.0)
    r1 = eng.run(df, desired, cost, execution="close_to_close")
    # Manually: pos = desired.shift(1); ret = close.pct_change(); strat=pos*ret
    pos = desired.shift(1).fillna(0.0)
    ret = df["close"].pct_change().fillna(0.0)
    expected = float((1 + pos * ret).prod())
    assert abs(res_final(r1) - expected) < 1e-9


def res_final(res):
    return float(res.equity.iloc[-1])


def test_round_trip_charges_two_sides():
    # One clean long round trip at zero price change must lose exactly two sides
    # of cost (entry + exit), nothing more.
    closes = [100, 100, 100, 100, 100]
    df = _frame(closes)
    # long during bars where pos=desired.shift(1) is 1: enter then exit once.
    desired = pd.Series([0, 1, 1, 0, 0], index=df.index, dtype=float)
    taker = 0.002
    res = eng.run(df, desired, CryptoCost(taker_per_side=taker), execution="close_to_close")
    assert len(res.trades) == 1
    tr = res.trades.iloc[0]
    assert abs(tr["net_ret"] - (-2 * taker)) < 1e-9  # flat price, only fees


def test_next_open_uses_open_prices():
    # With next_open execution and a step in opens, P&L must track open-to-open,
    # independent of closes.
    opens = [10, 10, 11, 11, 11]
    closes = [10, 10, 10, 10, 10]
    df = _frame(closes, opens=opens)
    desired = pd.Series([1, 1, 1, 1, 1], index=df.index, dtype=float)
    res = eng.run(df, desired, CryptoCost(0.0), execution="next_open")
    # held from open[1] onward; open 10->10->11->11 => +10% realised once
    assert res.equity.iloc[-1] > 1.09  # ~ +10%


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all engine tests passed")
