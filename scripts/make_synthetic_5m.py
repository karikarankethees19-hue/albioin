#!/usr/bin/env python3
"""Generate a synthetic 3-year 5-minute OHLCV series — PIPELINE TEST ONLY.

⚠️  This is NOT market data and carries NO predictive edge. It exists solely to
exercise the intraday harness end-to-end (VWAP session resets, ORB opening
range, rolling windows, fee autopsy) where the sandbox cannot fetch real 5m data.

It is a geometric random walk with realistic 5-minute volatility (~0.15%/bar, to
match the measured BTC bar range of ~$90 on ~$62.6k) and a daily (24/7) session
structure. Because a random walk has no edge BY CONSTRUCTION, any strategy run
on it should show gross return ≈ 0 and net return ≈ −(fees paid). That is the
whole point: it proves the accounting, and shows that on a no-edge series
intraday churn is a guaranteed loss equal to the cost. Real conclusions about
these strategies require REAL 5m data (see scripts/fetch_ccxt.py).

Usage:
  python scripts/make_synthetic_5m.py --symbol BTCUSD --years 3 --seed 7
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def generate(years: float, seed: int, start_price: float, sigma_bar: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    bars = int(years * 365 * 288)  # 288 five-minute bars per 24h day
    # log-returns: ~zero drift, sigma per bar. No edge by design.
    steps = rng.normal(loc=0.0, scale=sigma_bar, size=bars)
    close = start_price * np.exp(np.cumsum(steps))
    open_ = np.empty(bars)
    open_[0] = start_price
    open_[1:] = close[:-1]
    # intrabar high/low: extend beyond open/close by a fraction of bar vol
    wick = np.abs(rng.normal(0.0, sigma_bar * 0.6, size=bars)) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    # volume with a mild intraday sinusoidal profile + noise (all positive)
    tod = np.arange(bars) % 288
    profile = 1.0 + 0.5 * np.sin(2 * np.pi * tod / 288)
    volume = np.abs(rng.normal(profile, 0.3, size=bars)) * 100.0

    ts = pd.date_range("2023-01-01", periods=bars, freq="5min")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="SYNTH")
    ap.add_argument("--years", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start-price", type=float, default=62600.0)
    ap.add_argument("--sigma-bar", type=float, default=0.0015)
    args = ap.parse_args()

    df = generate(args.years, args.seed, args.start_price, args.sigma_bar)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{args.symbol}_5m.parquet"
    df.to_parquet(out, index=False)
    print(f"[SYNTHETIC — not market data] wrote {len(df)} bars to {out}")
    print(f"  {df.timestamp.min()} -> {df.timestamp.max()}")


if __name__ == "__main__":
    main()
