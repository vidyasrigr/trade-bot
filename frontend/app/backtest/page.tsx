"use client";

import { useState, useEffect } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

interface BacktestResults {
  run_date: string; period: string;
  total_simulated_trades: number; win_rate: number;
  avg_r_multiple: number; total_return_pct: number;
  max_drawdown_pct: number; sharpe_ratio: number;
  by_strategy: { strategy: string; trades: number; win_rate: number; avg_r: number; notes: string }[];
  by_regime: { regime: string; trades: number; win_rate: number; avg_r: number; best_strategy: string }[];
  top_factors_by_ic: { factor: string; ic: number; sample: number }[];
  monthly_returns: { month: string; pct: number }[];
  notes: string;
}

export default function BacktestPage() {
  const [results, setResults] = useState<BacktestResults | null>(null);

  useEffect(() => {
    fetch(`${API}/backtest/results`).then(r => r.json()).then(setResults);
  }, []);

  if (!results) return <div className="p-6 text-gray-500">Loading backtest results...</div>;

  const maxMonthly = Math.max(...results.monthly_returns.map(m => Math.abs(m.pct)));

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Backtest Results</h1>
        <p className="text-gray-400 text-sm mt-1">{results.period} · Run {results.run_date}</p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <BigStat label="Total Trades" value={results.total_simulated_trades.toLocaleString()} />
        <BigStat label="Win Rate" value={`${results.win_rate.toFixed(1)}%`} color="text-green-400" />
        <BigStat label="Avg R" value={`${results.avg_r_multiple.toFixed(2)}R`} color="text-green-400" />
        <BigStat label="Total Return" value={`+${results.total_return_pct.toFixed(1)}%`} color="text-green-400" />
        <BigStat label="Max Drawdown" value={`-${results.max_drawdown_pct.toFixed(1)}%`} color="text-red-400" />
        <BigStat label="Sharpe" value={results.sharpe_ratio.toFixed(2)} color="text-blue-400" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Monthly returns bar chart */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h2 className="text-gray-200 font-semibold mb-3">Monthly Returns</h2>
          <div className="flex items-end gap-1 h-28">
            {results.monthly_returns.map(m => {
              const h = Math.abs(m.pct) / maxMonthly * 100;
              const positive = m.pct >= 0;
              return (
                <div key={m.month} className="flex-1 flex flex-col items-center gap-0.5 group relative">
                  {positive
                    ? <div className="w-full bg-green-600/80 rounded-sm mt-auto" style={{ height: `${h}%` }} />
                    : <div className="w-full bg-red-700/80 rounded-sm" style={{ height: `${h}%` }} />}
                  <div className="absolute bottom-full mb-1 bg-gray-800 text-white text-xs px-1.5 py-0.5 rounded hidden group-hover:block whitespace-nowrap z-10">
                    {m.month}: {m.pct >= 0 ? "+" : ""}{m.pct.toFixed(1)}%
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-gray-600 text-xs mt-1">
            <span>{results.monthly_returns[0].month}</span>
            <span>{results.monthly_returns[results.monthly_returns.length - 1].month}</span>
          </div>
        </div>

        {/* Factor IC */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h2 className="text-gray-200 font-semibold mb-3">Top Factors by IC Score</h2>
          <div className="space-y-1.5">
            {results.top_factors_by_ic.map(f => (
              <div key={f.factor} className="flex items-center gap-2 text-xs">
                <span className="text-gray-400 w-32 font-mono">{f.factor}</span>
                <div className="flex-1 h-2 bg-gray-800 rounded-full">
                  <div
                    className={`h-2 rounded-full ${f.ic >= 0.07 ? "bg-green-500" : f.ic >= 0.05 ? "bg-yellow-500" : "bg-red-500"}`}
                    style={{ width: `${(f.ic / 0.12) * 100}%` }}
                  />
                </div>
                <span className={`w-12 text-right font-mono font-bold ${f.ic >= 0.07 ? "text-green-400" : f.ic >= 0.05 ? "text-yellow-400" : "text-red-400"}`}>
                  {f.ic.toFixed(3)}
                </span>
                <span className="text-gray-600 w-12 text-right">n={f.sample}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* By strategy */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 text-gray-200 font-semibold text-sm">Performance by Strategy</div>
          <table className="w-full text-xs">
            <thead><tr className="text-gray-500 border-b border-gray-800">
              <th className="px-3 py-2 text-left">Strategy</th>
              <th className="px-3 py-2 text-right">Trades</th>
              <th className="px-3 py-2 text-right">WR%</th>
              <th className="px-3 py-2 text-right">Avg R</th>
            </tr></thead>
            <tbody className="divide-y divide-gray-800/50">
              {results.by_strategy.map(s => (
                <tr key={s.strategy} className="text-gray-300">
                  <td className="px-3 py-2 font-mono text-xs">{s.strategy}</td>
                  <td className="px-3 py-2 text-right text-gray-500">{s.trades}</td>
                  <td className={`px-3 py-2 text-right font-bold ${s.win_rate >= 65 ? "text-green-400" : s.win_rate >= 55 ? "text-yellow-400" : "text-red-400"}`}>
                    {s.win_rate.toFixed(0)}%
                  </td>
                  <td className={`px-3 py-2 text-right font-bold ${s.avg_r >= 1.2 ? "text-green-400" : s.avg_r >= 0.8 ? "text-yellow-400" : "text-red-400"}`}>
                    {s.avg_r.toFixed(2)}R
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* By regime */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 text-gray-200 font-semibold text-sm">Performance by Market Regime</div>
          <table className="w-full text-xs">
            <thead><tr className="text-gray-500 border-b border-gray-800">
              <th className="px-3 py-2 text-left">Regime</th>
              <th className="px-3 py-2 text-right">WR%</th>
              <th className="px-3 py-2 text-right">Avg R</th>
              <th className="px-3 py-2 text-left">Best Strategy</th>
            </tr></thead>
            <tbody className="divide-y divide-gray-800/50">
              {results.by_regime.map(r => (
                <tr key={r.regime} className="text-gray-300">
                  <td className="px-3 py-2 capitalize text-gray-400">{r.regime.replace("_", " ")}</td>
                  <td className={`px-3 py-2 text-right font-bold ${r.win_rate >= 65 ? "text-green-400" : "text-yellow-400"}`}>
                    {r.win_rate.toFixed(0)}%
                  </td>
                  <td className={`px-3 py-2 text-right font-bold ${r.avg_r >= 1.2 ? "text-green-400" : "text-yellow-400"}`}>
                    {r.avg_r.toFixed(2)}R
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-blue-400">{r.best_strategy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Notes */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-gray-400 text-xs leading-relaxed">
        <span className="text-gray-500 font-medium">Methodology note: </span>{results.notes}
      </div>
    </div>
  );
}

function BigStat({ label, value, color = "text-white" }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 text-center">
      <div className="text-gray-500 text-xs mb-1">{label}</div>
      <div className={`font-bold text-lg ${color}`}>{value}</div>
    </div>
  );
}
