"""Reporting: equity-curve PNGs and a comparison table.

Matplotlib is imported with the non-interactive Agg backend so this runs
headless in the sandbox.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .engine import BacktestResult  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def equity_png(res: BacktestResult, title: str, filename: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / filename
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(res.equity.index, res.equity.values, label="strategy", lw=1.6)
    ax.plot(
        res.bh_equity.index,
        res.bh_equity.values,
        label="buy & hold",
        lw=1.2,
        alpha=0.8,
    )
    ax.axhline(1.0, color="grey", lw=0.6, ls="--")
    ax.set_title(title)
    ax.set_ylabel("equity (start = 1.0)")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
