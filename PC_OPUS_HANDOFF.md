# Handoff to Opus session running on V's PC

**Audience**: Opus 4.7 (or Sonnet 4.6) Claude Code session on V's RTX 5080 PC.
**Author**: Opus 4.7 session on V's laptop (the one V has been working with all week).
**Date**: 2026-06-16 ~9:30pm PT.
**Purpose**: bootstrap PC Opus with the EXACT state of validation work, what just broke, what to debug, and what's expected over the next 3-7 days. Don't re-discover, just execute.

If you're the PC Opus session reading this for the first time — **read `/Users/V/Projects/Options/SESSION_CONTEXT.md` first** for the bigger picture. This doc is the tactical now.

---

## Where we are right now

V started overnight backtest jobs ~6pm PT. ~3-4 hours later the jobs finished. **Both result files contain ZERO trades and an empty metrics dict.** This is *not* a verdict. It's a bug indicator.

Files V has:
- `pc/vrp_2018_2024_train.json` → `{"leg":"train", "window":"2018-01-01 to 2024-12-31", "universe_size":40, "metrics":{"num_trades":0}, "num_trades":0}`
- `pc/vrp_2025_2026_walkforward.json` → same shape, num_trades=0

The previous Haiku session interpreted this as **"signal failed DSR gate"**. That is wrong. **Real VRP harvest fires constantly on SPY/QQQ/AAPL — should produce 50-200+ trades per name across 8.5 years.** Zero trades on 40 mega-caps over 8.5 years means the harness didn't actually run the signal logic against real data.

V is frustrated. Don't be Haiku. **Diagnose first, conclude second.**

---

## The most likely root causes (ranked)

### #1 — MarketData historical chains returned empty for older dates

The Phase 5 smoke test in `OVERNIGHT_RUNBOOK.md` queried `SPY 2024-06-21 as_of=2024-05-01`. That's recent. The backtest queries dates from 2018-2024. **The Starter $30/mo tier may or may not cover full historical depth** — MarketData docs are unclear.

When `get_options_chain(as_of=2018-05-01)` returns 204 or 401:
1. `MarketDataHistoricalSource._load_chain` catches the exception silently (`logger.debug`)
2. Caches `None` so next read is also `None`
3. `_structure_exec_value` returns `None` because every leg quote is `None`
4. `simulate_trade` returns `None`
5. After all trades return `None`, `run_backtest` hits the "if not results" branch and writes `{"num_trades": 0}`

This explains the symptom perfectly.

### #2 — `trading_days()` calendar lookup is failing

`MarketDataHistoricalSource.trading_days` calls `self.client.get_history(SPY, ...)`. If MarketData's stock-candle endpoint isn't exposed to Starter tier (different from options), this returns `[]`. Then `simulate_trade` aborts at line `if not days: return None`.

### #3 — Strike rounding mismatch

`vrp_harvest._strangle_strikes(spot, 0.16)` returns `round(spot * (1 - 1.05*0.16), 0)` = nearest dollar. Real SPY chains in 2018 had only $5 strike increments. If we ask for strike 257.0 and the chain only has 255 and 260, the contract_key lookup returns None.

### #4 — Friday-rounding for non-existent expiry

`_next_45_dte_expiry(d)` always returns a Friday. In 2018 not every Friday was a SPY expiry (some monthlies only). The fetched chain at that expiry would be empty.

### #5 — Per-symbol exception not surfaced

`run_vrp_backtest` iterates symbols and accumulates trades. If yfinance returned nothing for "QQQ" (rare but possible during a rate limit), no error logs, just 0 trades for that name. Across 40 names with one or two failing, still expect SOME trades.

---

## Diagnostic protocol — run in this order, paste output back to V

Each command is self-contained. Run from `/Users/V/Projects/Options/backend/`.

### D1 — Surface the silent errors

```bash
echo "=== LEG 1 log full ==="
cat data/backtest_reports/vrp_leg1_train.log

echo
echo "=== LEG 2 log full ==="
cat data/backtest_reports/vrp_leg2_walkforward.log

echo
echo "=== Phase 6.5 jobs (the 'dependency issues' the previous session mentioned) ==="
for log in cross_section insider lead_lag squeeze climate; do
  echo "--- ${log} ---"
  tail -20 data/backtest_reports/${log}.log 2>/dev/null || echo "(no log)"
done
```

**Expected info you'll see**:
- Any tenacity retry errors against MarketData
- "trading_days SPY fetch failed" lines from the source
- "MarketData historical chain fetch failed" lines
- ImportError or AttributeError in the free signal jobs

### D2 — Did the cache fill?

```bash
echo "Cache size: $(du -sh data/marketdata_cache 2>/dev/null)"
echo "Cache file count: $(find data/marketdata_cache -name '*.parquet' 2>/dev/null | wc -l)"
echo
echo "Per-symbol counts:"
find data/marketdata_cache -mindepth 1 -maxdepth 1 -type d 2>/dev/null | while read d; do
  count=$(find "$d" -name "*.parquet" | wc -l)
  echo "  $(basename $d): $count files"
done | head -20
```

**Interpretation**:
- Cache empty / few files → MarketData never returned successful chains → **root cause is data access, not signal logic**
- Cache populated (thousands of files) but 0 trades → signal logic / strike-matching bug

### D3 — Test the source layer directly on the OLDEST date the backtest tries

```bash
python3 -c "
import asyncio
from datetime import date
from backtest.marketdata_source import MarketDataHistoricalSource
from backtest.engine import Leg

async def go():
    source = MarketDataHistoricalSource()

    # Test 1: trading_days — does the calendar work?
    days = await source.trading_days('SPY', date(2018, 1, 1), date(2018, 3, 31))
    print(f'TRADING DAYS Q1 2018: {len(days)} (expected ~62)')

    # Test 2: fetch a chain that backtest would actually need
    # Strangle entry on 2018-02-01, expiry ~45 DTE = mid-March 2018
    test_leg = Leg(right='C', strike=275.0, expiry=date(2018, 3, 16), qty=-1)
    quote = await source.eod_quote('SPY', test_leg, date(2018, 2, 1))
    print(f'SPY 275C exp 2018-03-16 on 2018-02-01: {quote}')

    test_leg2 = Leg(right='P', strike=255.0, expiry=date(2018, 3, 16), qty=-1)
    quote2 = await source.eod_quote('SPY', test_leg2, date(2018, 2, 1))
    print(f'SPY 255P exp 2018-03-16 on 2018-02-01: {quote2}')

    # Test 3: did the strikes exist?
    cache_key = ('SPY', date(2018, 3, 16), date(2018, 2, 1))
    cached = source._chain_cache.get(cache_key)
    if cached is None:
        print('Chain cache is None — MarketData returned empty/error')
    else:
        strikes = sorted(set(k[0] for k in cached.keys()))
        print(f'Available strikes for SPY exp 2018-03-16: {len(strikes)} total')
        print(f'  range: {min(strikes)}-{max(strikes)}')
        print(f'  near 265: {[s for s in strikes if 250 <= s <= 285]}')

    print(f'API fetches: {source.stats[\"api_fetches\"]}')
    print(f'Disk hits: {source.stats[\"disk_hits\"]}')

asyncio.run(go())
"
```

**Interpretation matrix**:

| Result | Diagnosis |
|---|---|
| `TRADING DAYS Q1 2018: 0` | Stock history endpoint doesn't work — could be Starter-tier limitation or yfinance fallback needed |
| `TRADING DAYS Q1 2018: ~62` but `SPY 275C... None` | Calendar OK, chain fetch failing — check log for HTTP status |
| Both work but `Chain cache is None` | API returned 204 = no historical depth for that date — **need to escalate to V, may need to subscribe to Trader tier OR backtest a shorter window starting from year MarketData covers** |
| Cache populated but exact strikes don't include 275/255 | Strike rounding mismatch — easy fix |

### D4 — Verify VRP signal logic on yfinance only (no MarketData)

If the signal logic itself is broken, no source fix will help. This isolates it:

```bash
python3 -c "
from datetime import date
from backtest.strategies.vrp_harvest import (
    generate_vrp_trades, _rolling_hv_rank, _vrp_z_series, VrpConfig,
)
from data.market import get_ohlcv_yfinance

df = get_ohlcv_yfinance('SPY', period='10y')
if df is None or df.empty:
    print('yfinance failed to return SPY history')
    raise SystemExit(1)

closes = df['close']
print(f'SPY history: {len(closes)} bars, {closes.index[0].date()} to {closes.index[-1].date()}')

iv_rank = _rolling_hv_rank(closes)
vrp_z = _vrp_z_series(closes)

# March 2020 (COVID): MUST be screaming high
mar2020 = (iv_rank.index >= '2020-03-01') & (iv_rank.index <= '2020-03-31')
print(f'HV-rank Mar 2020: max={float(iv_rank[mar2020].max()):.1f} (expect ~95-100)')
print(f'VRP-z   Mar 2020: max={float(vrp_z[mar2020].max()):.2f} (expect >3)')

trades = generate_vrp_trades('SPY', closes.loc['2018-01-01':'2024-12-31'])
print(f'SPY trades 2018-2024: {len(trades)}')
if trades:
    print(f'  first entry: {trades[0].entry_date}')
    print(f'  last entry: {trades[-1].entry_date}')
    print(f'  example legs: {trades[0].legs}')
"
```

**Interpretation**:
- If `SPY trades 2018-2024: 0` → signal-generation code is buggy. Likely the entry gate (`iv_rank > 50 AND vrp_z > +1`) never fires because `_vrp_z_series` is mis-computed. Check the rolling window indexing.
- If trades count is reasonable (50-200) → signal logic is fine, problem is downstream in execution / source / engine wiring.

### D5 — End-to-end mini run with synthetic source (proves engine plumbing)

If D4 shows trades but D3 shows source failures, run the full engine against the synthetic source to prove engine works:

```bash
python3 -c "
import asyncio
from datetime import date
from backtest.strategies.vrp_harvest import run_vrp_backtest
from backtest.synthetic_source import BlackScholesOptionsSource
from data.market import get_multi_ohlcv_yfinance

async def go():
    prices = get_multi_ohlcv_yfinance(['SPY', 'QQQ'], period='8y')
    spot_history = {s: df['close'] for s, df in prices.items() if df is not None and not df.empty}
    if not spot_history:
        print('NO YFINANCE DATA — STOP'); return
    source = BlackScholesOptionsSource(spot_history=spot_history)
    report = await run_vrp_backtest(
        symbols=['SPY', 'QQQ'], source=source,
        start=date(2018, 1, 1), end=date(2024, 12, 31),
    )
    print(f'Trades: {len(report.results)}')
    print(f'Metrics: {report.metrics}')

asyncio.run(go())
"
```

**Interpretation**:
- Trades > 0 → engine works end-to-end → real problem IS the MarketData source on historical dates
- Trades = 0 → engine wiring is broken, not the source. Trace `simulate_trade` for one failing trade.

---

## What you (PC Opus) can fix without escalation

If diagnostics show:

1. **Strike rounding mismatch (D3)** — fix `_strangle_strikes` to snap to actual chain strikes:
   ```python
   # In vrp_harvest.py — replace _strangle_strikes with:
   def _strangle_strikes(spot, target_delta, available_strikes=None):
       if available_strikes:
           put_target = spot * (1 - 1.05 * target_delta)
           call_target = spot * (1 + 1.05 * target_delta)
           put = min(available_strikes, key=lambda s: abs(s - put_target))
           call = min(available_strikes, key=lambda s: abs(s - call_target))
           return put, call
       # Fall back to dollar rounding if we don't have the chain yet
       return round(spot*(1-1.05*target_delta)), round(spot*(1+1.05*target_delta))
   ```
   Then `simulate_trade` fetches the chain at entry, gets available strikes, picks closest.

2. **Friday-rounding for non-existent expiries** — change `_next_45_dte_expiry` to find the nearest existing expiry in the available chain rather than always rounding to Friday:
   ```python
   # Use 3rd-Friday-of-month as the historical safe expiry (monthlies always existed)
   def _next_45_dte_expiry(d):
       # Third Friday of the month closest to d+45 days
       target = d + timedelta(days=45)
       first = target.replace(day=1)
       offset = (4 - first.weekday()) % 7
       return first + timedelta(days=offset + 14)  # 3rd Friday
   ```

3. **Engine error swallowing** — if D3 shows the chain fetch is silently catching errors, change `marketdata_source._load_chain`'s `logger.debug(...)` to `logger.warning(...)` so errors surface in the backtest log.

4. **yfinance fallback for trading_days** — if D3 shows `trading_days() returns []`, add a yfinance fallback:
   ```python
   # In MarketDataHistoricalSource.trading_days, after the existing logic:
   if not self._calendar_cache.get(self.calendar_symbol):
       from data.market import get_ohlcv_yfinance
       df = get_ohlcv_yfinance(self.calendar_symbol, period='10y')
       if df is not None and not df.empty:
           self._calendar_cache[self.calendar_symbol] = sorted(df.index.date.tolist())
   ```

## What requires escalating to V

If diagnostics show:

- **MarketData Starter tier doesn't have 2018-2020 historical depth**. → V needs to either:
  - Upgrade to Trader tier $30/mo annual (5-10x more credits, possibly deeper history)
  - Backtest a shorter window (2021-2024 train, 2025-today walk-forward)
  - Switch to ThetaData for backtest data
  - V's decision, not yours.

- **MarketData stocks/candles endpoint not exposed to Starter tier** — V would need to know whether to use yfinance fallback as a permanent solution. Probably yes. Easy fix.

- **D4 shows VRP signal generates 0 trades from yfinance prices alone** — this is the most concerning. Means the algorithm is wrong. Should not happen because VRP-z calculation is standard. But if it does, escalate to V before changing the algorithm.

---

## Expected pipeline for next 3-7 days

This is what V is trying to accomplish, in order. **Do not skip ahead.**

### Tue 6/17 (today — TONIGHT)
- [ ] Run D1 → D5 diagnostics above
- [ ] Identify root cause
- [ ] If it's a "PC Opus can fix" case → fix it, re-run VRP backtest, report verdict
- [ ] If it's an escalation case → write findings to V's terminal, **STOP**, wait for V to decide

### Wed 6/18
- [ ] **Watch Fed press conference at 11:30am ET** — Warsh's first. Significant volatility expansion + possible regime shift. The system's `market_weather` should flip if surprise. Run `curl http://localhost:8000/api/health` and `curl http://localhost:8000/api/briefing/daily` mid-day to see what the system says.
- [ ] After VRP backtest succeeds (whenever that is), launch parallel backtests for:
  - PEAD (FMP + yfinance — zero MarketData credits)
  - Momentum 12-1 (yfinance — zero credits)
  - Skew shorting (shares MarketData chain cache with VRP — minimal extra credits)
  - Pre-FOMC straddle (free — just FOMC dates + SPY)
- [ ] Each finishes with PROMOTE / OVERFIT / NO EDGE verdict using the same 2018-2024 / 2025-today split

### Thu 6/19
- [ ] Aggregate all signal verdicts
- [ ] Promote winners to paper trading (`paper_trades` table in DB)
- [ ] Start the daily scan + briefing cycle for real
- [ ] Each new paper trade creates a row in `recommendations` table (migration 018, Phase M)
- [ ] Nightly `evaluate_predictions` job (10:30pm ET, already scheduled) writes checkpoints

### Fri 6/20 — Sat 6/21
- [ ] **Nasdaq-100 rebalance effective Sat 6/21** (CRWV/NBIS/RKLB/ALAB/TER added). The system doesn't have an explicit detector yet (Phase P.2 in PENDING.md), but the scanner SHOULD pick up the unusual volume + price strength in those names. Watch whether they appear in the briefing's top picks Mon 6/23. This is a clean operational test.

### Mon 6/23 onward
- [ ] Daily 8am ET briefing fires (already scheduled in main.py)
- [ ] V reviews; N executes manually
- [ ] Trades logged to `recommendations` table with predicted target + horizon
- [ ] Nightly evaluator writes checkpoints
- [ ] Weekly Sun 10pm LightGBM retrain refines the ranker
- [ ] After 4 weeks of paper trading data, conviction-Brier calibration becomes meaningful

---

## The 5 things V cares about most right now

1. **VRP backtest produces a real number** (not 0 trades). PRIORITY.
2. **The free signal jobs (Phase 6.5) actually run** — they were started but had "dependency issues" per the previous session. Investigate D1 logs for those.
3. **The PC system is reachable** — `curl http://localhost:8000/api/health` should return everything green
4. **Daily briefing produces output** even if no signals pass — V wants to see the pipeline working end-to-end
5. **V doesn't waste another night** waiting for jobs that silently fail

---

## What NOT to do

- **Don't re-architect** anything. The architecture is right. V has spent days getting it right.
- **Don't invent new signals**. The 49 in the registry are enough. Validate them first.
- **Don't bypass the signal registry** (`scoring/signal_registry.py`). Every new signal must be registered.
- **Don't burn MarketData credits on speculative tests**. V is on Starter tier with 10k/day budget.
- **Don't claim a result is "validated" without DSR > 0.5 train AND > 0.3 walk-forward.** Refusing to promote bad signals is the system's superpower.
- **Don't disable the persistent cache** in `backtest/marketdata_source.py`. It's what makes parameter sweeps free.
- **Don't run sweeper on broken signals**. Fix the harness first, then sweep variants.

---

## Files V will check in the morning

Make sure these have content by then:

```
data/backtest_reports/
  vrp_leg1_train.log              ← V will tail this first
  vrp_leg2_walkforward.log
  vrp_2018_2024_train.json        ← V wants non-zero trades + real metrics here
  vrp_2025_2026_walkforward.json
  dna_seed.log
  cross_section.log
  insider.log
  lead_lag.log
  squeeze.log
  climate.log

data/marketdata_cache/             ← V will check size
  SPY/<expiry>/<date>.parquet      ← V wants this populated
  NVDA/<expiry>/<date>.parquet
  ...
```

V will then call the verdict template at the bottom of `OVERNIGHT_RUNBOOK.md`. That's the moment of truth.

---

## How to communicate with V

V is tired and frustrated. You will be 10x more useful if you:

1. **Report what you found**, not what you tried.
2. **Use the diagnosis → root cause → action format**: "D3 showed chain fetch returning None for 2018 dates. Root cause: MarketData Starter tier history depth limit. Action: switch backtest window to 2021-onward OR escalate to V for tier upgrade."
3. **Don't say "looks like X failed" without evidence.** Quote the actual log line.
4. **Don't conclude "signal failed validation" with 0 trades.** That conclusion can only be drawn when trades >= 100 and DSR < 0.35.
5. **If you fix something, run the tests**: `python3 -m pytest tests/ -q` should always pass 94/94 before declaring done.
6. **End every response with**: "What I did | What I found | What I changed | What I recommend V do next."

V's collaboration style: brutally honest, no flattery, recommend specific options first, don't write code unless asked or runbook says to.

---

## The honest truth about "moving Opus to PC"

V — you can't *move* the laptop Opus session. Each Claude Code session is independent. But:

- The codebase + docs ARE the persistent memory
- `SESSION_CONTEXT.md` boots any new session into ~95% of the laptop's context
- This doc (`PC_OPUS_HANDOFF.md`) handles the tactical now
- The laptop Opus (me) and PC Opus are the same model; given the same docs they'll behave the same way
- The "Haiku acting like an idiot" problem was Haiku being a smaller model with less reasoning. Opus on PC will be much better.

What you've done — written everything down in docs — is the right architecture for distributed AI collaboration. Don't beat yourself up. The system you've built is bigger than any one Claude session anyway.

---

## When PC Opus is done diagnosing tonight

End with this exact summary format so V can scan it quickly:

```
=== VRP BACKTEST DIAGNOSIS ===
Root cause: <one sentence>
Evidence: <log line OR diagnostic output that proves it>
Fix attempted: <what I changed, OR "escalating to V">
Verification: <what I ran to confirm, OR "blocked on V">
Tests: <X/94 passing>
Recommended next action for V: <one sentence>
```

Then exit.
