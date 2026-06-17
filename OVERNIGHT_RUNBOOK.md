# Overnight Runbook — VRP Validation + DNA Seed

**For**: a Claude Code session running Haiku on V's PC.
**Goal**: run the two VRP backtest legs (2018-2024 train fold + 2025→today walk-forward), in parallel with the per-stock DNA batch.
**Time**: ~6-10 hours wall clock. Safe to leave overnight.

You are spoon-fed. Every step is a single command with explicit pass/fail. If a step fails, **STOP and tell V** instead of guessing. Do not invent code or modify files unless this doc says to.

---

## Phase 0 — Sanity (3 min)

Run each block, paste the output back so V can verify.

### 0.1 Working directory + Python

```bash
cd /Users/V/Projects/Options/backend
python3 --version    # expect 3.10 or higher
which python3
```

### 0.2 Required env keys present

```bash
python3 -c "
import os
need = ['MARKETDATA_API_KEY','FRED_API_KEY','FMP_API_KEY','ALPHA_VANTAGE_API_KEY']
missing = [k for k in need if not os.environ.get(k)]
print('MISSING:', missing if missing else 'none ✅')
# Anthropic optional for backtest; warn if absent
if not os.environ.get('ANTHROPIC_API_KEY'):
    print('NOTE: ANTHROPIC_API_KEY not set — fine for backtest, blocks live scans')
"
```

**PASS**: prints `MISSING: none ✅`. If anything else is missing, STOP.

### 0.3 Python deps — use requirements.txt

```bash
pip install -r requirements.txt 2>&1 | tail -5
python3 -m scripts.status
```

**PASS**: `scripts.status` shows green on every required dep.

**FAIL modes Haiku must handle**:
- If a *single* package fails to build (commonly `bcrypt`, `psycopg2-binary`, `pandas-ta`), install the rest by retrying line by line:
  `grep -vE '^#|^$' requirements.txt | xargs -n1 pip install || true`
- `pandas-ta` may fail on Python 3.13 — drop it from the list and continue; system degrades gracefully.
- `psycopg2-binary` needs `pg_config` on macOS — `brew install postgresql` first, then retry.
- Torch is NOT in requirements.txt because it needs the CUDA index URL — see Phase 1.2.

---

## Phase 1 — GPU / CUDA verification (2 min)

### 1.1 NVIDIA driver

```bash
nvidia-smi
```

**PASS**: prints a table with `NVIDIA GeForce RTX 5080`, driver version, CUDA version. If "command not found", driver isn't installed — STOP.

### 1.2 PyTorch GPU — install matching CUDA wheel

**FIRST detect the CUDA version reported by the driver:**

```bash
nvidia-smi | grep -i "CUDA Version" | head -1
```

Typical readings: `CUDA Version: 12.1`, `12.4`, or `11.8`. Pick the matching wheel.

```bash
# CUDA 12.1 (most common today):
pip install torch --index-url https://download.pytorch.org/whl/cu121

# CUDA 12.4 (newer drivers):
# pip install torch --index-url https://download.pytorch.org/whl/cu124

# CUDA 11.8 (older drivers):
# pip install torch --index-url https://download.pytorch.org/whl/cu118
```

Verify:

```bash
python3 -c "
import torch
print('torch version:', torch.__version__)
print('CUDA available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('CUDA version:', torch.version.cuda)
    print('Device:', torch.cuda.get_device_name(0))
    print('VRAM (GB):', round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1))
"
```

**PASS**: `CUDA available: True`, device contains `5080`, VRAM ~16GB.

**FAIL modes**:
- `CUDA available: False` after a fresh install → wrong wheel for the driver. Pick the cuXXX matching nvidia-smi and `pip install torch --upgrade --force-reinstall --index-url https://download.pytorch.org/whl/cuXXX`.
- `RuntimeError: Found no NVIDIA driver` → driver broken; STOP and tell V.
- On macOS: GPU torch wheels are not published. Accept CPU torch (`pip install torch` without the index URL). The backtest does NOT require GPU torch — only sweeper's optional GPU metrics path uses it, and CuPy is the actual GPU dependency.

### 1.3 CuPy (OPTIONAL — skip if it errors, not blocking)

```bash
pip install cupy-cuda12x || echo "CuPy install failed — sweeper will use numpy fallback (this is fine)"

python3 -c "
try:
    import cupy as cp
    x = cp.array([1.0, 2.0, 3.0])
    print('CuPy OK:', x.sum())
except Exception as e:
    print('CuPy not available — sweeper falls back to numpy. NOT BLOCKING:', type(e).__name__)
"
```

PASS: either "CuPy OK" or the graceful fallback message. **DO NOT BLOCK on CuPy.** The backtest does not need it — it only accelerates the sweeper's metrics path. Numpy fallback gives identical results, just slower.

---

## Phase 2 — Ollama models (5 min)

### 2.1 Ollama running

```bash
curl -s http://localhost:11434/api/tags > /tmp/ollama_tags.json
cat /tmp/ollama_tags.json | python3 -c "import json, sys; d = json.load(sys.stdin); print('Installed models:', [m['name'] for m in d.get('models', [])])"
```

**PASS**: prints a list. If "connection refused", run `ollama serve &` first.

### 2.2 Pull required models

The system uses 3 local models. Pull each:

```bash
ollama pull llama3.1:8b           # sentiment analyst (~5GB)
ollama pull deepseek-r1:7b         # adversary (~5GB)
ollama pull nomic-embed-text       # embeddings (~300MB)
```

### 2.3 (Optional but recommended) Pull QwQ-32B for better reasoning

```bash
ollama pull qwq:32b-q3_k_m         # ~15GB — best adversary upgrade
```

If VRAM is tight, skip and stay with `deepseek-r1:7b`.

### 2.4 Smoke-test the models

```bash
python3 -c "
import httpx
for m in ['llama3.1:8b', 'deepseek-r1:7b', 'nomic-embed-text']:
    try:
        r = httpx.post('http://localhost:11434/api/generate',
                       json={'model': m, 'prompt': 'hi', 'stream': False}, timeout=30)
        print(f'  ✅ {m}' if r.status_code == 200 else f'  ❌ {m} status={r.status_code}')
    except Exception as e:
        print(f'  ❌ {m} error={e}')
"
```

**PASS**: 3 green checks. If any are red, re-pull the model.

---

## Phase 2.5 — Update migrations list (NEW)

Migration **017** was added 2026-06-16 (per-stock climate + market weather). Update the migration loop in Phase 3 below to include it.

---

## Phase 3 — Database migrations (one-time, 3 min)

Confirm Postgres is up:

```bash
psql $DATABASE_URL -c "SELECT 1;" 2>&1 | tail -2
```

PASS: `(1 row)`. If error, start Postgres (`brew services start postgresql` or your equivalent).

Run migrations 007-017 in order. **Do not skip any.**

```bash
for n in 007 008 009 010 011 012 013 014 015 016 017 018; do
  echo "=== Migration $n ==="
  psql $DATABASE_URL -f db/migrations/${n}_*.sql || { echo "FAILED at $n"; break; }
done
psql $DATABASE_URL -c "\dt" | tail -25
```

**PASS**: each migration completes without error; the `\dt` listing shows tables `signal_ranks`, `model_runs`, `backtest_runs`, `regime_forecasts`, `whale_flow_signals`, `short_squeeze_signals`, `reddit_signals`, `stock_climate`, `market_weather`, etc.

---

## Phase 4 — Feature store bootstrap (~25 min)

```bash
python3 -m scripts.backfill_feature_store --days 700 --max-symbols 500 2>&1 | tee /tmp/backfill.log | tail -20
```

**PASS**: log ends with `Backfill complete: {..., snapshots_written: N}` where N ≥ 60.

---

## Phase 4.5 — IF MarketData key NOT YET SET, run FREE backtests now (NEW)

**Haiku, READ THIS FIRST**: If `MARKETDATA_API_KEY` is not in `.env`, do NOT block on Phase 5. The swing + LT validation in **Phase 6.5** below is **100% free** (yfinance + FMP free tier only) and you can launch it RIGHT NOW. V will paste the MarketData key when ready, and you'll resume Phase 5 at that point.

Check:
```bash
python3 -c "import os; print('MD_KEY_SET' if os.environ.get('MARKETDATA_API_KEY') else 'MD_KEY_MISSING — skip to Phase 6.5')"
```

- If `MD_KEY_SET` → continue to Phase 5
- If `MD_KEY_MISSING` → **skip Phase 5 and Phase 6.3/6.4 (options legs). Jump to Phase 6.5 (free swing+LT validation). Resume Phase 5 when key arrives.**

---

## Phase 5 — Smoke-test MarketData historical chains (1 min)

```bash
python3 -c "
import asyncio
from data.marketdata import MarketDataClient

async def go():
    c = MarketDataClient()
    for d in ['2024-05-01', '2024-05-15', '2024-06-01']:
        chain = await c.get_options_chain('SPY', '2024-06-21', as_of=d)
        atm = [o for o in chain if o.get('option_type', '').lower().startswith('c') and 530 <= float(o.get('strike', 0)) <= 550]
        if not atm:
            print(f'  ❌ {d}: 0 calls returned'); continue
        s = atm[0]
        print(f'  ✅ {d}: strike={s[\"strike\"]} bid={s[\"bid\"]} ask={s[\"ask\"]} delta={s.get(\"greeks\",{}).get(\"delta\")}')

asyncio.run(go())
"
```

**PASS**: 3 green checks, bid/ask values **different across the 3 dates** (proves historical data is real, not today's quote being returned every time).

If FAIL (empty chains or same values): paste error to V before proceeding. Backtest cannot run without this.

---

## Phase 6 — Launch the two backtest legs + DNA seed (the actual overnight work)

### 6.1 Make sure output dir exists

```bash
mkdir -p data/backtest_reports
```

### 6.2 Launch DNA batch in background (independent, doesn't block backtest)

```bash
nohup python3 -c "
import asyncio
from analysis.stock_dna import run_nightly_dna_batch
from data.scanner import get_full_universe

async def go():
    universe = get_full_universe()
    print(f'DNA seed: {len(universe)} symbols')
    await run_nightly_dna_batch(universe, max_concurrent=5)
    print('DNA seed DONE')
asyncio.run(go())
" > data/backtest_reports/dna_seed.log 2>&1 &
echo $! > data/backtest_reports/dna.pid
echo "DNA seed running as PID $(cat data/backtest_reports/dna.pid)"
```

### 6.3 Launch backtest LEG 1 (train fold 2018-01-01 → 2024-12-31)

```bash
nohup python3 -c "
import asyncio, json
from datetime import date
from backtest.strategies.vrp_harvest import run_vrp_backtest
from backtest.marketdata_source import MarketDataHistoricalSource

UNIVERSE = ['SPY','QQQ','IWM','DIA','AAPL','MSFT','NVDA','AMZN','META','GOOGL',
            'TSLA','AMD','AVGO','INTC','MU','JPM','BAC','GS','MS','WFC',
            'XOM','CVX','UNH','LLY','JNJ','PFE','ABBV','COST','HD','WMT',
            'KO','PEP','MCD','DIS','NFLX','CRM','ORCL','BA','CAT','MMM']

async def go():
    source = MarketDataHistoricalSource()
    print(f'LEG 1: train fold 2018-01-01 → 2024-12-31, {len(UNIVERSE)} names')
    report = await run_vrp_backtest(
        symbols=UNIVERSE, source=source,
        start=date(2018,1,1), end=date(2024,12,31),
    )
    with open('data/backtest_reports/vrp_2018_2024_train.json','w') as f:
        json.dump({
            'leg': 'train',
            'window': '2018-01-01 to 2024-12-31',
            'universe_size': len(UNIVERSE),
            'metrics': report.metrics,
            'num_trades': len(report.results),
        }, f, indent=2, default=str)
    print('LEG 1 DONE')
    print(json.dumps(report.metrics, indent=2, default=str))

asyncio.run(go())
" > data/backtest_reports/vrp_leg1_train.log 2>&1 &
echo $! > data/backtest_reports/leg1.pid
echo "LEG 1 running as PID $(cat data/backtest_reports/leg1.pid)"
```

### 6.4 Launch backtest LEG 2 (walk-forward 2025-01-01 → 2026-06-15) — also in parallel

LEG 2 hits different contracts than LEG 1, so they parallelize cleanly. If you'd rather sequence them to be polite to MarketData, sleep 4 hours after LEG 1 starts. With 100k credits/day budget, parallel is fine.

```bash
nohup python3 -c "
import asyncio, json
from datetime import date
from backtest.strategies.vrp_harvest import run_vrp_backtest
from backtest.marketdata_source import MarketDataHistoricalSource

UNIVERSE = ['SPY','QQQ','IWM','DIA','AAPL','MSFT','NVDA','AMZN','META','GOOGL',
            'TSLA','AMD','AVGO','INTC','MU','JPM','BAC','GS','MS','WFC',
            'XOM','CVX','UNH','LLY','JNJ','PFE','ABBV','COST','HD','WMT',
            'KO','PEP','MCD','DIS','NFLX','CRM','ORCL','BA','CAT','MMM']

async def go():
    source = MarketDataHistoricalSource()
    print(f'LEG 2: walk-forward 2025-01-01 → 2026-06-15, {len(UNIVERSE)} names')
    report = await run_vrp_backtest(
        symbols=UNIVERSE, source=source,
        start=date(2025,1,1), end=date(2026,6,15),
    )
    with open('data/backtest_reports/vrp_2025_2026_walkforward.json','w') as f:
        json.dump({
            'leg': 'walk_forward',
            'window': '2025-01-01 to 2026-06-15',
            'universe_size': len(UNIVERSE),
            'metrics': report.metrics,
            'num_trades': len(report.results),
        }, f, indent=2, default=str)
    print('LEG 2 DONE')
    print(json.dumps(report.metrics, indent=2, default=str))

asyncio.run(go())
" > data/backtest_reports/vrp_leg2_walkforward.log 2>&1 &
echo $! > data/backtest_reports/leg2.pid
echo "LEG 2 running as PID $(cat data/backtest_reports/leg2.pid)"
```

### 6.5 NEW — Launch FREE swing + LT backtests (no MarketData needed)

These can run **regardless of whether MD key is set**. Launch them in parallel with whatever else is running. Cost: $0 credits.

```bash
nohup python3 -c "
import asyncio, json
from datetime import date

# 7 yfinance-only signals across full liquid universe
UNIVERSE_LIQUID = None  # let the harness pick top-2000 by dollar volume

async def go():
    from data.scanner import get_scan_universe
    universe = (await get_scan_universe())[:2000]
    print(f'Free-tier backtests on {len(universe)} symbols')

    # Momentum 12-1 (Jegadeesh-Titman)
    from analysis.momentum import _spx_crash_regime
    # ... placeholder: each signal's backtest harness goes here
    # Real implementation in backtest/strategies/free_signals.py (TODO if missing)
    print('SWING/LT backtest scaffolding pending — see PARALLEL_VALIDATION_PLAN.md')

asyncio.run(go())
" > data/backtest_reports/free_signals_day1.log 2>&1 &
echo $! > data/backtest_reports/free.pid
echo "FREE backtests running as PID $(cat data/backtest_reports/free.pid)"
```

**NOTE TO HAIKU**: The unified `backtest/strategies/free_signals.py` harness for all 7 yfinance-only signals (momentum_12_1, lead_lag, pairs, PEAD, insider, LT score, 52w high) is NOT YET WRITTEN. **DO NOT try to write it from scratch — that's a multi-hundred-line task.** Instead, if MD key isn't there, run these individual scripts which DO exist:

```bash
# Already-existing nightly jobs — run them on-demand to get same-day evidence
nohup python3 -c "import asyncio; from analysis.cross_section_job import run_cross_section_job; asyncio.run(run_cross_section_job())" > data/backtest_reports/cross_section.log 2>&1 &
nohup python3 -c "import asyncio; from analysis.insider_flow import run_insider_flow_job; asyncio.run(run_insider_flow_job())" > data/backtest_reports/insider.log 2>&1 &
nohup python3 -c "import asyncio; from analysis.lead_lag import run_lead_lag_job; asyncio.run(run_lead_lag_job())" > data/backtest_reports/lead_lag.log 2>&1 &
nohup python3 -c "import asyncio; from analysis.short_squeeze import run_short_squeeze_job; asyncio.run(run_short_squeeze_job())" > data/backtest_reports/squeeze.log 2>&1 &
nohup python3 -c "import asyncio; from analysis.stock_climate import run_climate_job; asyncio.run(run_climate_job())" > data/backtest_reports/climate.log 2>&1 &
echo "Cross-section, insider, lead_lag, squeeze, climate jobs launched"
```

These compute TODAY's signal values across the universe (not historical backtests). They populate `signal_ranks` so V can immediately see which names look attractive on each signal RIGHT NOW. A proper historical backtest of these signals comes next session.

### 6.6 Confirm all jobs are running

```bash
sleep 3
ps -p $(cat data/backtest_reports/dna.pid) > /dev/null && echo "✅ DNA running" || echo "❌ DNA died"
ps -p $(cat data/backtest_reports/leg1.pid) > /dev/null && echo "✅ LEG 1 running" || echo "❌ LEG 1 died"
ps -p $(cat data/backtest_reports/leg2.pid) > /dev/null && echo "✅ LEG 2 running" || echo "❌ LEG 2 died"
```

If anything shows ❌, `tail -50 data/backtest_reports/<that>.log` for the error. Most likely cause: missing env var. Fix and relaunch.

### 6.6 Tell V

Print this exact summary, then exit. Do not loop.

```text
=== OVERNIGHT JOBS LAUNCHED ===
DNA seed:      data/backtest_reports/dna_seed.log
VRP train fold:  data/backtest_reports/vrp_leg1_train.log
VRP walk-fwd:    data/backtest_reports/vrp_leg2_walkforward.log
Results JSON:
  data/backtest_reports/vrp_2018_2024_train.json
  data/backtest_reports/vrp_2025_2026_walkforward.json

In the morning:
  tail -30 data/backtest_reports/vrp_leg1_train.log
  tail -30 data/backtest_reports/vrp_leg2_walkforward.log
  cat data/backtest_reports/vrp_2018_2024_train.json | python3 -m json.tool
  cat data/backtest_reports/vrp_2025_2026_walkforward.json | python3 -m json.tool
```

---

## Morning verdict template (V runs this)

```bash
cd /Users/V/Projects/Options/backend

python3 -c "
import json, os
def load(p):
    return json.load(open(p)) if os.path.exists(p) else None
t = load('data/backtest_reports/vrp_2018_2024_train.json')
w = load('data/backtest_reports/vrp_2025_2026_walkforward.json')
if not t or not w:
    print('Reports missing. Check the .log files.')
    raise SystemExit(1)
tdsr = t['metrics'].get('deflated_sharpe', 0)
wdsr = w['metrics'].get('deflated_sharpe', 0)
print(f'TRAIN  dsr={tdsr:+.2f}  trades={t[\"num_trades\"]}  win_rate={t[\"metrics\"].get(\"win_rate\",0):.0%}  pnl=\${t[\"metrics\"].get(\"total_pnl\",0):.0f}')
print(f'WF     dsr={wdsr:+.2f}  trades={w[\"num_trades\"]}  win_rate={w[\"metrics\"].get(\"win_rate\",0):.0%}  pnl=\${w[\"metrics\"].get(\"total_pnl\",0):.0f}')
print()
if tdsr > 0.5 and wdsr > 0.3:
    print('✅ PROMOTE VRP TO PAPER')
elif tdsr > 0.5:
    print('⚠️  OVERFIT — train passed, WF failed. SANDBOX it.')
else:
    print('❌ NO EDGE in this universe. SANDBOX. Try wider universe or different params.')
"
```

---

## Rules for the Haiku session

1. **Do NOT modify files** unless this doc explicitly tells you to.
2. **Do NOT invent commands.** Run only what's here.
3. **Do NOT call Claude APIs** during backtest. Entry/exit is deterministic from the signal logic in `vrp_harvest.py`.
4. **STOP and report** if any PASS check fails. Don't push through and hope.
5. **Total spend cap**: V has 100k MarketData credits/day. Even 2 parallel backtests on 40 names won't exceed ~10-20k.
6. **Anthropic key not present is FINE** for this run.
7. End your session by printing the summary in 6.6 and exiting.
