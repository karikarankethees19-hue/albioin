# Guru Strategy Falsification Harness

Code viral trading-Reel strategies **exactly as sold**, backtest them honestly
(real costs, no look-ahead, no overfitting), and benchmark every one against
buy-and-hold. If a "just follow these 3 rules" strategy loses money — or merely
fails to beat holding — under honest conditions, the guru was selling vibes.

> Core thesis: if it's codeable, it's testable. A bot also removes the
> psychology excuse — it never quits during drawdown.

---

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Reproduce Test 1 + cross-check EMA 9/21 on BTC/ETH (uses the committed cache):
python run.py --suite

# One-off run:
python run.py --strategy ema_cross --symbol BTCUSD --asset crypto --taker 0.001 --plot
python run.py --strategy rsi --symbol ETHUSD --asset crypto --taker 0.001

# Tests (no-look-ahead + cost accounting):
python -m pytest -q
```

The daily parquet cache is committed, so the harness runs **offline** with no
data fetch required.

---

## Honest-backtest guarantees

| Rule | How the engine enforces it |
|---|---|
| No look-ahead | A strategy returns a `desired` position known only at bar *t*'s close; the engine holds `desired.shift(1)` — you can never act on a bar before its signal exists. |
| No repainting | Indicators (EMA, Wilder RSI) use `adjust=False` / causal smoothing — past+current bars only. |
| Real costs | Charged **per side** on every unit of turnover: enter = 1 side, exit = 1 side, flip = 2. Whipsaw is punished by construction. Crypto taker %/side; FX pips/round-trip. |
| Execution honesty | `next_open` (v2, preferred): signal at close *t-1* → fill at open *t*. `close_to_close` (v1): signal executes at the same close that formed it. |
| Always benchmarked | Every run reports buy-and-hold return + max drawdown on the identical window. |

Metrics logged: total return, CAGR, win rate, profit factor, max drawdown,
trade count, vs buy-and-hold.

---

## Data — and a hard sandbox constraint

**The engine is source-agnostic**: it only ever reads canonical OHLCV parquet
from `data/cache/`. Whatever fills the cache is irrelevant to the backtest.

There are two populators, because **this repo was built inside Claude Code on
the web, whose network policy blocks all market-data hosts** (Binance, Kraken,
Coinbase, KuCoin, Yahoo, Alpha Vantage's REST API — every one returns HTTP 403;
only package registries are allowlisted). The handoff's assumption that
`ccxt` gives "free unlimited OHLCV in Claude Code" **does not hold in the web
sandbox** — ccxt installs fine but cannot reach any exchange from there.

| Populator | Where it works | What it can fetch |
|---|---|---|
| `scripts/mcp_to_cache.py` | the sandbox | **daily** FX + crypto, free, via the Alpha Vantage MCP channel (bypasses the HTTP block) |
| `scripts/fetch_ccxt.py` | any **open-network** machine (e.g. Karikaran's Windows box) | **any timeframe**, incl. 5-minute crypto |

### Free-data reality check (measured this session)

| Need | Path | Status in sandbox |
|---|---|---|
| FX daily (EURUSD) | AV `FX_DAILY` | ✅ free |
| Crypto daily (BTC/ETH) | AV `DIGITAL_CURRENCY_DAILY` | ✅ free |
| Crypto 5-minute | AV `CRYPTO_INTRADAY` | ❌ premium (paywalled, same as FX_INTRADAY) |
| Any exchange via ccxt | network | ❌ 403 blocked |

**Consequence:** the intraday 5-minute fee-shredder test (hit-list item for EMA
and the whole point of VWAP/ORB) **cannot be run from the sandbox.** Run
`scripts/fetch_ccxt.py --timeframe 5m` locally, then `python run.py` unchanged.

Committed cache: `BTCUSD_1d` (2010→), `ETHUSD_1d` (2015→), `EURUSD_1d`
(2020-12→, covers Test 1's window with warmup).

---

## Results

### Engine validation — reproduces Test 1 (EURUSD daily, close-to-close, 1.5 pip)

| metric | reproduced | handoff | note |
|---|---|---|---|
| buy & hold return / DD | **+1.40% / −8.82%** | +1.40% / −8.82% | exact |
| long-only max drawdown | **−4.34%** | −4.33% | matches to a basis point |
| long/short max drawdown | **−6.06%** | −6.06% | exact |
| long-only return | +5.28% | +4.38% | within ~1% |
| long-only trades | 13 | 14 | see conventions below |

The exact B&H match and basis-point DD match confirm the data, window, and
equity accounting. Small residuals in return/trade-count/PF come from two
**documented convention differences**, not bugs:
1. **EMA warmup**: this engine seeds EMAs from 2020; the original had only ~856
   rows warming from Apr 2023. Different seeds flip a crossover or two early in
   a 13-trade sample.
2. **Open trade at window end**: a position still open on the last bar is
   marked-to-market in the equity curve but **not** counted as a closed trade
   (so its P&L is in the return but not in win-rate/PF). That alone explains the
   off-by-one trade count.

### Cross-check — EMA 9/21 on BTC/ETH daily, next-open fills, honest fees, 2023-07-13 → 2026-07-13

| asset · side · fees | return | CAGR | maxDD | trades | B&H ret | B&H DD |
|---|--:|--:|--:|--:|--:|--:|
| BTC long-only · retail 0.10%/side | +161% | +36% | −27% | 22 | +110% | −53% |
| BTC long-only · VIP 0.04%/side | +169% | +37% | −27% | 22 | +110% | −53% |
| BTC long/short · retail | +140% | +32% | −45% | 45 | +110% | −53% |
| ETH long-only · retail | +53% | +13% | −52% | 21 | −4% | −68% |
| ETH long-only · VIP | +57% | +14% | −52% | 21 | −4% | −68% |
| ETH long/short · retail | +18% | +4% | −77% | 43 | −4% | −68% |

**Reading it honestly:**
- **On daily bars, fees are not the killer.** Retail (0.10%/side) vs VIP
  (0.04%/side) differ by only ~5–8% of total return. This *confirms* the
  handoff's daily-timeframe finding on crypto too. The fee-shredder thesis is
  specifically an **intraday** phenomenon (5-min pays 20–50%) — still untested
  here because the sandbox can't get 5-min data.
- **Long-only beat buy-and-hold with roughly half the drawdown** on both assets
  in this window — but the window (2023–2026) was a crypto bull market, exactly
  the regime that flatters trend-following. Single window, single regime: treat
  the outperformance as regime-dependent, not proven edge.
- **Shorting hurt.** Long/short underperformed long-only everywhere (fading an
  uptrend), with far deeper drawdowns.
- Sub-50% win rates with PF > 1 = classic trend-following: a few big rides carry
  it. A human watching −27% to −52% drawdowns mid-ride is the real failure mode,
  not the math.

Equity curves in `reports/`.

### Regime dependence — per-year windows (`python analysis.py`)

The single multi-year headline above is *misleading*, and the per-year
breakdown proves it. Same strategy, same fees, one calendar year at a time
(excess = strategy − buy-and-hold, next-open fills, retail fees):

**EMA 9/21 on BTC — "beats buy-and-hold" is really "avoids crashes":**

| year | strat | buy&hold | excess |
|---|--:|--:|--:|
| 2021 (bull) | +128% | +63% | **+65%** |
| 2022 (bear) | −53% | −64% | +11% |
| 2023 (bull) | +100% | +155% | **−55%** |
| 2024 (bull) | +83% | +119% | **−36%** |
| 2026 (down) | −1% | −29% | +28% |

EMA *lagged* buy-and-hold in the strong bull years (2023, 2024) and only "won"
by losing less in down/sideways years (2022, 2026). Its edge is **downside
protection, not trend capture** — insurance, not alpha. Beat B&H in 6/8 years
but median excess only +7.4%, and the crypto "outperformance" cited earlier was
an artefact of *which* years the 3-year window happened to span.

**RSI 30/70 — destroyed, exactly as predicted:** beat buy-and-hold in **2/8
years on BTC (median excess −82%)** and 2/8 on ETH (−22%). It trades once or
twice a year and sits out entire bull runs (2020: +123% vs B&H +301%, a −178pp
miss). The mean-reversion meat grinder, confirmed.

**Supertrend:** mediocre and regime-dependent — 3/8 years on BTC (median −18%),
5/8 on ETH (+12.5%), carried by single outliers (ETH 2021 +139pp).

**FX (EURUSD):** all three beat a flat/declining buy-and-hold in most years, but
absolute returns are trivial (a few %/year) — a GIC still wins. Consistent with
Test 1.

See `reports/regime_heatmap.png` for the full grid.

---

## Adding a strategy (~10 lines)

```python
# gsf/strategies/supertrend.py
from .base import Strategy, register
import pandas as pd

@register("supertrend")
class Supertrend(Strategy):
    def positions(self, df: pd.DataFrame) -> pd.Series:
        # return a Series in {-1, 0, +1}, using only data up to each bar's close
        ...
```

Import it in `gsf/strategies/__init__.py` and it's runnable via
`--strategy supertrend`.

Currently implemented:

| strategy | timeframe | notes |
|---|---|---|
| `ema_cross` | any | 9/21 EMA crossover, long-only or long/short |
| `rsi` | any | Wilder RSI, buy < 30 / sell > 70, stateful hold between bands |
| `supertrend` | any | ATR-banded (10/3), causal band carry-forward |
| `vwap_bounce` | **intraday only** | long while above session VWAP; needs sub-daily bars |
| `orb` | **intraday only** | first-15-min opening-range breakout, flat overnight |

`vwap_bounce` and `orb` are session-aware and raise on daily data — populate a
5-minute cache with `scripts/fetch_ccxt.py` (locally, open network) and they run
unchanged.

---

## Layout

```
gsf/
  data.py         # cache loader (source-agnostic)
  costs.py        # CryptoCost (%/side), FxCost (pips/round-trip)
  engine.py       # vectorized, look-ahead-free backtest + trade extraction
  metrics.py      # return, CAGR, win rate, PF, max DD, comparison table
  report.py       # equity-curve PNGs
  windows.py      # per-year / rolling regime analysis
  strategies/     # registry + ema_cross, rsi, supertrend, intraday (vwap, orb)
run.py            # CLI (single run, or --suite)
suite.py          # Test 1 reproduction + BTC/ETH cross-check
analysis.py       # per-year regime grid + heatmap
scripts/          # fetch_ccxt.py (local), mcp_to_cache.py (sandbox)
tests/            # no-look-ahead, cost-accounting, strategy + session tests
data/cache/       # committed daily parquet
reports/          # committed equity PNGs
```

## Next steps (from the project plan)

1. **5-minute EMA 9/21 on BTC** with fee tiers — run `fetch_ccxt.py --timeframe 5m`
   locally, then confirm/deny the fee-shredder prediction. *(blocked in sandbox)*
2. Run **`vwap_bounce` and `orb`** on that same local 5-min cache (modules ready;
   they raise on daily data by design).
3. ~~RSI 30/70~~ ✅ done on daily — destroyed on trending crypto (2/8 years).
4. ~~Supertrend~~ ✅ done on daily — mediocre, regime-dependent.
5. ~~Rolling multi-window regime analysis~~ ✅ done — see `analysis.py` / heatmap.
6. Paper-trade any survivor forward one month before touching the $100 CAD.
   (On the daily evidence so far, there is no survivor worth live capital: EMA's
   only edge is crash-avoidance, and it lags in bull years.)
