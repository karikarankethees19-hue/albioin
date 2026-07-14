#!/usr/bin/env python3
"""Populate the OHLCV cache from a crypto exchange via ccxt.

THIS DOES NOT RUN IN THE CLAUDE-CODE-ON-THE-WEB SANDBOX: that environment's
network policy returns HTTP 403 for every exchange host (Binance, Kraken,
Coinbase, KuCoin all blocked — only package registries are allowlisted). Run it
on an open-network machine (e.g. Karikaran's Windows box) to fetch data the
sandbox cannot — most importantly the 5-minute crypto series needed for the
intraday fee-shredder test, which has no free path inside the sandbox.

It paginates fetch_ohlcv to pull long histories and writes canonical parquet
files that the engine reads unchanged. Same cache format as the MCP daily path,
so results are directly comparable.

Examples
--------
  python scripts/fetch_ccxt.py --exchange kraken --symbol BTC/USD  --timeframe 1d  --since 2018-01-01
  python scripts/fetch_ccxt.py --exchange binance --symbol BTC/USDT --timeframe 5m  --since 2025-07-01
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _cache_key(symbol: str, timeframe: str) -> str:
    # BTC/USDT -> BTCUSD (drop the quote's trailing T so USDT->USD groups with
    # the AV daily cache); keep it simple and explicit.
    base, quote = symbol.split("/")
    quote = "USD" if quote in ("USDT", "USD", "USDC") else quote
    return f"{base}{quote}_{timeframe}"


def fetch(exchange_id: str, symbol: str, timeframe: str, since: str) -> pd.DataFrame:
    import ccxt  # imported lazily so the module loads even where ccxt is absent

    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    since_ms = ex.parse8601(f"{since}T00:00:00Z")
    all_rows: list[list] = []
    limit = 1000
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        if not batch:
            break
        all_rows += batch
        since_ms = batch[-1][0] + 1
        if len(batch) < limit:
            break
        time.sleep(ex.rateLimit / 1000.0)
    df = pd.DataFrame(all_rows, columns=["ms", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["ms"], unit="ms")
    return (
        df[["timestamp", "open", "high", "low", "close", "volume"]]
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exchange", default="kraken")
    ap.add_argument("--symbol", default="BTC/USD")
    ap.add_argument("--timeframe", default="1d")
    ap.add_argument("--since", default="2018-01-01")
    args = ap.parse_args()

    df = fetch(args.exchange, args.symbol, args.timeframe, args.since)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(args.symbol, args.timeframe)
    out = CACHE_DIR / f"{key}.parquet"
    df.to_parquet(out, index=False)
    print(f"wrote {len(df)} rows to {out}  ({df.timestamp.min().date()} -> {df.timestamp.max().date()})")


if __name__ == "__main__":
    main()
