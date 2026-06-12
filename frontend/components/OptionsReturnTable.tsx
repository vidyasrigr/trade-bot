"use client";

import { useState, useEffect } from "react";
import { TrendingUp, Target, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";

interface OptimizerRow {
  expiry: string;
  dte: number;
  strike: number;
  type: "call" | "put";
  option_price: number;
  iv_pct: number;
  delta: number;
  // 30% gain
  target_price_30: number;
  move_pct_30: number;
  prob_30: number;
  conf_30: number;
  // 100% gain
  target_price_100: number;
  move_pct_100: number;
  prob_100: number;
  conf_100: number;
  recommended: boolean;
  rationale: string;
}

interface OptimizerData {
  symbol: string;
  current_price: number;
  iv_pct: number;
  hv20_pct: number;
  direction: string;
  iv_vs_hv: string;
  rows: OptimizerRow[];
  note: string;
}

type GainTarget = "30" | "100";

function ConfBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? "bg-green-900/50 text-green-400 border-green-700" :
    score >= 55 ? "bg-yellow-900/50 text-yellow-400 border-yellow-700" :
    "bg-red-900/50 text-red-400 border-red-700";
  return (
    <span className={`inline-flex items-center border rounded px-1.5 py-0.5 text-xs font-bold ${color}`}>
      {score}
    </span>
  );
}

function ProbBar({ pct }: { pct: number }) {
  const color =
    pct >= 40 ? "bg-green-500" :
    pct >= 20 ? "bg-yellow-500" :
    "bg-red-500";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="text-xs text-gray-300 tabular-nums">{pct}%</span>
    </div>
  );
}

export function OptionsReturnTable({ symbol }: { symbol: string }) {
  const [data, setData] = useState<OptimizerData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gainTarget, setGainTarget] = useState<GainTarget>("30");
  const [showOnlyRecommended, setShowOnlyRecommended] = useState(false);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/analysis/${symbol}/optimizer`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [symbol]);

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6">
        <div className="flex items-center gap-2 text-gray-400 text-sm">
          <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
          Computing options return scenarios...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 text-red-400 text-sm">
        Failed to load optimizer data.
      </div>
    );
  }

  const displayRows = showOnlyRecommended
    ? data.rows.filter(r => r.recommended)
    : data.rows;

  const recommendedCount = data.rows.filter(r => r.recommended).length;

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-700">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Target className="w-5 h-5 text-blue-400" />
            <div>
              <h3 className="text-white font-semibold text-sm">Options Return Optimizer</h3>
              <p className="text-gray-400 text-xs">
                Current: <span className="text-white font-medium">${data.current_price.toFixed(2)}</span>
                &nbsp;·&nbsp;IV: <span className={data.iv_vs_hv === "rich" ? "text-orange-400" : "text-green-400"}>
                  {data.iv_pct}th pct ({data.iv_vs_hv})
                </span>
                &nbsp;·&nbsp;HV20: <span className="text-gray-300">{data.hv20_pct}%</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Gain target toggle */}
            <div className="bg-gray-800 rounded-lg p-0.5 flex">
              {(["30", "100"] as GainTarget[]).map(t => (
                <button
                  key={t}
                  onClick={() => setGainTarget(t)}
                  className={`px-3 py-1 rounded text-xs font-semibold transition ${
                    gainTarget === t
                      ? "bg-blue-600 text-white"
                      : "text-gray-400 hover:text-gray-200"
                  }`}
                >
                  +{t}% Target
                </button>
              ))}
            </div>

            {recommendedCount > 0 && (
              <button
                onClick={() => setShowOnlyRecommended(v => !v)}
                className={`px-3 py-1 rounded text-xs font-semibold border transition ${
                  showOnlyRecommended
                    ? "bg-emerald-900/50 border-emerald-600 text-emerald-400"
                    : "border-gray-600 text-gray-400 hover:text-gray-200"
                }`}
              >
                ⭐ Best ({recommendedCount})
              </button>
            )}
          </div>
        </div>

        {/* IV note */}
        <div className="mt-3 text-xs text-gray-300 bg-gray-800/50 rounded-lg px-3 py-2">
          {data.note}
        </div>
      </div>

      {/* Indicators legend */}
      <div className="px-5 py-3 border-b border-gray-800 bg-gray-900/50">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500">
          <span><span className="text-gray-300 font-medium">Conf</span> = Confidence score (trend + IV rank + DTE + delta + probability)</span>
          <span><span className="text-gray-300 font-medium">Prob</span> = Lognormal probability of stock reaching target price</span>
          <span><span className="text-gray-300 font-medium">Move%</span> = Underlying stock move needed (not option move)</span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
              <th className="px-4 py-3 text-left">Strike / Type</th>
              <th className="px-4 py-3 text-left">Expiry</th>
              <th className="px-4 py-3 text-right">Price</th>
              <th className="px-4 py-3 text-right">Delta</th>
              <th className="px-4 py-3 text-right">
                {gainTarget === "30" ? "Target (30%↑)" : "Target (100%↑)"}
              </th>
              <th className="px-4 py-3 text-right">Move Needed</th>
              <th className="px-4 py-3 text-left">Probability</th>
              <th className="px-4 py-3 text-right">Conf</th>
              <th className="px-4 py-3 text-center">Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {displayRows.map((row, i) => {
              const isCall = row.type === "call";
              const targetPrice = gainTarget === "30" ? row.target_price_30 : row.target_price_100;
              const movePct = gainTarget === "30" ? row.move_pct_30 : row.move_pct_100;
              const prob = gainTarget === "30" ? row.prob_30 : row.prob_100;
              const conf = gainTarget === "30" ? row.conf_30 : row.conf_100;
              const isExpanded = expandedRow === i;

              return (
                <>
                  <tr
                    key={`${row.strike}-${row.expiry}-${row.type}`}
                    onClick={() => setExpandedRow(isExpanded ? null : i)}
                    className={`cursor-pointer transition-colors ${
                      row.recommended
                        ? "bg-emerald-950/20 hover:bg-emerald-950/30"
                        : "hover:bg-gray-800/50"
                    }`}
                  >
                    {/* Strike / Type */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-white font-semibold tabular-nums">${row.strike}</span>
                        <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                          isCall
                            ? "bg-blue-900/40 text-blue-300"
                            : "bg-red-900/40 text-red-300"
                        }`}>
                          {row.type.toUpperCase()}
                        </span>
                      </div>
                    </td>

                    {/* Expiry */}
                    <td className="px-4 py-3">
                      <div className="text-gray-300 tabular-nums">{row.expiry}</div>
                      <div className="text-gray-500 text-xs">{row.dte}d</div>
                    </td>

                    {/* Option Price */}
                    <td className="px-4 py-3 text-right">
                      <div className="text-white font-medium tabular-nums">${row.option_price.toFixed(2)}</div>
                      <div className="text-gray-500 text-xs">IV {row.iv_pct}%</div>
                    </td>

                    {/* Delta */}
                    <td className="px-4 py-3 text-right">
                      <span className={`tabular-nums font-medium ${
                        row.delta >= 0.35 && row.delta <= 0.55
                          ? "text-blue-400"
                          : "text-gray-300"
                      }`}>
                        Δ{row.delta.toFixed(2)}
                      </span>
                    </td>

                    {/* Target price */}
                    <td className="px-4 py-3 text-right">
                      <div className="text-gray-200 tabular-nums">
                        ${targetPrice.toFixed(2)}
                      </div>
                      <div className="text-gray-500 text-xs">
                        stock must reach
                      </div>
                    </td>

                    {/* Move needed */}
                    <td className="px-4 py-3 text-right">
                      <span className={`tabular-nums font-semibold ${
                        movePct <= 5 ? "text-green-400" :
                        movePct <= 10 ? "text-yellow-400" :
                        "text-orange-400"
                      }`}>
                        {movePct.toFixed(1)}%
                      </span>
                    </td>

                    {/* Probability bar */}
                    <td className="px-4 py-3">
                      <ProbBar pct={prob} />
                    </td>

                    {/* Confidence */}
                    <td className="px-4 py-3 text-right">
                      <ConfBadge score={conf} />
                    </td>

                    {/* Flag */}
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        {row.recommended && (
                          <span title="Recommended">⭐</span>
                        )}
                        {isExpanded ? (
                          <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
                        )}
                      </div>
                    </td>
                  </tr>

                  {/* Expanded rationale row */}
                  {isExpanded && (
                    <tr key={`${row.strike}-${row.expiry}-expanded`} className="bg-gray-800/40">
                      <td colSpan={9} className="px-6 py-3">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                          <div>
                            <div className="text-gray-500 mb-1">30% Gain Scenario</div>
                            <div className="text-gray-200">Stock → <span className="text-green-400 font-medium">${row.target_price_30.toFixed(2)}</span></div>
                            <div className="text-gray-400">{row.move_pct_30.toFixed(1)}% move · {row.prob_30}% prob · conf <strong>{row.conf_30}</strong></div>
                          </div>
                          <div>
                            <div className="text-gray-500 mb-1">100% Gain Scenario</div>
                            <div className="text-gray-200">Stock → <span className="text-blue-400 font-medium">${row.target_price_100.toFixed(2)}</span></div>
                            <div className="text-gray-400">{row.move_pct_100.toFixed(1)}% move · {row.prob_100}% prob · conf <strong>{row.conf_100}</strong></div>
                          </div>
                          <div>
                            <div className="text-gray-500 mb-1">Greeks</div>
                            <div className="text-gray-300">Delta: Δ{row.delta.toFixed(2)} · IV: {row.iv_pct}%</div>
                            <div className="text-gray-400">DTE: {row.dte} days</div>
                          </div>
                          {row.rationale && (
                            <div>
                              <div className="text-gray-500 mb-1">Rationale</div>
                              <div className="text-emerald-300">{row.rationale}</div>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}

            {displayRows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                  No recommended setups found. Try showing all options.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Footer: indicator legend */}
      <div className="px-5 py-4 border-t border-gray-800 bg-gray-900/50">
        <div className="text-xs text-gray-600 font-medium mb-2">Confidence Score Breakdown</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1 text-xs text-gray-500">
          <span>• Trend score (bull/bear conviction) → ±8 pts</span>
          <span>• IV percentile: &lt;35th cheap → +12, &gt;65th rich → -8</span>
          <span>• DTE 14-21 sweet spot → +6 / under 7d → -15</span>
          <span>• Delta 0.35-0.55 ATM → +8 / &lt;0.15 far OTM → -10</span>
          <span>• Lognormal 30% probability → ×0.15 contribution</span>
          <span>• Base: 40 pts · Range: 10-95</span>
        </div>
      </div>
    </div>
  );
}
