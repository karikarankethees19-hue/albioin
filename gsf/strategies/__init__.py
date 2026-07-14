"""Strategy registry.

Adding a new Reel strategy is ~10 lines: subclass Strategy, implement
``positions``, and decorate with ``@register("name")``. See ema_cross.py.
"""
from __future__ import annotations

from .base import Strategy, register, get, all_strategies

# Import modules so their @register decorators run.
from . import ema_cross  # noqa: F401
from . import rsi  # noqa: F401

__all__ = ["Strategy", "register", "get", "all_strategies"]
