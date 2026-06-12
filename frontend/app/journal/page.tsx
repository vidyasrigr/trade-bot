"use client";

import { useState, useEffect } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export default function JournalPage() {
  const [entries, setEntries] = useState<unknown[]>([]);
  const [weights, setWeights] = useState<unknown[]>([]);

  useEffect(() => {
    fetch(`${API}/memory/journal`).then(r => r.json()).then(d => setEntries(d.entries || []));
    fetch(`${API}/memory/weights`).then(r => r.json()).then(d => setWeights(d.weights || []));
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Learning Journal</h1>

      <div className="grid grid-cols-2 gap-6">
        {/* Memory entries */}
        <div>
          <h2 className="text-lg font-semibold text-gray-200 mb-3">Trade Lessons</h2>
          <div className="space-y-3">
            {entries.length === 0 ? (
              <div className="text-gray-500 text-sm py-8 text-center">No lessons yet — close some trades to generate post-mortems</div>
            ) : entries.map((e: unknown) => {
              const entry = e as {
                id: number; symbol: string; regime: string; lesson: string;
                r_multiple: number | null; factors_that_worked: string[]; factors_that_failed: string[];
                created_at: string;
              };
              return (
                <div key={entry.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <span className="text-white font-bold mr-2">{entry.symbol}</span>
                      <span className="text-gray-500 text-xs">{entry.regime}</span>
                    </div>
                    {entry.r_multiple !== null && (
                      <span className={`flex items-center gap-1 text-sm font-bold ${entry.r_multiple >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {entry.r_multiple >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {entry.r_multiple?.toFixed(2)}R
                      </span>
                    )}
                  </div>
                  <p className="text-gray-300 text-sm">{entry.lesson}</p>
                  {entry.factors_that_worked?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {entry.factors_that_worked.map(f => (
                        <span key={f} className="bg-green-900/30 text-green-400 text-xs px-2 py-0.5 rounded-full">✓ {f}</span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* IC weight tracker */}
        <div>
          <h2 className="text-lg font-semibold text-gray-200 mb-3">Factor IC Weights</h2>
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500">
                  <th className="px-3 py-2 text-left">Category</th>
                  <th className="px-3 py-2 text-left">Regime</th>
                  <th className="px-3 py-2 text-right">IC</th>
                  <th className="px-3 py-2 text-right">Multiplier</th>
                  <th className="px-3 py-2 text-right">Trades</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {weights.slice(0, 20).map((w: unknown) => {
                  const weight = w as { category: string; regime: string; ic_score: number; weight_multiplier: number; sample_count: number };
                  return (
                    <tr key={`${weight.category}-${weight.regime}`} className="text-gray-300">
                      <td className="px-3 py-1.5 font-mono">{weight.category}</td>
                      <td className="px-3 py-1.5 text-gray-500">{weight.regime}</td>
                      <td className={`px-3 py-1.5 text-right font-mono ${weight.ic_score > 0.05 ? "text-green-400" : "text-red-400"}`}>
                        {weight.ic_score?.toFixed(3)}
                      </td>
                      <td className={`px-3 py-1.5 text-right font-mono ${weight.weight_multiplier >= 1 ? "text-white" : "text-yellow-400"}`}>
                        {weight.weight_multiplier?.toFixed(2)}×
                      </td>
                      <td className="px-3 py-1.5 text-right text-gray-500">{weight.sample_count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
