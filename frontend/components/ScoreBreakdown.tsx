"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

interface CategoryScore {
  name: string;
  weight: number;
  raw_score: number;
  weighted_score: number;
  direction: string;
  signals: Array<{ name: string; value?: unknown; direction?: string; note?: string }>;
  summary: string;
}

interface Props {
  categoryScores: Record<string, CategoryScore>;
}

const CATEGORY_LABELS: Record<string, string> = {
  macro: "Market & Macro",
  calendar: "Seasonality",
  fundamental: "Fundamental",
  trend: "Trend",
  support_resistance: "Support/Resistance",
  candles: "Candlesticks",
  chart_patterns: "Chart Patterns",
  momentum: "Momentum",
  iv_analysis: "IV & Volatility",
  options_chain: "Options Chain",
  greeks: "Greeks",
  trade_structure: "Trade Structure",
  sentiment: "Sentiment",
  liquidity: "Liquidity",
  risk: "Risk Mgmt",
  gex_dex: "GEX/DEX",
  options_flow: "Inst. Flow",
  volatility_regime: "Vol Regime",
  earnings_adj_iv: "Earnings IV",
};

export function ScoreBreakdown({ categoryScores }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const sorted = Object.entries(categoryScores).sort(
    ([, a], [, b]) => (b.weight * b.raw_score) - (a.weight * a.raw_score)
  );

  if (sorted.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center text-gray-500">
        Run analysis to see 20-category score breakdown
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <h3 className="text-white font-semibold">20-Category Score Breakdown</h3>
        <div className="text-gray-400 text-xs">{sorted.length} categories</div>
      </div>
      <div className="divide-y divide-gray-800">
        {sorted.map(([key, cat]) => (
          <CategoryCard
            key={key}
            catKey={key}
            cat={cat}
            isExpanded={expanded === key}
            onToggle={() => setExpanded(prev => prev === key ? null : key)}
          />
        ))}
      </div>
    </div>
  );
}

function CategoryCard({
  catKey, cat, isExpanded, onToggle,
}: {
  catKey: string;
  cat: CategoryScore;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const score = cat.raw_score;
  const barColor = score >= 7 ? "bg-green-500" : score >= 5 ? "bg-yellow-500" : "bg-red-500";
  const dirColor = {
    bullish: "text-green-400",
    bearish: "text-red-400",
    neutral: "text-gray-400",
  }[cat.direction] || "text-gray-400";

  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-800/50 transition text-left"
      >
        <div className="w-36 text-gray-300 text-sm font-medium">
          {CATEGORY_LABELS[catKey] || catKey}
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-gray-800 rounded-full h-1.5">
              <div
                className={`${barColor} h-1.5 rounded-full transition-all`}
                style={{ width: `${(score / 10) * 100}%` }}
              />
            </div>
            <div className="w-8 text-right text-white text-sm font-mono">{score.toFixed(1)}</div>
          </div>
        </div>

        <div className={`w-16 text-xs font-medium capitalize text-right ${dirColor}`}>
          {cat.direction}
        </div>

        <div className="w-12 text-right text-gray-500 text-xs">{cat.weight}%</div>

        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-gray-500" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-500" />
        )}
      </button>

      {isExpanded && (
        <div className="px-4 pb-4 pt-1 bg-gray-800/20">
          {cat.summary && (
            <p className="text-gray-400 text-xs mb-3">{cat.summary}</p>
          )}
          {cat.signals && cat.signals.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {cat.signals.slice(0, 8).map((sig, i) => (
                <SignalBadge key={i} signal={sig} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SignalBadge({ signal }: { signal: Record<string, unknown> }) {
  const dir = signal.direction as string;
  const cls = dir === "bullish" ? "signal-badge-bullish" :
              dir === "bearish" ? "signal-badge-bearish" : "signal-badge-neutral";

  const label = signal.name as string;
  const val = signal.value !== undefined ? `=${signal.value}` : "";
  const note = signal.note as string | undefined;

  return (
    <span
      className={`${cls} text-xs px-2 py-0.5 rounded-full font-mono`}
      title={note}
    >
      {label}{val}
    </span>
  );
}
