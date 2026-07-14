"""EMA fast/slow crossover — the canonical "just follow 3 rules" Reel strategy.

Rules as sold: when the fast EMA crosses above the slow EMA, go long; when it
crosses below, exit (long-only) or flip short (long/short). Default 9/21.

Non-repainting: EMAs use only past+current closes (ewm, adjust=False), and the
position for bar t is a pure function of EMAs through bar t. The engine adds the
one-bar execution delay, so there is no look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy, register


def _ema(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, adjust=False).mean()


@register("ema_cross")
class EmaCross(Strategy):
    def __init__(self, fast: int = 9, slow: int = 21, allow_short: bool = False):
        if fast >= slow:
            raise ValueError("fast span must be < slow span")
        self.fast = fast
        self.slow = slow
        self.allow_short = allow_short

    def positions(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)
        ef, es = _ema(close, self.fast), _ema(close, self.slow)
        long = ef > es
        if self.allow_short:
            pos = np.where(long, 1.0, -1.0)
        else:
            pos = np.where(long, 1.0, 0.0)
        out = pd.Series(pos, index=df.index)
        # No position until both EMAs have enough history to differ meaningfully.
        out.iloc[: self.slow] = 0.0
        return out
