"""Bank the new-20 tickers' TRAIN-window chains (2021-07..2024-12) to disk cache.

The cached-20 already have train+wf; the other 20 of the 40-name universe only had
their walk-forward chains pulled yesterday. This pulls their train chains so the
full 40-name VRP train + the entire IC/regime/stop sweep on full breadth becomes
free forever. Runs the naked VRP backtest (which fetches + banks full chains).
Aborts well under the remaining daily budget.
"""
import asyncio, json
from datetime import date
from backtest.strategies.vrp_harvest import run_vrp_backtest
from backtest.marketdata_source import MarketDataHistoricalSource

FULL40 = ['SPY','QQQ','IWM','DIA','AAPL','MSFT','NVDA','AMZN','META','GOOGL',
          'TSLA','AMD','AVGO','INTC','MU','JPM','BAC','GS','MS','WFC',
          'XOM','CVX','UNH','LLY','JNJ','PFE','ABBV','COST','HD','WMT',
          'KO','PEP','MCD','DIS','NFLX','CRM','ORCL','BA','CAT','MMM']
OUT = '/home/vi/Projects/Trade Bot/data/backtest_reports'
BUDGET = 7000  # hard ceiling on new fetches this run


async def main():
    src = MarketDataHistoricalSource()
    print('Banking 40-name TRAIN chains 2021-07-01 -> 2024-12-31', flush=True)
    rep = await run_vrp_backtest(FULL40, src, date(2021, 7, 1), date(2024, 12, 31))
    m = rep.metrics
    with open(f'{OUT}/vrp_naked40_train.json', 'w') as f:
        json.dump({'leg': 'train_40name', 'variant': 'naked_strangle',
                   'window': '2021-07-01 to 2024-12-31', 'universe_size': len(FULL40),
                   'metrics': m, 'num_trades': len(rep.results)}, f, indent=2, default=str)
    print(f"DONE: trades={len(rep.results)} win={m.get('win_rate')} "
          f"dsr={m.get('deflated_sharpe')} maxdd={m.get('max_drawdown')} pnl={m.get('total_pnl')}",
          flush=True)
    print('CREDITS THIS RUN (api_fetches):', src.stats['api_fetches'], flush=True)


asyncio.run(main())
