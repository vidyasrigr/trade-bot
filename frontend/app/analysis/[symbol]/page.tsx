"use client";

import { useState, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import { CandlestickChart } from "@/components/CandlestickChart";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { ReasoningStream } from "@/components/ReasoningStream";
import { OptionsChain } from "@/components/OptionsChain";
import { OrderTicket } from "@/components/OrderTicket";
import { OptionsReturnTable } from "@/components/OptionsReturnTable";
import { IndicatorsPanel } from "@/components/IndicatorsPanel";
import { Dna, TrendingUp, AlertTriangle, Zap } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface StockDNA {
  symbol: string;
  earnings_realized_implied_ratio: number;
  earnings_direction_bias_on_beat: number;
  iv_crush_avg_pct: number;
  beat_and_raise_pead_rate: number;
  earnings_events_count: number;
  sell_news_conditions: Record<string, number>;
  post_ath_5d_median_return: number;
  post_ath_20d_median_return: number;
  ath_continuation_rate: number;
  momentum_persistence_days: number;
  volume_leads_price_days: number;
  best_indicator_ic: Record<string, number>;
  semis_cascade_member: boolean;
  hyperscaler_lag_days: number;
  uses_behavioral_twins: boolean;
  twin_symbols: string[];
  data_quality_score: number;
  computed_at: string;
}

interface AnalysisState {
  status: string;
  message: string;
  categoryScores: Record<string, { name: string; weight: number; raw_score: number; weighted_score: number; direction: string; signals: Array<{ name: string; value?: unknown; direction?: string; note?: string }>; summary: string }>;
  analystReports: {
    fundamental: string;
    technical: string;
    volatility: string;
    sentiment: string;
  };
  traderThesis: string;
  riskAssessment: string;
  orderTicket: Record<string, unknown>;
  totalScore: number;
  direction: string;
  convictionScore: number;
  complete: boolean;
}

export default function AnalysisPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const [analysis, setAnalysis] = useState<AnalysisState>({
    status: "idle",
    message: "",
    categoryScores: {},
    analystReports: { fundamental: "", technical: "", volatility: "", sentiment: "" },
    traderThesis: "",
    riskAssessment: "",
    orderTicket: {},
    totalScore: 0,
    direction: "neutral",
    convictionScore: 0,
    complete: false,
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const [dna, setDna] = useState<StockDNA | null>(null);
  const [dnaLoading, setDnaLoading] = useState(false);

  const loadDna = async () => {
    setDnaLoading(true);
    try {
      const resp = await fetch(`${API}/dna/${symbol}`);
      if (resp.ok) setDna(await resp.json());
    } catch {}
    finally { setDnaLoading(false); }
  };

  const startAnalysis = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setIsStreaming(true);
    setAnalysis(prev => ({ ...prev, status: "starting", complete: false, traderThesis: "" }));

    const es = new EventSource(`${API}/analysis/${symbol}`);
    eventSourceRef.current = es;

    es.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setAnalysis(prev => ({ ...prev, status: data.stage, message: data.message || "" }));
    });

    es.addEventListener("analysis_scores", (e) => {
      const data = JSON.parse(e.data);
      setAnalysis(prev => ({
        ...prev,
        categoryScores: data.category_scores || {},
        totalScore: data.total_score || 0,
        direction: data.direction || "neutral",
      }));
    });

    es.addEventListener("analyst_reports", (e) => {
      const data = JSON.parse(e.data);
      setAnalysis(prev => ({ ...prev, analystReports: data }));
    });

    es.addEventListener("trader_thesis", (e) => {
      const data = JSON.parse(e.data);
      setAnalysis(prev => ({ ...prev, traderThesis: data.thesis || "" }));
    });

    es.addEventListener("risk_assessment", (e) => {
      const data = JSON.parse(e.data);
      setAnalysis(prev => ({ ...prev, riskAssessment: data.assessment || "" }));
    });

    es.addEventListener("order_ticket", (e) => {
      const data = JSON.parse(e.data);
      setAnalysis(prev => ({ ...prev, orderTicket: data }));
    });

    es.addEventListener("complete", (e) => {
      const data = JSON.parse(e.data);
      setAnalysis(prev => ({
        ...prev,
        complete: true,
        convictionScore: data.conviction_score || 0,
        status: "complete",
      }));
      setIsStreaming(false);
      es.close();
    });

    es.addEventListener("error", () => {
      setIsStreaming(false);
      es.close();
    });
  };

  useEffect(() => {
    if (symbol) { startAnalysis(); loadDna(); }
    return () => eventSourceRef.current?.close();
  }, [symbol]);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-3xl font-bold text-white">{symbol}</h1>
          <DirectionChip direction={analysis.direction} />
          {analysis.totalScore > 0 && (
            <div className="bg-gray-800 rounded-lg px-3 py-1">
              <span className="text-gray-400 text-xs">Score </span>
              <span className={`font-bold text-lg ${
                analysis.totalScore >= 70 ? "text-green-400" :
                analysis.totalScore >= 50 ? "text-yellow-400" : "text-red-400"
              }`}>{analysis.totalScore.toFixed(1)}</span>
              <span className="text-gray-500 text-xs">/100</span>
            </div>
          )}
          {analysis.convictionScore > 0 && (
            <div className="bg-gray-800 rounded-lg px-3 py-1">
              <span className="text-gray-400 text-xs">Conviction </span>
              <span className="font-bold text-white text-lg">{analysis.convictionScore.toFixed(0)}</span>
            </div>
          )}
        </div>
        <button
          onClick={startAnalysis}
          disabled={isStreaming}
          className="bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition"
        >
          {isStreaming ? `Analyzing... (${analysis.message || analysis.status})` : "Re-Analyze"}
        </button>
      </div>

      {/* Status bar */}
      {isStreaming && (
        <div className="mb-4 bg-blue-900/20 border border-blue-800 rounded-lg px-4 py-2 text-blue-300 text-sm flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
          {analysis.message || "Analyzing..."}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left column: Chart + Scores */}
        <div className="xl:col-span-2 space-y-6">
          <CandlestickChart symbol={symbol} />
          <ScoreBreakdown categoryScores={analysis.categoryScores} />
        </div>

        {/* Right column: AI reasoning + Order ticket */}
        <div className="space-y-4">
          <ReasoningStream
            analystReports={analysis.analystReports}
            traderThesis={analysis.traderThesis}
            riskAssessment={analysis.riskAssessment}
            isStreaming={isStreaming}
          />

          {analysis.orderTicket && Object.keys(analysis.orderTicket).length > 0 && (
            <OrderTicket
              ticket={analysis.orderTicket}
              symbol={symbol}
            />
          )}
        </div>
      </div>

      {/* Full-width: Behavioral DNA Panel */}
      <div className="mt-6">
        <DNAPanel dna={dna} loading={dnaLoading} symbol={symbol} />
      </div>

      {/* Full-width: Options Return Optimizer */}
      <div className="mt-6">
        <OptionsReturnTable symbol={symbol} />
      </div>

      {/* Full-width: Indicators Checked panel */}
      <div className="mt-6">
        <IndicatorsPanel />
      </div>
    </div>
  );
}

function DirectionChip({ direction }: { direction: string }) {
  const styles = {
    bullish: "bg-green-900/40 text-green-400 border-green-700",
    bearish: "bg-red-900/40 text-red-400 border-red-700",
    neutral: "bg-gray-800/60 text-gray-400 border-gray-700",
  } as Record<string, string>;
  return (
    <span className={`border rounded-full px-3 py-1 text-sm font-medium capitalize ${styles[direction] || styles.neutral}`}>
      {direction}
    </span>
  );
}

// ---------------------------------------------------------------------------
// DNA Behavioral Profile Panel
// ---------------------------------------------------------------------------

function DNAPanel({ dna, loading, symbol }: { dna: StockDNA | null; loading: boolean; symbol: string }) {
  const [collapsed, setCollapsed] = useState(false);

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4 flex items-center gap-2 text-gray-500 text-sm">
        <div className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
        Loading behavioral DNA for {symbol}...
      </div>
    );
  }

  if (!dna || dna.data_quality_score < 5) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4 text-gray-600 text-sm">
        No behavioral DNA available for {symbol} — nightly batch will compute it overnight.
      </div>
    );
  }

  const directionBias = dna.earnings_direction_bias_on_beat;
  const sellNewsRate = dna.sell_news_conditions?.eps_only_beat_sell_rate;
  const beatRaiseCont = dna.sell_news_conditions?.beat_and_raise_continuation_rate;
  const topIndicators = Object.entries(dna.best_indicator_ic)
    .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
    .slice(0, 4);

  return (
    <div className="bg-gray-900 border border-purple-900/40 rounded-xl overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-3 border-b border-gray-800 cursor-pointer hover:bg-gray-800/30 transition"
        onClick={() => setCollapsed(v => !v)}
      >
        <div className="flex items-center gap-2.5">
          <Dna className="w-4 h-4 text-purple-400" />
          <span className="text-white font-semibold text-sm">{symbol} Behavioral DNA</span>
          <span className={`text-xs px-2 py-0.5 rounded-full border ${
            dna.data_quality_score >= 70 ? "bg-green-900/30 text-green-400 border-green-800" :
            dna.data_quality_score >= 40 ? "bg-yellow-900/30 text-yellow-400 border-yellow-800" :
            "bg-gray-800 text-gray-500 border-gray-700"
          }`}>
            Quality {dna.data_quality_score.toFixed(0)}/100
          </span>
          {dna.uses_behavioral_twins && (
            <span className="text-xs text-gray-500">
              (using {dna.twin_symbols.slice(0, 2).join(", ")} as behavioral twins)
            </span>
          )}
          <span className="text-xs text-gray-600">{dna.earnings_events_count} earnings events</span>
        </div>
        <span className="text-gray-500 text-xs">{collapsed ? "▼ expand" : "▲ collapse"}</span>
      </div>

      {!collapsed && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-0 divide-x divide-gray-800">

          {/* Earnings Behavior */}
          <div className="px-5 py-4 space-y-2">
            <div className="text-gray-400 text-xs font-semibold uppercase tracking-wide mb-3">Earnings Behavior</div>

            <div className="flex justify-between items-center">
              <span className="text-gray-500 text-xs">Beat → up</span>
              <span className={`text-sm font-bold ${
                directionBias >= 0.60 ? "text-green-400" :
                directionBias <= 0.40 ? "text-red-400" : "text-yellow-400"
              }`}>
                {(directionBias * 100).toFixed(0)}%
                {directionBias < 0.45 && <span className="text-xs ml-1 font-normal text-red-400">sell-the-news</span>}
                {directionBias >= 0.60 && <span className="text-xs ml-1 font-normal text-green-400">bullish bias</span>}
              </span>
            </div>

            {dna.earnings_realized_implied_ratio > 0 && (
              <div className="flex justify-between items-center">
                <span className="text-gray-500 text-xs">Realized/Implied</span>
                <span className={`text-sm font-bold ${
                  dna.earnings_realized_implied_ratio < 0.85 ? "text-green-400" :
                  dna.earnings_realized_implied_ratio > 1.15 ? "text-red-400" : "text-gray-300"
                }`}>
                  {dna.earnings_realized_implied_ratio.toFixed(2)}x
                </span>
              </div>
            )}

            {dna.iv_crush_avg_pct > 0 && (
              <div className="flex justify-between items-center">
                <span className="text-gray-500 text-xs">IV crush avg</span>
                <span className={`text-sm font-bold ${dna.iv_crush_avg_pct > 30 ? "text-amber-400" : "text-gray-300"}`}>
                  {(dna.iv_crush_avg_pct * 100).toFixed(0)}%
                </span>
              </div>
            )}

            {dna.beat_and_raise_pead_rate > 0 && (
              <div className="flex justify-between items-center">
                <span className="text-gray-500 text-xs">Beat+raise PEAD</span>
                <span className={`text-sm font-bold ${dna.beat_and_raise_pead_rate >= 0.60 ? "text-green-400" : "text-gray-400"}`}>
                  {(dna.beat_and_raise_pead_rate * 100).toFixed(0)}%
                </span>
              </div>
            )}
          </div>

          {/* Sell-the-News Conditions */}
          <div className="px-5 py-4 space-y-2">
            <div className="text-gray-400 text-xs font-semibold uppercase tracking-wide mb-3">Sell-the-News Risk</div>

            {sellNewsRate !== undefined ? (
              <div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-500 text-xs">EPS-only beat sells off</span>
                  <span className={`text-sm font-bold ${sellNewsRate >= 0.60 ? "text-red-400" : sellNewsRate >= 0.45 ? "text-yellow-400" : "text-green-400"}`}>
                    {(sellNewsRate * 100).toFixed(0)}%
                  </span>
                </div>
                {sellNewsRate >= 0.60 && (
                  <div className="mt-1 flex items-center gap-1 text-xs text-red-400">
                    <AlertTriangle className="w-3 h-3" />
                    Avoid naked long calls into earnings
                  </div>
                )}
              </div>
            ) : (
              <div className="text-gray-600 text-xs">Insufficient data</div>
            )}

            {beatRaiseCont !== undefined && (
              <div className="flex justify-between items-center mt-2">
                <span className="text-gray-500 text-xs">Beat+raise continues</span>
                <span className={`text-sm font-bold ${beatRaiseCont >= 0.65 ? "text-green-400" : "text-gray-400"}`}>
                  {(beatRaiseCont * 100).toFixed(0)}%
                </span>
              </div>
            )}

            <div className="mt-3 text-gray-600 text-xs leading-relaxed">
              {directionBias < 0.45
                ? "High sell-the-news risk — use defined-risk spreads or avoid holding calls through earnings."
                : directionBias >= 0.60
                ? "Bullish bias on beats — straddle or long call viable near earnings."
                : "Mixed reaction history — spread positions recommended."}
            </div>
          </div>

          {/* Post-ATH Behavior */}
          <div className="px-5 py-4 space-y-2">
            <div className="text-gray-400 text-xs font-semibold uppercase tracking-wide mb-3">Post-ATH Behavior</div>

            {dna.post_ath_20d_median_return !== 0 ? (
              <>
                <div className="flex justify-between items-center">
                  <span className="text-gray-500 text-xs">5d after ATH</span>
                  <span className={`text-sm font-bold ${dna.post_ath_5d_median_return >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {dna.post_ath_5d_median_return >= 0 ? "+" : ""}{(dna.post_ath_5d_median_return * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-500 text-xs">20d after ATH</span>
                  <span className={`text-sm font-bold ${dna.post_ath_20d_median_return >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {dna.post_ath_20d_median_return >= 0 ? "+" : ""}{(dna.post_ath_20d_median_return * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-500 text-xs">Continuation rate</span>
                  <span className={`text-sm font-bold ${dna.ath_continuation_rate >= 0.55 ? "text-green-400" : "text-red-400"}`}>
                    {(dna.ath_continuation_rate * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-500 text-xs">Momentum persists</span>
                  <span className="text-sm font-bold text-gray-300">{dna.momentum_persistence_days}d</span>
                </div>
              </>
            ) : (
              <div className="text-gray-600 text-xs">Insufficient ATH event data</div>
            )}
          </div>

          {/* Indicators + Cascade */}
          <div className="px-5 py-4 space-y-2">
            <div className="text-gray-400 text-xs font-semibold uppercase tracking-wide mb-3">Best Indicators</div>

            {topIndicators.length > 0 ? (
              <div className="space-y-1.5">
                {topIndicators.map(([indicator, ic]) => (
                  <div key={indicator} className="flex justify-between items-center">
                    <span className="text-gray-400 text-xs capitalize">{indicator.replace(/_/g, " ")}</span>
                    <div className="flex items-center gap-1.5">
                      <div className="w-14 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${ic > 0 ? "bg-green-500" : "bg-red-500"}`}
                          style={{ width: `${Math.min(Math.abs(ic) * 200, 100)}%` }}
                        />
                      </div>
                      <span className={`text-xs font-mono tabular-nums ${ic > 0.3 ? "text-green-400" : ic > 0.1 ? "text-yellow-400" : "text-gray-500"}`}>
                        {ic > 0 ? "+" : ""}{ic.toFixed(3)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-gray-600 text-xs">IC data not yet available</div>
            )}

            {(dna.semis_cascade_member || dna.hyperscaler_lag_days > 0) && (
              <div className="mt-3 pt-3 border-t border-gray-800 space-y-1.5">
                {dna.semis_cascade_member && (
                  <div className="flex items-center gap-1.5 text-xs text-amber-400">
                    <Zap className="w-3 h-3" />
                    Semis cascade member
                  </div>
                )}
                {dna.hyperscaler_lag_days > 0 && (
                  <div className="flex items-center gap-1.5 text-xs text-blue-400">
                    <TrendingUp className="w-3 h-3" />
                    Hyperscaler lag: {dna.hyperscaler_lag_days}d
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
