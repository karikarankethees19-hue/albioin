"""Strategy base class + registry.

A Strategy maps an OHLCV frame to a `desired` position series in {-1, 0, +1},
using ONLY information available at each bar's close. It must not peek ahead and
must not apply costs or execution delay — the engine owns those.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

_REGISTRY: dict[str, "Strategy"] = {}


class Strategy:
    #: registry key, set by @register
    name: str = "unnamed"

    def positions(self, df: pd.DataFrame) -> pd.Series:
        """Return desired positions in {-1,0,+1}, indexed like ``df``.

        ``desired[t]`` is the position wanted as of the close of bar t, from data
        up to and including bar t only.
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Strategy {self.name}>"


def register(name: str) -> Callable[[type], type]:
    def deco(cls: type) -> type:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def get(name: str) -> type:
    if name not in _REGISTRY:
        raise KeyError(f"unknown strategy {name!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def all_strategies() -> list[str]:
    return sorted(_REGISTRY)
