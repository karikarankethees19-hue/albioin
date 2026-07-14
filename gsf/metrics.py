"""Performance metrics computed from a BacktestResult.

All metrics are honest and benchmark-relative:
    total_return, cagr, win_rate, profit_factor, max_drawdown, trades,
    plus the buy-and-hold equivalents for side-by-side comparison.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import BacktestResult


def _cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    total = equity.iloc[-1] / equity.iloc[0] - 1.0
    days = (equity.index[-1] - equity.index[0]).days
    if days <= 0:
        return 0.0
    return (1.0 + total) ** (365.0 / days) - 1.0


def _max_drawdown(equity: pd.Series) -> float:
    if len(equity) == 0:
        return 0.0
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def summarize(res: BacktestResult, label: str = "") -> dict:
    eq, bh, tr = res.equity, res.bh_equity, res.trades

    total = float(eq.iloc[-1] - 1.0) if len(eq) else 0.0
    bh_total = float(bh.iloc[-1] - 1.0) if len(bh) else 0.0

    n_trades = int(len(tr))
    wins = tr[tr["net_ret"] > 0]["net_ret"] if n_trades else pd.Series(dtype=float)
    losses = tr[tr["net_ret"] < 0]["net_ret"] if n_trades else pd.Series(dtype=float)
    win_rate = float(len(wins) / n_trades) if n_trades else 0.0
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else np.inf

    return {
        "label": label,
        "execution": res.meta.get("execution"),
        "start": res.meta.get("start"),
        "end": res.meta.get("end"),
        "total_return": total,
        "cagr": _cagr(eq),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": _max_drawdown(eq),
        "trades": n_trades,
        "bh_total_return": bh_total,
        "bh_cagr": _cagr(bh),
        "bh_max_drawdown": _max_drawdown(bh),
    }


def autopsy(res: BacktestResult, label: str = "") -> dict:
    """Fee-shredder autopsy: how much of the gross edge do costs eat, and how
    hard does the strategy churn? This is the intraday-specific diagnosis.
    """
    eq, geq = res.equity, res.gross_equity
    net_total = float(eq.iloc[-1] - 1.0) if len(eq) else 0.0
    gross_total = float(geq.iloc[-1] - 1.0) if (geq is not None and len(geq)) else net_total

    # Cost drag in equity terms = gross final - net final (both start at 1.0).
    cost_drag = float((geq.iloc[-1] - eq.iloc[-1])) if geq is not None and len(geq) else 0.0
    # Share of the *gross* profit surrendered to fees (only meaningful if gross>0).
    if gross_total > 1e-9:
        cost_share_of_gross = cost_drag / (geq.iloc[-1] - 1.0)
    else:
        cost_share_of_gross = float("nan")

    n_trades = int(len(res.trades))
    span_days = max((eq.index[-1] - eq.index[0]).days, 1) if len(eq) else 1
    trades_per_day = n_trades / span_days

    # Average holding period from trade entry/exit timestamps.
    if n_trades:
        holds = (res.trades["exit_time"] - res.trades["entry_time"]).dt.total_seconds()
        avg_hold_hours = float(holds.mean() / 3600.0)
    else:
        avg_hold_hours = float("nan")

    return {
        "label": label,
        "gross_return": gross_total,
        "net_return": net_total,
        "cost_drag": cost_drag,
        "cost_share_of_gross": cost_share_of_gross,
        "trades": n_trades,
        "trades_per_day": trades_per_day,
        "avg_hold_hours": avg_hold_hours,
    }


def format_autopsy(rows: list[dict]) -> str:
    head = (
        f"{'strategy / tier':<40}  {'gross':>8}  {'net':>8}  "
        f"{'fees ate':>9}  {'trades':>7}  {'trd/day':>8}  {'hold(h)':>8}"
    )
    lines = [head, "-" * len(head)]
    for r in rows:
        share = r["cost_share_of_gross"]
        share_s = "n/a" if share != share else f"{share * 100:.0f}%"  # nan check
        hold = r["avg_hold_hours"]
        hold_s = "n/a" if hold != hold else f"{hold:.1f}"
        lines.append(
            f"{r['label']:<40}  {r['gross_return']*100:>+7.1f}%  {r['net_return']*100:>+7.1f}%  "
            f"{share_s:>9}  {r['trades']:>7}  {r['trades_per_day']:>8.2f}  {hold_s:>8}"
        )
    return "\n".join(lines)


def format_table(rows: list[dict]) -> str:
    """Render summary dicts as a fixed-width comparison table."""
    cols = [
        ("label", "strategy", 34, "s"),
        ("execution", "exec", 13, "s"),
        ("total_return", "return", 9, "pct"),
        ("cagr", "CAGR", 8, "pct"),
        ("win_rate", "win%", 6, "pct"),
        ("profit_factor", "PF", 6, "f2"),
        ("max_drawdown", "maxDD", 8, "pct"),
        ("trades", "trades", 7, "d"),
        ("bh_total_return", "B&H ret", 9, "pct"),
        ("bh_max_drawdown", "B&H DD", 8, "pct"),
    ]

    def fmt(v, kind):
        if kind == "pct":
            return f"{v * 100:+.2f}%"
        if kind == "f2":
            return "inf" if v == np.inf else f"{v:.2f}"
        if kind == "d":
            return f"{v:d}"
        return str(v)

    head = "  ".join(f"{h:>{w}}" if k != "label" else f"{h:<{w}}" for k, h, w, _ in cols)
    lines = [head, "-" * len(head)]
    for r in rows:
        cells = []
        for k, _h, w, kind in cols:
            s = fmt(r.get(k, ""), kind) if r.get(k, "") != "" else ""
            cells.append(f"{s:<{w}}" if k == "label" else f"{s:>{w}}")
        lines.append("  ".join(cells))
    return "\n".join(lines)
