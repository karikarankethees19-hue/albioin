"""Session-aware intraday strategies: VWAP bounce and Opening-Range Breakout.

Both are meaningless on daily bars — VWAP needs many bars per session to form,
ORB needs the first N minutes of a session — so they require sub-daily data and
raise a clear error otherwise. Sessions are grouped by calendar date of the bar
timestamp (crypto trades 24/7, so a "session" is a UTC day; for equities/FX the
same grouping works once the feed is already session-scoped).

These run unchanged once a 5-minute cache exists (see scripts/fetch_ccxt.py).
Everything is causal: VWAP and the opening range at bar t use only bars up to t
within the same session, and the engine adds the one-bar execution delay.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy, register


def _require_intraday(df: pd.DataFrame) -> pd.Series:
    ts = pd.to_datetime(df["timestamp"])
    deltas = ts.diff().dropna()
    if len(deltas) and deltas.median() >= pd.Timedelta(days=1):
        raise ValueError(
            "intraday strategy needs sub-daily bars; got ~daily spacing. "
            "Populate a 5m/15m cache via scripts/fetch_ccxt.py."
        )
    return ts


def _sessions(ts: pd.Series) -> pd.Series:
    return ts.dt.normalize()  # calendar-day session key


@register("vwap_bounce")
class VwapBounce(Strategy):
    """Long while price holds above the session VWAP (support); flat below it.

    The guru "bounce" framing = buy when price reclaims VWAP and ride it; step
    aside when it loses VWAP. Coded as: position 1 when close > session VWAP,
    else 0 (or short if enabled). VWAP is cumulative within the session only.
    """

    def __init__(self, allow_short: bool = False):
        self.allow_short = allow_short

    def positions(self, df: pd.DataFrame) -> pd.Series:
        ts = _require_intraday(df)
        session = _sessions(ts)
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["volume"].replace(0.0, np.nan)
        pv = (typical * vol).groupby(session).cumsum()
        cum_v = vol.groupby(session).cumsum()
        vwap = pv / cum_v
        above = df["close"] > vwap
        pos = np.where(above, 1.0, -1.0 if self.allow_short else 0.0)
        out = pd.Series(pos, index=df.index)
        out[vwap.isna()] = 0.0  # first bar(s) of a session before VWAP exists
        return out


@register("orb")
class OpeningRangeBreakout(Strategy):
    """Opening-Range Breakout: mark the first ``or_minutes`` of each session,
    then go long on a break above that range's high (short below its low if
    enabled). Positions are forced flat at session end (no overnight risk),
    matching how ORB is actually traded.
    """

    def __init__(self, or_minutes: int = 15, allow_short: bool = False):
        self.or_minutes = or_minutes
        self.allow_short = allow_short

    def positions(self, df: pd.DataFrame) -> pd.Series:
        ts = _require_intraday(df)
        session = _sessions(ts)
        out = np.zeros(len(df))

        for _key, idx in df.groupby(session).groups.items():
            g = df.loc[idx]
            gts = ts.loc[idx]
            start = gts.iloc[0]
            in_or = gts < start + pd.Timedelta(minutes=self.or_minutes)
            if in_or.all() or (~in_or).sum() == 0:
                continue  # session too short to have a post-range
            or_high = g.loc[in_or.values, "high"].max()
            or_low = g.loc[in_or.values, "low"].min()
            cur = 0.0
            positions = []
            for _i, (c, isor) in enumerate(zip(g["close"].to_numpy(), in_or.to_numpy())):
                if isor:
                    positions.append(0.0)  # no trading during the opening range
                    continue
                if c > or_high:
                    cur = 1.0
                elif c < or_low:
                    cur = -1.0 if self.allow_short else 0.0
                positions.append(cur)
            # force flat on the last bar of the session
            if positions:
                positions[-1] = 0.0
            out[[df.index.get_loc(j) for j in idx]] = positions
        return pd.Series(out, index=df.index)
