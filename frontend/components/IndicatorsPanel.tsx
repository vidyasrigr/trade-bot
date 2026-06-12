"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

const INDICATOR_GROUPS = [
  {
    group: "Trend & Structure",
    weight: "18%",
    color: "blue",
    categories: [
      {
        name: "Trend & Market Structure",
        weight: "10%",
        indicators: [
          "EMA 8 / 21 / 50 / 200 alignment",
          "Higher-high / higher-low structure (HH/HL)",
          "Golden cross (50MA > 200MA) / Death cross",
          "Price vs EMA21 (bullish if above)",
          "Trend slope: accelerating vs decelerating",
        ],
      },
      {
        name: "Support & Resistance",
        weight: "8%",
        indicators: [
          "Pivot high / pivot low detection",
          "Fibonacci retracement levels (23.6%, 38.2%, 61.8%)",
          "VWAP (anchor + rolling)",
          "Prior swing highs/lows as S/R",
          "False breakout filter: 2+ closes above resistance + 1.5× volume",
        ],
      },
    ],
  },
  {
    group: "Volatility & Options",
    weight: "30%",
    color: "purple",
    categories: [
      {
        name: "IV & Volatility",
        weight: "12%",
        indicators: [
          "IV Rank (IVR): current IV vs 52-week range",
          "IV Percentile (ORATS-style): % of days IV was lower",
          "IV vs HV20 ratio (rich = IV > HV, cheap = IV < HV)",
          "Earnings-adjusted IV (strips earnings spike)",
          "IV skew: put vs call IV difference",
          "IV term structure: contango vs backwardation",
        ],
      },
      {
        name: "Options Chain Selection",
        weight: "10%",
        indicators: [
          "Open interest by strike (liquidity map)",
          "Bid-ask spread % of mid (gate: <10%)",
          "Strike recommender: 0.35–0.45 Δ directional",
          "DTE selection: 14-21d swing / 30-60d position",
          "Breakeven calculation (premium / delta)",
          "Put/call OI ratio (sentiment)",
        ],
      },
      {
        name: "Greeks",
        weight: "8%",
        indicators: [
          "Delta (directional exposure)",
          "Gamma (rate of delta change — highest near expiry)",
          "Theta (time decay — enemy for buyers)",
          "Vega (sensitivity to IV change)",
          "Delta-adjusted position sizing",
          "Black-Scholes theoretical value vs market price",
        ],
      },
      {
        name: "Volatility Regime",
        weight: "overlay",
        indicators: [
          "VIX level: <15 calm / 15-20 normal / 20-30 elevated / >30 crisis",
          "VIX vs 200-day MA (above = upgrade caution)",
          "VIX front-month backwardation (acute stress flag)",
          "Realized vol 20-day vs 60-day (expanding/contracting)",
          "Regime label: bull_trend / bear_trend / chop / high_vol",
        ],
      },
    ],
  },
  {
    group: "Momentum & Technicals",
    weight: "21%",
    color: "amber",
    categories: [
      {
        name: "Volume & Momentum",
        weight: "7%",
        indicators: [
          "RSI-14 level + crossover signals",
          "RSI crossing 50 from below (bullish momentum flip)",
          "RSI crossing 30 from below (oversold bounce)",
          "MACD line vs signal line crossover",
          "MACD histogram direction (expanding = strengthening)",
          "Bollinger Band squeeze (low volatility before breakout)",
          "ATR-14 (volatility measurement for stop placement)",
          "OBV (On-Balance Volume) trend confirmation",
          "Volume spike: >2× 20-day average = institutional interest",
        ],
      },
      {
        name: "Candlestick Patterns",
        weight: "7%",
        indicators: [
          "Bullish reversal: hammer, morning star, bullish engulfing",
          "Bearish reversal: shooting star, evening star, bearish engulfing",
          "Continuation: marubozu, spinning top in trend",
          "Doji: indecision at key levels",
          "Pin bar: rejection of price level",
        ],
      },
      {
        name: "Chart Patterns",
        weight: "7%",
        indicators: [
          "Bull flag / bear flag (continuation)",
          "Ascending / descending wedge",
          "Head & shoulders / inverse H&S",
          "Cup & handle (accumulation breakout)",
          "Double top / double bottom",
          "Volume must confirm breakout",
        ],
      },
    ],
  },
  {
    group: "Fundamental & Macro",
    weight: "23%",
    color: "green",
    categories: [
      {
        name: "Fundamental & Catalyst",
        weight: "8%",
        indicators: [
          "Earnings date proximity (within 5 days = risk flag)",
          "EPS growth rate (YoY, QoQ)",
          "Revenue growth rate",
          "Analyst price target consensus gap (vs current price)",
          "Recent analyst upgrades/downgrades (TipRanks)",
          "Short interest % of float (high = squeeze potential or trap)",
          "Insider buying activity",
          "Government contract announcements",
        ],
      },
      {
        name: "Market & Macro",
        weight: "8%",
        indicators: [
          "SPY/QQQ trend (market direction)",
          "Sector ETF trend (sector leadership)",
          "VIX regime (macro volatility context)",
          "Yield curve shape (2y-10y spread)",
          "Fed funds rate trajectory",
          "GDP growth momentum",
          "CPI / inflation trend",
          "DXY (dollar strength — inverse to risk assets)",
        ],
      },
      {
        name: "Seasonality & Calendar",
        weight: "7%",
        indicators: [
          "Day-of-week historical bias (Mon bullish / Fri bearish)",
          "Monthly seasonality (options expiry week patterns)",
          "Earnings season (Q1/Q2/Q3/Q4 sector rotation)",
          "OPEX proximity (Vanna/Charm flows on expiry week)",
          "Holiday pre/post effects",
        ],
      },
    ],
  },
  {
    group: "Flow & Sentiment",
    weight: "10%",
    color: "rose",
    categories: [
      {
        name: "Sentiment & Smart Money",
        weight: "5%",
        indicators: [
          "Unusual options activity: volume >150% of 20-day avg",
          "Ask-side prints (aggressor = conviction)",
          "Large premium prints ($50K+ single orders)",
          "Dark pool divergence from options flow",
          "Put/call ratio vs historical norm",
        ],
      },
      {
        name: "GEX / Dealer Flow",
        weight: "overlay",
        indicators: [
          "GEX (Gamma Exposure): positive = dampener, negative = amplifier",
          "DEX (Delta Exposure): net dealer delta position",
          "Vanna flow: vol drop → dealers buy stock",
          "Charm flow: time decay → opening drift on OPEX days",
          "Best for SPX/SPY (78% accuracy). Less reliable on small caps.",
        ],
      },
    ],
  },
  {
    group: "Risk & Execution",
    weight: "~10%",
    color: "gray",
    categories: [
      {
        name: "Liquidity & Execution",
        weight: "5%",
        indicators: [
          "Options bid-ask spread < 10% of mid",
          "Open interest > 500 contracts",
          "Daily options volume > $500K notional",
          "SmartPricing: estimated fill between bid and mid",
        ],
      },
      {
        name: "Risk Management",
        weight: "5%",
        indicators: [
          "Half-Kelly position sizing (0.50× multiplier)",
          "Max position: 4% of portfolio",
          "Portfolio heat: max 30% deployed across all positions",
          "Sector concentration: max 35% in any one sector",
          "Daily loss circuit breaker: halt at -5% portfolio",
          "Max drawdown circuit breaker: halt at -15% from peak",
          "3 independent signal groups required before entry",
          "Stop loss: 50% of debit paid / 2× credit received",
        ],
      },
    ],
  },
];

const COLOR_MAP: Record<string, string> = {
  blue: "border-blue-800 bg-blue-950/20",
  purple: "border-purple-800 bg-purple-950/20",
  amber: "border-amber-800 bg-amber-950/20",
  green: "border-green-800 bg-green-950/20",
  rose: "border-rose-800 bg-rose-950/20",
  gray: "border-gray-700 bg-gray-800/30",
};

const BADGE_MAP: Record<string, string> = {
  blue: "bg-blue-900/50 text-blue-300",
  purple: "bg-purple-900/50 text-purple-300",
  amber: "bg-amber-900/50 text-amber-300",
  green: "bg-green-900/50 text-green-300",
  rose: "bg-rose-900/50 text-rose-300",
  gray: "bg-gray-700/50 text-gray-300",
};

export function IndicatorsPanel() {
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  const toggle = (key: string) =>
    setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }));

  const totalIndicators = INDICATOR_GROUPS.flatMap(g => g.categories).flatMap(c => c.indicators).length;

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
        <div>
          <h3 className="text-white font-semibold text-sm">Indicators Checked Before Entry</h3>
          <p className="text-gray-400 text-xs mt-0.5">
            {INDICATOR_GROUPS.flatMap(g => g.categories).length} categories · {totalIndicators}+ sub-indicators · 3 independent groups required
          </p>
        </div>
      </div>

      <div className="divide-y divide-gray-800">
        {INDICATOR_GROUPS.map((group) => {
          const isOpen = openGroups[group.group] ?? false;
          return (
            <div key={group.group}>
              <button
                onClick={() => toggle(group.group)}
                className="w-full px-5 py-3 flex items-center justify-between hover:bg-gray-800/50 transition"
              >
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${BADGE_MAP[group.color]}`}>
                    {group.weight}
                  </span>
                  <span className="text-gray-200 text-sm font-medium">{group.group}</span>
                  <span className="text-gray-500 text-xs">
                    {group.categories.length} categories
                  </span>
                </div>
                {isOpen ? (
                  <ChevronUp className="w-4 h-4 text-gray-500 flex-shrink-0" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
                )}
              </button>

              {isOpen && (
                <div className={`px-5 pb-4 grid grid-cols-1 md:grid-cols-2 gap-3`}>
                  {group.categories.map((cat) => (
                    <div
                      key={cat.name}
                      className={`border rounded-lg p-3 ${COLOR_MAP[group.color]}`}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-gray-200 text-xs font-semibold">{cat.name}</span>
                        <span className="text-gray-500 text-xs">({cat.weight})</span>
                      </div>
                      <ul className="space-y-1">
                        {cat.indicators.map((ind, j) => (
                          <li key={j} className="text-gray-400 text-xs flex items-start gap-1.5">
                            <span className="text-gray-600 mt-0.5 flex-shrink-0">›</span>
                            {ind}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="px-5 py-3 border-t border-gray-800 bg-gray-900/50">
        <p className="text-xs text-gray-500">
          All signals run through a <span className="text-gray-300">3-independent-group minimum gate</span> before any entry.
          Correlated signals (RSI + MACD + Stochastic) count as <span className="text-gray-300">1 vote</span>, not 3.
          Weights auto-adjust via IC tracker after every closed trade.
        </p>
      </div>
    </div>
  );
}
