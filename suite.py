#!/usr/bin/env python3
"""Validation + cross-check suite.

1. Reproduce Test 1 (EURUSD daily, close-to-close, 1.5 pip round trip, exactly
   3 years) and print it next to the handoff's reported numbers. Matching trade
   count and direction validates the engine's no-look-ahead accounting.

2. Cross-check the EMA 9/21 finding on BTC and ETH daily with honest crypto
   fees (retail 0.10%/side and VIP 0.04%/side), next-open fills, same 3-yr
   window — to see whether the "works but barely beats risk-free" verdict from
   EURUSD generalises to crypto.
"""
from __future__ import annotations

from gsf import data, metrics, report, costs
from gsf import engine as eng
from gsf.strategies.ema_cross import EmaCross

WIN = ("2023-07-13", "2026-07-13")  # same 3-yr window as Test 1

# Handoff Test 1 reference numbers (EURUSD, close-to-close, 1.5 pip).
TEST1_REF = {
    "long-only": dict(total=0.0438, trades=14, win=0.429, pf=1.81, dd=-0.0433),
    "long/short": dict(total=0.0678, trades=28, win=0.464, pf=1.54, dd=-0.0606),
    "buy&hold": dict(total=0.0140, dd=-0.0882),
}


def _ema_run(symbol, allow_short, cost, execution):
    df = data.load_ohlcv(symbol, "1d")
    desired = EmaCross(9, 21, allow_short=allow_short).positions(df)
    return eng.run(df, desired, cost, execution=execution, start=WIN[0], end=WIN[1])


def validate_test1() -> list[dict]:
    print("=" * 92)
    print("PART 1 — Engine validation: reproduce Test 1 (EURUSD daily, close-to-close, 1.5 pip)")
    print("=" * 92)
    fx = costs.FxCost(pips_round_trip=1.5, pip_size=1e-4)
    rows = []
    for short, key in [(False, "long-only"), (True, "long/short")]:
        res = _ema_run("EURUSD", short, fx, "close_to_close")
        s = metrics.summarize(res, f"ema_cross EURUSD {key}")
        rows.append(s)
        ref = TEST1_REF[key]
        print(f"\n[{key}]  reproduced vs handoff:")
        print(f"    total return : {s['total_return']*100:+6.2f}%   (handoff {ref['total']*100:+.2f}%)")
        print(f"    trades       : {s['trades']:6d}     (handoff {ref['trades']})")
        print(f"    win rate     : {s['win_rate']*100:6.1f}%    (handoff {ref['win']*100:.1f}%)")
        pf = "inf" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
        print(f"    profit factor: {pf:>6}     (handoff {ref['pf']})")
        print(f"    max drawdown : {s['max_drawdown']*100:+6.2f}%   (handoff {ref['dd']*100:+.2f}%)")
    bh = rows[0]
    print(f"\n[buy&hold]  return {bh['bh_total_return']*100:+.2f}% (handoff {TEST1_REF['buy&hold']['total']*100:+.2f}%)"
          f"  |  maxDD {bh['bh_max_drawdown']*100:+.2f}% (handoff {TEST1_REF['buy&hold']['dd']*100:+.2f}%)")
    report.equity_png(_ema_run("EURUSD", False, costs.FxCost(1.5, 1e-4), "close_to_close"),
                      "EMA 9/21 EURUSD long-only (Test 1 repro)", "test1_eurusd_longonly.png")
    return rows


def crosscheck_crypto() -> list[dict]:
    print("\n" + "=" * 92)
    print("PART 2 — Cross-check on BTC / ETH daily, EMA 9/21, next-open fills, honest crypto fees")
    print("=" * 92)
    rows = []
    fee_tiers = [("retail 0.10%/side", 0.001), ("VIP 0.04%/side", 0.0004)]
    for symbol in ["BTCUSD", "ETHUSD"]:
        for tier_name, taker in fee_tiers:
            cost = costs.CryptoCost(taker_per_side=taker)
            for short in [False, True]:
                res = _ema_run(symbol, short, cost, "next_open")
                side = "L/S" if short else "long-only"
                s = metrics.summarize(res, f"{symbol} {side} [{tier_name}]")
                rows.append(s)
        # one representative equity curve per symbol (long-only, retail)
        rep = _ema_run(symbol, False, costs.CryptoCost(0.001), "next_open")
        report.equity_png(rep, f"EMA 9/21 {symbol} long-only (retail fees)",
                          f"ema_{symbol}_longonly.png")
    print("\n" + metrics.format_table(rows))
    return rows


def run_suite() -> None:
    t1 = validate_test1()
    cx = crosscheck_crypto()
    print("\n" + "=" * 92)
    print("SUMMARY TABLE (all runs)")
    print("=" * 92)
    print(metrics.format_table(t1 + cx))
    print("\nEquity curves written to reports/.")


if __name__ == "__main__":
    run_suite()
