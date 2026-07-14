"""RSI oversold/overbought — buy < 30, sell > 70 (Wilder's RSI, default period 14).

Prediction on the hit list: destroyed on trending pairs (mean-reversion meat
grinder) — it fades exactly the moves a trend keeps extending.

Interpretation of "buy < 30 / sell > 70" as a stateful position (the way it is
actually traded, not a per-bar in/out flicker): go long when RSI drops below the
oversold line and hold until RSI reaches the overbought line; with shorts
enabled, then flip short and hold until oversold. This is non-repainting: RSI at
bar t uses closes through t, and the position is carried forward deterministically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy, register


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing == EMA with alpha = 1/period.
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi.fillna(50.0)


@register("rsi")
class Rsi(Strategy):
    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        allow_short: bool = False,
    ):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.allow_short = allow_short

    def positions(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)
        rsi = wilder_rsi(close, self.period)
        rsi_arr = rsi.to_numpy()

        pos = np.zeros(len(df))
        cur = 0.0
        short_val = -1.0 if self.allow_short else 0.0
        for i, r in enumerate(rsi_arr):
            if i < self.period:
                pos[i] = 0.0
                continue
            if r < self.oversold:
                cur = 1.0
            elif r > self.overbought:
                cur = short_val
            # else: hold current position (band between the lines)
            pos[i] = cur
        return pd.Series(pos, index=df.index)
