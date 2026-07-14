"""Transaction cost models, expressed as a *per-side* fraction of notional.

Cost is charged on every side of every position change (turnover):
    - opening a position pays one side,
    - closing pays one side,
    - a flip (+1 -> -1) pays two sides (close + open).

So a full round trip (enter + exit) = 2 sides. This is the honest accounting:
you cannot enter or exit for free, and whipsaw is punished by construction.

Two asset-class models:
    - CryptoCost: taker fee % per side (+ optional half-spread), price-independent.
    - FxCost: quoted in pips per *round trip*; converted to a per-side price
      fraction using the live price (a pip is absolute, so its fractional cost
      drifts slightly with price — we compute it per bar).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class CostModel:
    def per_side_fraction(self, price: pd.Series) -> pd.Series:  # pragma: no cover
        """Per-side cost as a fraction of notional, aligned to `price`."""
        raise NotImplementedError


@dataclass(frozen=True)
class CryptoCost(CostModel):
    """Crypto exchange fees. ``taker_per_side`` and ``half_spread`` are fractions.

    Retail Crypto.com taker ~0.10%/side -> taker_per_side=0.001.
    VIP tier ~0.04%/side -> 0.0004. Add half_spread for the touch you cross.
    """

    taker_per_side: float = 0.001  # 0.10% retail default
    half_spread: float = 0.0

    def per_side_fraction(self, price: pd.Series) -> pd.Series:
        val = self.taker_per_side + self.half_spread
        return pd.Series(np.full(len(price), val), index=price.index)


@dataclass(frozen=True)
class FxCost(CostModel):
    """FX spot cost quoted in pips per round trip (spread + slippage).

    ``pips_round_trip`` is split evenly across the two sides. ``pip_size`` is the
    price increment of one pip (1e-4 for most majors, 1e-2 for JPY pairs).
    """

    pips_round_trip: float = 1.5
    pip_size: float = 1e-4

    def per_side_fraction(self, price: pd.Series) -> pd.Series:
        pips_per_side = self.pips_round_trip / 2.0
        return (pips_per_side * self.pip_size) / price


def build_cost(asset_class: str, **kwargs) -> CostModel:
    ac = asset_class.lower()
    if ac in ("crypto", "cx"):
        return CryptoCost(**kwargs)
    if ac in ("fx", "forex"):
        return FxCost(**kwargs)
    raise ValueError(f"unknown asset_class {asset_class!r}")
