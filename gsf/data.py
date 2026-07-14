"""Data access layer.

The backtest engine is *source-agnostic*: it reads canonical OHLCV parquet
files from ``data/cache/`` and never talks to the network. Whatever populated
the cache (Alpha Vantage MCP, ccxt, yfinance, a manual CSV) is irrelevant to
the engine. See ``scripts/`` for the populators.

Canonical schema (one row per bar, ascending time):
    timestamp : datetime64  (UTC-naive, bar open time)
    open, high, low, close : float
    volume : float  (0.0 where a source has no meaningful volume, e.g. FX)

Cache filename convention: ``{SYMBOL}_{TIMEFRAME}.parquet`` e.g. ``BTCUSD_1d``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

CANONICAL_COLS = ["timestamp", "open", "high", "low", "close", "volume"]


def cache_path(symbol: str, timeframe: str) -> Path:
    return CACHE_DIR / f"{symbol}_{timeframe}.parquet"


def available() -> list[str]:
    """List cached ``SYMBOL_TIMEFRAME`` keys."""
    return sorted(p.stem for p in CACHE_DIR.glob("*.parquet"))


def load_ohlcv(
    symbol: str,
    timeframe: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load OHLCV from the local cache, optionally sliced to [start, end].

    Slicing is inclusive on both ends and operates on bar timestamps. Indicator
    warmup is the caller's responsibility: load the *full* series, compute
    indicators, then restrict the trading window (see engine.run's `start`/`end`).
    """
    path = cache_path(symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(
            f"No cached data for {symbol} {timeframe} at {path}.\n"
            f"Available: {available()}\n"
            f"Populate it via scripts/fetch_ccxt.py (open network) or the "
            f"Alpha Vantage MCP path documented in the README."
        )
    df = pd.read_parquet(path)
    missing = [c for c in CANONICAL_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} missing columns {missing}")
    df = df[CANONICAL_COLS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if start is not None:
        df = df[df["timestamp"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["timestamp"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)
