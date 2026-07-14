"""Rolling / per-year window analysis to expose regime dependence.

A strategy that only "works" in one regime (e.g. trend-following in a bull
market) will show wildly different per-year results. Running the same strategy
across consecutive calendar-year windows — with indicators warmed on the full
history and only the *reporting* window sliced — makes that dependence explicit
instead of hiding it inside one flattering multi-year number.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data, metrics
from . import engine as eng
from .costs import CryptoCost, FxCost
from .strategies import get as get_strategy


def _make_strategy(name: str, allow_short: bool):
    cls = get_strategy(name)
    return cls(allow_short=allow_short)


def per_year(
    symbol: str,
    strategy: str,
    asset: str = "crypto",
    allow_short: bool = False,
    timeframe: str = "1d",
    taker: float = 0.001,
    pips: float = 1.5,
    years: range | None = None,
) -> pd.DataFrame:
    """Backtest ``strategy`` on ``symbol`` for each calendar year and tabulate.

    Returns a DataFrame indexed by year with strategy vs buy-and-hold columns.
    """
    df = data.load_ohlcv(symbol, timeframe)
    desired = _make_strategy(strategy, allow_short).positions(df)
    cost = CryptoCost(taker_per_side=taker) if asset == "crypto" else FxCost(pips_round_trip=pips)

    yrs = years or range(df["timestamp"].dt.year.min(), df["timestamp"].dt.year.max() + 1)
    rows = []
    for y in yrs:
        start, end = f"{y}-01-01", f"{y}-12-31"
        sub = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]
        if len(sub) < 20:  # skip thin/partial years
            continue
        res = eng.run(df, desired, cost, execution="next_open", start=start, end=end)
        s = metrics.summarize(res)
        rows.append(
            {
                "year": y,
                "strat_ret": s["total_return"],
                "bh_ret": s["bh_total_return"],
                "excess": s["total_return"] - s["bh_total_return"],
                "maxDD": s["max_drawdown"],
                "trades": s["trades"],
            }
        )
    return pd.DataFrame(rows).set_index("year")


def rolling(
    df: pd.DataFrame,
    desired: pd.Series,
    cost,
    window_days: int,
    step_days: int,
    execution: str = "next_open",
) -> pd.DataFrame:
    """Roll a fixed-length window across the data and backtest each placement.

    Works on any timeframe (this is the intraday path). Indicators are warmed on
    the full ``df``; each window only restricts the reporting range. Returns one
    row per window start with strategy vs buy-and-hold and fee autopsy fields.
    """
    ts = pd.to_datetime(df["timestamp"])
    t0, t1 = ts.iloc[0], ts.iloc[-1]
    wlen = pd.Timedelta(days=window_days)
    step = pd.Timedelta(days=step_days)

    rows = []
    start = t0
    while start + wlen <= t1 + pd.Timedelta(days=1):
        end = start + wlen
        res = eng.run(df, desired, cost, execution=execution,
                      start=str(start), end=str(end))
        if res.meta["bars"] >= 50:
            s = metrics.summarize(res)
            a = metrics.autopsy(res)
            rows.append(
                {
                    "win_start": start.date(),
                    "win_end": end.date(),
                    "strat_ret": s["total_return"],
                    "gross_ret": a["gross_return"],
                    "bh_ret": s["bh_total_return"],
                    "excess": s["total_return"] - s["bh_total_return"],
                    "cost_share_of_gross": a["cost_share_of_gross"],
                    "maxDD": s["max_drawdown"],
                    "trades": s["trades"],
                    "trades_per_day": a["trades_per_day"],
                }
            )
        start = start + step
    return pd.DataFrame(rows)


def format_year_table(dfy: pd.DataFrame, title: str) -> str:
    lines = [title, "-" * len(title), f"{'year':>6}  {'strat':>9}  {'buy&hold':>9}  {'excess':>9}  {'maxDD':>8}  {'trades':>6}"]
    for y, r in dfy.iterrows():
        lines.append(
            f"{y:>6}  {r['strat_ret']*100:>+8.1f}%  {r['bh_ret']*100:>+8.1f}%  "
            f"{r['excess']*100:>+8.1f}%  {r['maxDD']*100:>+7.1f}%  {int(r['trades']):>6}"
        )
    # regime summary
    beat = int((dfy["excess"] > 0).sum())
    n = len(dfy)
    lines.append("-" * len(title))
    lines.append(f"beat buy&hold in {beat}/{n} years  |  median excess {dfy['excess'].median()*100:+.1f}%")
    return "\n".join(lines)
