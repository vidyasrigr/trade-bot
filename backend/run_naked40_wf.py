"""40-name naked-strangle VRP, walk-forward leg only — breadth confirmation.

Cached 20 are free (disk); the new 20 cost ~2,180 credits (322 cand × 6.78),
well under V's 7,000 cap. Answers: does walk-forward DSR hold with broader breadth?
"""
import asyncio, json
from datetime import date
from backtest.strategies.vrp_harvest import run_vrp_backtest
from backtest.marketdata_source import MarketDataHistoricalSource

UNIVERSE = ['SPY','QQQ','IWM','DIA','AAPL','MSFT','NVDA','AMZN','META','GOOGL',
            'TSLA','AMD','AVGO','INTC','MU','JPM','BAC','GS','MS','WFC',
            'XOM','CVX','UNH','LLY','JNJ','PFE','ABBV','COST','HD','WMT',
            'KO','PEP','MCD','DIS','NFLX','CRM','ORCL','BA','CAT','MMM']
OUT = '/home/vi/Projects/Trade Bot/data/backtest_reports'


async def main():
    src = MarketDataHistoricalSource()
    print(f'40-name naked walk-forward 2025-01-01 → 2026-06-17', flush=True)
    rep = await run_vrp_backtest(UNIVERSE, src, date(2025, 1, 1), date(2026, 6, 17))
    m = rep.metrics
    with open(f'{OUT}/vrp_naked40_walkforward.json', 'w') as f:
        json.dump({'leg': 'walkforward_40name', 'variant': 'naked_strangle',
                   'window': '2025-01-01 to 2026-06-17', 'universe_size': len(UNIVERSE),
                   'metrics': m, 'num_trades': len(rep.results)}, f, indent=2, default=str)
    print(f"DONE: trades={len(rep.results)} win={m.get('win_rate')} "
          f"dsr={m.get('deflated_sharpe')} maxdd={m.get('max_drawdown')} "
          f"sharpe={m.get('sharpe')} pnl={m.get('total_pnl')}", flush=True)
    print('CREDIT COST (api_fetches):', src.stats, flush=True)


asyncio.run(main())
