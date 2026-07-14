#!/usr/bin/env python3
"""Intraday verification: fee-shredder autopsy + rolling 3-year windows on 5m data.

This is the test the daily analysis cannot substitute for. It runs every
strategy on a 5-minute cache, over rolling windows spanning the full history,
at several fee tiers, and reports:

  1. Fee autopsy   — gross vs net return, what % of the gross edge fees eat,
                     trade count, trades/day, average holding period.
  2. Rolling grid  — per-window excess vs buy-and-hold and cost-share, to expose
                     regime dependence (never trust one window).

Data: expects data/cache/{SYMBOL}_5m.parquet.
  * Real crypto:   python scripts/fetch_ccxt.py --exchange kraken --symbol BTC/USD --timeframe 5m --since 2022-01-01
  * Pipeline test: python scripts/make_synthetic_5m.py --symbol BTCUSD   (⚠ not market data)

  python analysis_intraday.py --symbol BTCUSD
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from gsf import data, metrics, windows  # noqa: E402
from gsf import engine as eng  # noqa: E402
from gsf.costs import CryptoCost  # noqa: E402
from gsf.report import REPORT_DIR  # noqa: E402
from gsf.strategies import get as get_strategy  # noqa: E402

# taker per side, half-spread per side
FEE_TIERS = [
    ("zero (gross ref)", 0.0, 0.0),
    ("VIP 0.04%/side", 0.0004, 0.0),
    ("retail 0.10%/side", 0.001, 0.0),
    ("retail+spread", 0.001, 0.0005),
]
STRATS = ["ema_cross", "rsi", "supertrend", "vwap_bounce", "orb"]


def _positions(name, df):
    return get_strategy(name)(allow_short=False).positions(df)


def fee_autopsy(symbol: str) -> None:
    df = data.load_ohlcv(symbol, "5m")
    print("=" * 100)
    print(f"FEE-SHREDDER AUTOPSY — {symbol} 5-minute, {df.timestamp.min().date()} → {df.timestamp.max().date()}, next-open fills")
    print("=" * 100)
    for strat in STRATS:
        try:
            desired = _positions(strat, df)
        except ValueError as e:
            print(f"\n[{strat}] skipped: {e}")
            continue
        rows = []
        for tier, taker, spread in FEE_TIERS:
            cost = CryptoCost(taker_per_side=taker, half_spread=spread)
            res = eng.run(df, desired, cost, execution="next_open")
            rows.append(metrics.autopsy(res, label=f"{strat} · {tier}"))
        print("\n" + metrics.format_autopsy(rows))


def rolling_grid(symbol: str, window_days: int, step_days: int) -> None:
    df = data.load_ohlcv(symbol, "5m")
    cost = CryptoCost(taker_per_side=0.001)  # retail
    print("\n" + "=" * 100)
    print(f"ROLLING {window_days}-DAY WINDOWS (step {step_days}d), retail 0.10%/side — {symbol} 5m")
    print("=" * 100)

    grid = {}  # strat -> DataFrame
    for strat in STRATS:
        try:
            desired = _positions(strat, df)
        except ValueError as e:
            print(f"\n[{strat}] skipped: {e}")
            continue
        r = windows.rolling(df, desired, cost, window_days=window_days, step_days=step_days)
        grid[strat] = r
        if len(r):
            beat = int((r["excess"] > 0).sum())
            print(
                f"\n{strat}: {len(r)} windows | beat B&H {beat}/{len(r)} | "
                f"median excess {r['excess'].median()*100:+.1f}% | "
                f"median fees-ate {np.nanmedian(r['cost_share_of_gross'])*100:.0f}% of gross | "
                f"median trades/day {r['trades_per_day'].median():.1f}"
            )
    _heatmap(symbol, grid, window_days)


def _heatmap(symbol, grid, window_days) -> None:
    strats = [s for s in STRATS if s in grid and len(grid[s])]
    if not strats:
        return
    n_win = max(len(grid[s]) for s in strats)
    mat = np.full((len(strats), n_win), np.nan)
    for i, s in enumerate(strats):
        vals = (grid[s]["excess"] * 100.0).to_numpy()
        mat[i, : len(vals)] = vals
    fig, ax = plt.subplots(figsize=(1.0 * n_win + 3, 0.6 * len(strats) + 2))
    vmax = np.nanmax(np.abs(mat)) or 1.0
    im = ax.imshow(mat, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_yticks(range(len(strats)))
    ax.set_yticklabels(strats)
    ax.set_xlabel(f"rolling {window_days}-day window # (chronological)")
    for i in range(len(strats)):
        for j in range(n_win):
            if not np.isnan(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:+.0f}", ha="center", va="center", fontsize=7)
    ax.set_title(f"{symbol} 5m — excess vs buy&hold per rolling window (%), retail fees")
    fig.colorbar(im, ax=ax, label="excess (pp)")
    fig.tight_layout()
    out = REPORT_DIR / f"intraday_rolling_{symbol}.png"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\nHeatmap -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSD")
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--step-days", type=int, default=90)
    args = ap.parse_args()
    fee_autopsy(args.symbol)
    rolling_grid(args.symbol, args.window_days, args.step_days)


if __name__ == "__main__":
    main()
