#!/usr/bin/env python3
"""Regime-dependence analysis: per-year windows across strategies and assets.

Runs EMA 9/21, RSI 30/70, and Supertrend on daily BTC/ETH/EURUSD, one calendar
year at a time, and prints per-year tables plus an excess-return heatmap. The
point is to see whether a strategy's edge is real or just a bull-market artefact.

    python analysis.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from gsf import windows  # noqa: E402
from gsf.report import REPORT_DIR  # noqa: E402

# (symbol, asset). Restrict to years with enough data per asset.
ASSETS = [("BTCUSD", "crypto"), ("ETHUSD", "crypto"), ("EURUSD", "fx")]
STRATS = ["ema_cross", "rsi", "supertrend"]
YEARS = range(2019, 2027)


def main() -> None:
    grids = {}  # (symbol, strat) -> per_year DataFrame
    for symbol, asset in ASSETS:
        print("\n" + "#" * 78)
        print(f"# {symbol}  ({asset})")
        print("#" * 78)
        for strat in STRATS:
            dfy = windows.per_year(symbol, strat, asset=asset, years=YEARS)
            grids[(symbol, strat)] = dfy
            print("\n" + windows.format_year_table(dfy, f"{strat}  ·  {symbol}  (excess = strat − buy&hold)"))

    _heatmap(grids)


def _heatmap(grids) -> None:
    """Excess-return heatmap: rows = (symbol, strategy), cols = years."""
    row_keys = [(sym, st) for sym, _ in ASSETS for st in STRATS]
    years = sorted({y for dfy in grids.values() for y in dfy.index})
    mat = np.full((len(row_keys), len(years)), np.nan)
    for i, key in enumerate(row_keys):
        dfy = grids[key]
        for j, y in enumerate(years):
            if y in dfy.index:
                mat[i, j] = dfy.loc[y, "excess"] * 100.0

    fig, ax = plt.subplots(figsize=(1.1 * len(years) + 3, 0.6 * len(row_keys) + 2))
    vmax = np.nanmax(np.abs(mat))
    im = ax.imshow(mat, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years)
    ax.set_yticks(range(len(row_keys)))
    ax.set_yticklabels([f"{s} · {st}" for s, st in row_keys])
    for i in range(len(row_keys)):
        for j in range(len(years)):
            if not np.isnan(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:+.0f}", ha="center", va="center", fontsize=8)
    ax.set_title("Excess return vs buy & hold, per year (%)  — green = strategy beat holding")
    fig.colorbar(im, ax=ax, label="excess return (pp)")
    fig.tight_layout()
    out = REPORT_DIR / "regime_heatmap.png"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\nHeatmap -> {out}")


if __name__ == "__main__":
    main()
