#!/usr/bin/env python3
"""Convert a saved Alpha Vantage MCP tool result into a canonical parquet cache.

This is the sandbox data path. Alpha Vantage MCP tools (DIGITAL_CURRENCY_DAILY,
FX_DAILY) route through the app's MCP channel and so bypass the sandbox's HTTP
403 wall. Their large results get offloaded to a JSON file on disk; point this
script at that file to normalise it into data/cache/{KEY}.parquet.

The JSON is either {"result": "<csv>"} (full) or a preview object carrying the
data under "sample_data" with a "headers" line. Both are handled.

Usage:
  python scripts/mcp_to_cache.py <saved_json> --key BTCUSD_1d
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _extract_csv(obj: dict) -> str:
    if "result" in obj and obj["result"]:
        return obj["result"]
    if "sample_data" in obj:  # preview payload
        return obj["sample_data"]
    raise ValueError("no CSV found under 'result' or 'sample_data'")


def normalise(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text))
    df = df.rename(columns=str.lower)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c])
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    return (
        df[["timestamp", "open", "high", "low", "close", "volume"]]
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("--key", required=True, help="cache key, e.g. BTCUSD_1d")
    args = ap.parse_args()

    obj = json.load(open(args.json_file))
    df = normalise(_extract_csv(obj))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{args.key}.parquet"
    df.to_parquet(out, index=False)
    print(f"wrote {len(df)} rows to {out}  ({df.timestamp.min().date()} -> {df.timestamp.max().date()})")


if __name__ == "__main__":
    main()
