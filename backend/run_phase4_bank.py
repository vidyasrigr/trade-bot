"""Phase 4 — bank new sector/skew-diverse optionable names (train+wf) to chain cache."""
import asyncio, json
from datetime import date
from backtest.strategies.vrp_harvest import run_vrp_backtest
from backtest.marketdata_source import MarketDataHistoricalSource
NEW = ['C','SCHW','GILD','AMGN','REGN','PLTR','COIN','SMCI','MRVL']
OUT='/home/vi/Projects/Trade Bot/data/backtest_reports'
async def main():
    src=MarketDataHistoricalSource()
    print(f'Phase 4 banking {len(NEW)} names train+wf', flush=True)
    tr=await run_vrp_backtest(NEW,src,date(2021,7,1),date(2024,12,31))
    print(f'TRAIN done: {len(tr.results)} trades; api_fetches so far={src.stats["api_fetches"]} exp_api={src.stats["expirations_api"]}', flush=True)
    wf=await run_vrp_backtest(NEW,src,date(2025,1,1),date(2026,6,18))
    print(f'WF done: {len(wf.results)} trades', flush=True)
    print('TOTAL credits this run:', src.stats['api_fetches'] + src.stats['expirations_api'], '| stats:', src.stats, flush=True)
    json.dump({'names':NEW,'train_trades':len(tr.results),'wf_trades':len(wf.results),
               'train_metrics':tr.metrics,'wf_metrics':wf.metrics,'stats':src.stats},
              open(f'{OUT}/phase4_bank.json','w'), indent=2, default=str)
asyncio.run(main())
