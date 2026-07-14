"""Vectorized, look-ahead-free backtest engine.

Contract with strategies
------------------------
A strategy sees a full OHLCV DataFrame and returns a `desired` position series
in {-1, 0, +1}, where ``desired[t]`` is the position you *want* as of the close
of bar ``t`` (computed only from data up to and including bar ``t``). It is the
engine's job — never the strategy's — to impose execution delay and costs.

Execution models
----------------
Because a signal is only *known* at bar t's close, you cannot trade on bar t's
own open/close-that-formed-it. The engine holds ``desired.shift(1)`` and marks
it against:

  * ``next_open`` (v2, preferred): return over [open[t], open[t+1]]. To hold a
    position at open[t] you needed the signal at close[t-1] -> no look-ahead.
    Transaction price at a position change on bar t is ``open[t]``.

  * ``close_to_close`` (v1): signal at close[t] executes at that same close and
    earns close[t] -> close[t+1]. Equivalent to holding ``desired.shift(1)``
    against close-to-close returns. Transaction price is ``close[t-1]``. This
    reproduces the "signal at close, executed at same close" convention.

Costs are charged per side on every unit of turnover ``|Δpos|`` (see costs.py),
applied as a negative return on the bar where the position changes.

Outputs (BacktestResult)
------------------------
  equity     : bar-level mark-to-market equity curve (starts at 1.0)
  bh_equity  : buy-and-hold benchmark on the same window (starts at 1.0)
  trades     : one row per completed round trip (entry/exit/side/pnl)
  returns    : per-bar net strategy return
Everything is derived from the single ``pos`` series, so stats are mutually
consistent.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import CostModel

EXECUTIONS = ("next_open", "close_to_close")


@dataclass
class BacktestResult:
    equity: pd.Series
    bh_equity: pd.Series
    returns: pd.Series
    trades: pd.DataFrame
    pos: pd.Series
    price: pd.Series  # price series used for buy-and-hold / marking
    meta: dict
    gross_equity: pd.Series = None  # equity with zero transaction cost
    cost_returns: pd.Series = None  # per-bar cost drag (>= 0), windowed


def run(
    df: pd.DataFrame,
    desired: pd.Series,
    cost: CostModel,
    execution: str = "next_open",
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    """Backtest ``desired`` positions over ``df`` and return a BacktestResult.

    Indicators/positions are computed on the *full* ``df`` (warm) by the caller;
    ``start``/``end`` then restrict the traded/return window without discarding
    the warmup used to form the signal.
    """
    if execution not in EXECUTIONS:
        raise ValueError(f"execution must be one of {EXECUTIONS}")

    df = df.reset_index(drop=True)
    desired = pd.Series(np.asarray(desired, dtype=float), index=df.index)
    if not desired.isin([-1.0, 0.0, 1.0]).all():
        raise ValueError("desired positions must be in {-1, 0, 1}")

    ts = df["timestamp"]
    open_, close = df["open"].astype(float), df["close"].astype(float)

    # Position actually *held* over each bar = signal known one bar earlier.
    pos = desired.shift(1).fillna(0.0)

    if execution == "next_open":
        mark = open_
        # Return realised over bar t while holding pos[t]: open[t] -> open[t+1].
        bar_ret = open_.shift(-1) / open_ - 1.0
        txn_price = open_  # price paid when pos changes on bar t
    else:  # close_to_close
        mark = close
        # pos (= desired.shift(1)) held over bar t earns close[t-1] -> close[t];
        # i.e. the signal formed at close[t-1] executes at that same close.
        bar_ret = close.pct_change()
        txn_price = close.shift(1)  # change on bar t transacts at close[t-1]

    # Cost drag on bars where the held position changes.
    turnover = pos.diff().abs().fillna(pos.abs())
    per_side = cost.per_side_fraction(txn_price.bfill().ffill())
    cost_ret = (per_side * turnover).fillna(0.0)

    gross_ret = (pos * bar_ret).fillna(0.0)
    net_ret = gross_ret - cost_ret

    # Restrict to the trading window (keep warmup out of the reported curve).
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= ts >= pd.Timestamp(start)
    if end is not None:
        mask &= ts <= pd.Timestamp(end)
    win = df.index[mask]

    net_w = net_ret.loc[win]
    equity = (1.0 + net_w).cumprod()
    equity.index = ts.loc[win]

    gross_w = gross_ret.loc[win]
    gross_equity = (1.0 + gross_w).cumprod()
    gross_equity.index = ts.loc[win]
    cost_w = cost_ret.loc[win].copy()
    cost_w.index = ts.loc[win]

    price_w = mark.loc[win]
    bh_ret = price_w.pct_change().fillna(0.0)
    bh_equity = (1.0 + bh_ret).cumprod()
    bh_equity.index = ts.loc[win]

    trades = _extract_trades(
        ts=ts, pos=pos, txn_price=txn_price, cost=cost, window=win, execution=execution
    )

    returns = net_w.copy()
    returns.index = ts.loc[win]

    meta = {
        "execution": execution,
        "start": str(ts.loc[win].iloc[0].date()) if len(win) else None,
        "end": str(ts.loc[win].iloc[-1].date()) if len(win) else None,
        "bars": int(len(win)),
    }
    return BacktestResult(
        equity, bh_equity, returns, trades, pos.loc[win], price_w, meta,
        gross_equity=gross_equity, cost_returns=cost_w,
    )


def _extract_trades(ts, pos, txn_price, cost, window, execution) -> pd.DataFrame:
    """Reconstruct discrete round-trip trades from the held-position series.

    A trade is a contiguous run of a constant non-zero position. Its entry/exit
    prices are the transaction prices at the run's boundaries; net P&L is the
    directional price move minus one side of cost at each boundary. Only trades
    whose *entry* falls inside the reporting window are counted, so stats align
    with the windowed equity curve.
    """
    p = pos.to_numpy()
    n = len(p)
    price = txn_price.to_numpy()
    win_set = set(window)

    rows = []
    i = 0
    # bar 0 has no prior transaction price under close_to_close; positions there
    # are 0 anyway (shift fill), so the walk below naturally skips it.
    while i < n:
        side = p[i]
        if side == 0.0:
            i += 1
            continue
        j = i
        while j + 1 < n and p[j + 1] == side:
            j += 1
        entry_idx, exit_idx = i, j + 1  # position exits when it changes at j+1
        if exit_idx >= n:
            break  # position still open at series end -> not a completed trade
        entry_px = price[entry_idx]
        exit_px = price[exit_idx]
        if np.isnan(entry_px) or np.isnan(exit_px):
            i = j + 1
            continue
        gross = side * (exit_px / entry_px - 1.0)
        # one side of cost at entry and at exit, as fractions of notional
        c_entry = cost.per_side_fraction(pd.Series([entry_px])).iloc[0]
        c_exit = cost.per_side_fraction(pd.Series([exit_px])).iloc[0]
        net = gross - c_entry - c_exit
        if entry_idx in win_set:
            rows.append(
                {
                    "entry_time": ts.iloc[entry_idx],
                    "exit_time": ts.iloc[exit_idx],
                    "side": int(side),
                    "entry_px": entry_px,
                    "exit_px": exit_px,
                    "gross_ret": gross,
                    "net_ret": net,
                }
            )
        i = j + 1

    return pd.DataFrame(
        rows,
        columns=[
            "entry_time",
            "exit_time",
            "side",
            "entry_px",
            "exit_px",
            "gross_ret",
            "net_ret",
        ],
    )
