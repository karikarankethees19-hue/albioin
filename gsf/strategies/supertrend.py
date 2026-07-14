"""Supertrend — ATR-banded trend follower. Guru pitch: "green = buy, red = sell."

Classic formulation (Wilder ATR + causal band carry-forward). The direction can
only change on a *close* that pierces the opposite final band, and every band at
bar t uses data through bar t only — so it is non-repainting. The engine adds
the one-bar execution delay.

direction +1 -> long ; direction -1 -> short (if allow_short) else flat.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy, register


def wilder_atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


@register("supertrend")
class Supertrend(Strategy):
    def __init__(self, period: int = 10, multiplier: float = 3.0, allow_short: bool = False):
        self.period = period
        self.multiplier = multiplier
        self.allow_short = allow_short

    def positions(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float).to_numpy()
        hl2 = ((df["high"] + df["low"]) / 2.0).to_numpy()
        atr = wilder_atr(df, self.period).to_numpy()

        n = len(df)
        upper = hl2 + self.multiplier * atr
        lower = hl2 - self.multiplier * atr
        final_upper = np.full(n, np.nan)
        final_lower = np.full(n, np.nan)
        direction = np.ones(n)  # +1 up, -1 down

        for i in range(n):
            if i == 0 or np.isnan(atr[i]):
                final_upper[i] = upper[i]
                final_lower[i] = lower[i]
                direction[i] = 1.0
                continue
            final_upper[i] = (
                upper[i]
                if (upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1])
                else final_upper[i - 1]
            )
            final_lower[i] = (
                lower[i]
                if (lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1])
                else final_lower[i - 1]
            )
            if close[i] > final_upper[i - 1]:
                direction[i] = 1.0
            elif close[i] < final_lower[i - 1]:
                direction[i] = -1.0
            else:
                direction[i] = direction[i - 1]

        pos = np.where(direction > 0, 1.0, -1.0 if self.allow_short else 0.0)
        out = pd.Series(pos, index=df.index)
        out.iloc[: self.period] = 0.0  # warmup: ATR not yet meaningful
        return out
