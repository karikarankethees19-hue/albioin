#!/usr/bin/env python3
"""Guru Strategy Falsification — CLI entry point.

Examples
--------
  # EMA 9/21 long-only on BTC daily, next-open fills, retail crypto fees:
  python run.py --strategy ema_cross --symbol BTCUSD --timeframe 1d \
      --asset crypto --taker 0.001

  # Long/short, VIP fees:
  python run.py --strategy ema_cross --symbol ETHUSD --allow-short \
      --asset crypto --taker 0.0004

  # Reproduce Test 1 (EURUSD daily, close-to-close, 1.5 pip round trip):
  python run.py --strategy ema_cross --symbol EURUSD --asset fx --pips 1.5 \
      --execution close_to_close --start 2023-07-13 --end 2026-07-13

Run the bundled validation + cross-check suite instead of a single config:
  python run.py --suite
"""
from __future__ import annotations

import argparse

from gsf import data, metrics, report, costs
from gsf import engine as eng
from gsf.strategies import get as get_strategy


def run_one(args) -> dict:
    df = data.load_ohlcv(args.symbol, args.timeframe)
    strat_cls = get_strategy(args.strategy)

    kwargs = {"allow_short": args.allow_short}
    if args.strategy == "ema_cross":
        kwargs.update(fast=args.fast, slow=args.slow)
    strat = strat_cls(**kwargs)

    desired = strat.positions(df)

    if args.asset == "crypto":
        cost = costs.CryptoCost(taker_per_side=args.taker, half_spread=args.half_spread)
    else:
        cost = costs.FxCost(pips_round_trip=args.pips, pip_size=args.pip_size)

    res = eng.run(
        df, desired, cost, execution=args.execution, start=args.start, end=args.end
    )
    side = "L/S" if args.allow_short else "long-only"
    label = f"{args.strategy} {args.symbol} {side}"
    summ = metrics.summarize(res, label=label)

    if args.plot:
        fn = f"{args.strategy}_{args.symbol}_{'ls' if args.allow_short else 'long'}.png"
        p = report.equity_png(res, label, fn)
        print(f"  equity curve -> {p}")
    return summ


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="ema_cross")
    ap.add_argument("--symbol", default="BTCUSD")
    ap.add_argument("--timeframe", default="1d")
    ap.add_argument("--execution", default="next_open", choices=list(eng.EXECUTIONS))
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--allow-short", action="store_true")
    ap.add_argument("--fast", type=int, default=9)
    ap.add_argument("--slow", type=int, default=21)
    # cost model
    ap.add_argument("--asset", default="crypto", choices=["crypto", "fx"])
    ap.add_argument("--taker", type=float, default=0.001, help="crypto taker per side")
    ap.add_argument("--half-spread", type=float, default=0.0)
    ap.add_argument("--pips", type=float, default=1.5, help="fx pips per round trip")
    ap.add_argument("--pip-size", type=float, default=1e-4)
    ap.add_argument("--plot", action="store_true")
    ap.add_argument("--suite", action="store_true", help="run validation + cross-check suite")
    args = ap.parse_args()

    if args.suite:
        from suite import run_suite

        run_suite()
        return

    summ = run_one(args)
    print(metrics.format_table([summ]))


if __name__ == "__main__":
    main()
