"""Iron-condor VRP — both legs on the cached 20-name universe. Reports credits."""
import asyncio, json
from datetime import date
from backtest.strategies.vrp_harvest_ic import run_vrp_ic_backtest
from backtest.marketdata_source import MarketDataHistoricalSource

# The 20 names fully cached from the naked run (276+ chains each).
UNIVERSE = ['SPY','QQQ','IWM','AAPL','MSFT','NVDA','AMZN','META','GOOGL','TSLA',
            'AMD','JPM','BAC','XOM','UNH','LLY','COST','WMT','DIS','NFLX']

OUT = '/home/vi/Projects/Trade Bot/data/backtest_reports'


async def leg(source, name, start, end):
    print(f'=== IC {name}: {start} → {end} ===', flush=True)
    rep = await run_vrp_ic_backtest(UNIVERSE, source, start, end)
    m = rep.metrics
    payload = {
        'leg': name, 'variant': 'iron_condor',
        'window': f'{start} to {end}',
        'universe_size': len(UNIVERSE),
        'metrics': m, 'num_trades': len(rep.results),
    }
    with open(f'{OUT}/vrp_ic_{name}.json', 'w') as f:
        json.dump(payload, f, indent=2, default=str)
    print(f'IC {name} DONE: trades={len(rep.results)} '
          f"win={m.get('win_rate')} dsr={m.get('deflated_sharpe')} "
          f"maxdd={m.get('max_drawdown')} pnl={m.get('total_pnl')}", flush=True)
    return rep


async def main():
    source = MarketDataHistoricalSource()  # shared cache across both legs
    await leg(source, 'train', date(2021, 7, 1), date(2024, 12, 31))
    await leg(source, 'walkforward', date(2025, 1, 1), date(2026, 6, 17))
    print('FINAL source stats (credit cost):', source.stats, flush=True)


asyncio.run(main())
