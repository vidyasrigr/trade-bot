"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp, Star, AlertTriangle, ChevronDown, ChevronUp,
  RefreshCw, Upload, Target, Shield, Zap, GitBranch,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface LTScore {
  symbol: string;
  total_score: number;
  tier: "leaps_candidate" | "long" | "neutral" | "blocked";
  valuation_pts: number;
  growth_pts: number;
  quality_pts: number;
  moat_pts: number;
  fcf_yield: number | null;
  peg_ratio: number | null;
  pe_vs_5yr_mean: number | null;
  revenue_acceleration: string;
  gross_margin_trend: string;
  eps_revision_dir: string;
  piotroski: number | null;
  roic: number | null;
  rule_of_40: number | null;
  insider_ownership: number | null;
  accruals_ratio: number | null;
  sell_triggers_active: string[];
  leaps_candidate: boolean;
  covered_call_opportunity: boolean;
  tranche_levels: Record<string, number | null>;
  quality_momentum_tier: number;
  sector_phase_multiplier: number;
  data_confidence: string;
}

interface HoldingRow extends LTScore {
  shares?: number;
  avg_cost_basis?: number;
  error?: string;
}

interface CorrPair {
  symbol1: string;
  symbol2: string;
  correlation: number;
  level: "extreme" | "high" | "moderate";
}

interface CorrelationData {
  symbols: string[];
  matrix: Record<string, Record<string, number | null>>;
  high_correlation_pairs: CorrPair[];
  avg_correlation: number | null;
  warning: string | null;
}

function TierBadge({ tier }: { tier: string }) {
  const map: Record<string, string> = {
    leaps_candidate: "bg-purple-900/50 text-purple-300 border-purple-700",
    long: "bg-green-900/40 text-green-400 border-green-700",
    neutral: "bg-gray-800 text-gray-400 border-gray-600",
    blocked: "bg-red-900/40 text-red-400 border-red-700",
  };
  const labels: Record<string, string> = {
    leaps_candidate: "⭐ LEAPS",
    long: "✓ Long",
    neutral: "Neutral",
    blocked: "⛔ Blocked",
  };
  return (
    <span className={`inline-flex border rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[tier] || map.neutral}`}>
      {labels[tier] || tier}
    </span>
  );
}

function ScoreBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-300 tabular-nums">{value.toFixed(0)}/{max}</span>
    </div>
  );
}

function QualityMomentumBadge({ tier }: { tier: number }) {
  if (tier === 1) return <span className="text-xs text-green-400 font-medium">✅ Full Conviction</span>;
  if (tier === 2) return <span className="text-xs text-yellow-400">⚠ Quality only (half size)</span>;
  if (tier === 3) return <span className="text-xs text-yellow-400">⚠ Momentum only (half size)</span>;
  return <span className="text-xs text-gray-500">No conviction</span>;
}

function LTScoreRow({ lt, showDetails }: { lt: HoldingRow; showDetails: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const hasTriggers = lt.sell_triggers_active && lt.sell_triggers_active.length > 0;

  return (
    <>
      <tr
        onClick={() => setExpanded(v => !v)}
        className={`cursor-pointer transition-colors border-b border-gray-800 ${
          hasTriggers ? "bg-red-950/20 hover:bg-red-950/30" :
          lt.tier === "leaps_candidate" ? "bg-purple-950/20 hover:bg-purple-950/30" :
          lt.tier === "long" ? "bg-green-950/10 hover:bg-green-950/20" :
          "hover:bg-gray-800/50"
        }`}
      >
        {/* Symbol */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-white font-semibold">{lt.symbol}</span>
            <TierBadge tier={lt.tier} />
            {hasTriggers && <AlertTriangle className="w-3.5 h-3.5 text-red-400" />}
          </div>
          {lt.covered_call_opportunity && (
            <div className="text-xs text-amber-400 mt-0.5">💰 CC opportunity</div>
          )}
        </td>

        {/* Total score */}
        <td className="px-4 py-3">
          <div className={`text-2xl font-bold tabular-nums ${
            lt.total_score >= 75 ? "text-green-400" :
            lt.total_score >= 65 ? "text-blue-400" :
            lt.total_score >= 40 ? "text-gray-300" : "text-red-400"
          }`}>
            {lt.total_score?.toFixed(0) ?? "—"}
          </div>
          <div className="text-gray-500 text-xs">/ 100</div>
        </td>

        {/* Layer breakdown */}
        <td className="px-4 py-3 space-y-1">
          <ScoreBar value={lt.valuation_pts ?? 0} max={25} color="bg-blue-500" />
          <ScoreBar value={lt.growth_pts ?? 0} max={30} color="bg-green-500" />
          <ScoreBar value={lt.quality_pts ?? 0} max={25} color="bg-purple-500" />
          <ScoreBar value={lt.moat_pts ?? 0} max={20} color="bg-amber-500" />
        </td>

        {/* Key metrics */}
        <td className="px-4 py-3 text-xs text-gray-400 space-y-0.5">
          {lt.piotroski !== null && <div>F-score: <span className={`font-medium ${lt.piotroski >= 7 ? "text-green-400" : lt.piotroski <= 3 ? "text-red-400" : "text-gray-300"}`}>{lt.piotroski}/9</span></div>}
          {lt.fcf_yield !== null && <div>FCF yield: <span className="text-gray-300">{(lt.fcf_yield * 100).toFixed(1)}%</span></div>}
          {lt.peg_ratio !== null && <div>PEG: <span className={`font-medium ${lt.peg_ratio < 1.5 ? "text-green-400" : lt.peg_ratio > 3 ? "text-red-400" : "text-gray-300"}`}>{lt.peg_ratio?.toFixed(1)}x</span></div>}
        </td>

        {/* Trends */}
        <td className="px-4 py-3 text-xs space-y-0.5">
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500">Rev:</span>
            <span className={
              lt.revenue_acceleration === "accelerating" ? "text-green-400" :
              lt.revenue_acceleration === "decelerating" ? "text-red-400" : "text-gray-400"
            }>{lt.revenue_acceleration}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500">GM:</span>
            <span className={
              lt.gross_margin_trend === "expanding" ? "text-green-400" :
              lt.gross_margin_trend === "compressing" ? "text-red-400" : "text-gray-400"
            }>{lt.gross_margin_trend}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500">EPS rev:</span>
            <span className={
              lt.eps_revision_dir === "up" ? "text-green-400" :
              lt.eps_revision_dir === "down" ? "text-red-400" : "text-gray-400"
            }>{lt.eps_revision_dir === "up" ? "↑" : lt.eps_revision_dir === "down" ? "↓" : "→"}</span>
          </div>
        </td>

        {/* Q/M tier */}
        <td className="px-4 py-3">
          <QualityMomentumBadge tier={lt.quality_momentum_tier ?? 0} />
        </td>

        {/* Expand */}
        <td className="px-4 py-3 text-center">
          {expanded ? <ChevronUp className="w-3.5 h-3.5 text-gray-500" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-500" />}
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className="bg-gray-900/60 border-b border-gray-800">
          <td colSpan={7} className="px-6 py-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">

              {/* Tranche levels */}
              {lt.tranche_levels && Object.keys(lt.tranche_levels).length > 0 && (
                <div>
                  <div className="text-gray-500 font-medium mb-2">Tranche Buy Levels</div>
                  {Object.entries(lt.tranche_levels).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span className={`capitalize ${k === "stop" ? "text-red-400" : "text-gray-400"}`}>{k}</span>
                      <span className={k === "stop" ? "text-red-300 font-medium" : "text-gray-200 font-medium"}>
                        {v !== null ? `$${v?.toFixed(2)}` : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Holdings context */}
              {lt.shares !== undefined && (
                <div>
                  <div className="text-gray-500 font-medium mb-2">Your Position</div>
                  <div className="flex justify-between"><span className="text-gray-400">Shares</span><span className="text-gray-200">{lt.shares}</span></div>
                  {lt.avg_cost_basis && <div className="flex justify-between"><span className="text-gray-400">Avg cost</span><span className="text-gray-200">${lt.avg_cost_basis?.toFixed(2)}</span></div>}
                </div>
              )}

              {/* Additional fundamentals */}
              <div>
                <div className="text-gray-500 font-medium mb-2">Fundamentals</div>
                {lt.roic !== null && <div className="flex justify-between"><span className="text-gray-400">ROIC</span><span className="text-gray-200">{(lt.roic * 100).toFixed(1)}%</span></div>}
                {lt.rule_of_40 !== null && <div className="flex justify-between"><span className="text-gray-400">Rule of 40</span><span className={`font-medium ${(lt.rule_of_40 ?? 0) > 40 ? "text-green-400" : "text-gray-300"}`}>{lt.rule_of_40?.toFixed(0)}</span></div>}
                {lt.insider_ownership !== null && <div className="flex justify-between"><span className="text-gray-400">Insider own.</span><span className="text-gray-200">{((lt.insider_ownership ?? 0) * 100).toFixed(1)}%</span></div>}
                {lt.accruals_ratio !== null && lt.accruals_ratio > 0.05 && (
                  <div className="flex justify-between text-orange-400"><span>⚠ Accruals</span><span>{lt.accruals_ratio?.toFixed(3)}</span></div>
                )}
              </div>

              {/* Sell triggers */}
              <div>
                <div className="text-gray-500 font-medium mb-2">Sell Triggers</div>
                {hasTriggers ? (
                  lt.sell_triggers_active.map(t => (
                    <div key={t} className="text-red-400 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      <span>{t.replace(/_/g, " ")}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-green-400 text-xs">✓ No triggers active</div>
                )}
                {lt.data_confidence && (
                  <div className="mt-2 text-gray-500">
                    Data confidence: <span className={
                      lt.data_confidence === "high" ? "text-green-400" :
                      lt.data_confidence === "medium" ? "text-yellow-400" : "text-gray-400"
                    }>{lt.data_confidence}</span>
                  </div>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Upload modal for Robinhood CSV
// ---------------------------------------------------------------------------
function CsvUploadModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ imported: number; symbols: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);

    try {
      const resp = await fetch(`${API}/api/portfolio/import/robinhood`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Upload failed");
      }
      const data = await resp.json();
      setResult(data);
      onImported();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full">
        <h3 className="text-white font-semibold text-lg mb-1">Import Robinhood Portfolio</h3>
        <p className="text-gray-400 text-sm mb-4">
          Export from Robinhood: <span className="text-gray-300">Account → Reports and Statements → Generate Report → Download CSV</span>
        </p>

        {result ? (
          <div className="space-y-3">
            <div className="bg-green-900/20 border border-green-800 rounded-lg p-3 text-green-300 text-sm">
              ✓ Imported {result.imported} holdings
            </div>
            <div className="text-gray-400 text-xs">{result.symbols.join(", ")}</div>
            <button onClick={onClose} className="w-full bg-gray-800 hover:bg-gray-700 text-white py-2 rounded-lg text-sm">
              Close
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <input
              type="file"
              accept=".csv"
              onChange={e => setFile(e.target.files?.[0] || null)}
              className="w-full text-sm text-gray-400 file:bg-gray-800 file:text-gray-300 file:border-0 file:rounded file:px-3 file:py-1.5 file:cursor-pointer"
            />
            {error && <div className="text-red-400 text-sm">{error}</div>}
            <div className="flex gap-2">
              <button
                onClick={handleUpload}
                disabled={!file || loading}
                className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white py-2 rounded-lg text-sm"
              >
                {loading ? "Uploading..." : "Import"}
              </button>
              <button onClick={onClose} className="flex-1 bg-gray-800 hover:bg-gray-700 text-white py-2 rounded-lg text-sm">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
type ActiveTab = "portfolio" | "opportunities" | "all";

export default function LongTermPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("portfolio");
  const [portfolio, setPortfolio] = useState<HoldingRow[]>([]);
  const [opportunities, setOpportunities] = useState<{
    leaps_candidates: HoldingRow[];
    long_candidates: HoldingRow[];
    covered_call_opportunities: HoldingRow[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [searchSymbol, setSearchSymbol] = useState("");
  const [lookupResult, setLookupResult] = useState<LTScore | null>(null);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [correlation, setCorrelation] = useState<CorrelationData | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);

  const loadCorrelation = async () => {
    setCorrLoading(true);
    try {
      const resp = await fetch(`${API}/api/lt/correlation`);
      if (resp.ok) setCorrelation(await resp.json());
    } catch {}
    finally { setCorrLoading(false); }
  };

  const loadPortfolio = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${API}/api/lt/portfolio`);
      const data = await resp.json();
      setPortfolio(data.holdings || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadOpportunities = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${API}/api/lt/opportunities`);
      const data = await resp.json();
      setOpportunities(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleLookup = async () => {
    if (!searchSymbol.trim()) return;
    setLookupLoading(true);
    setLookupResult(null);
    try {
      const resp = await fetch(`${API}/api/lt/score/${searchSymbol.trim().toUpperCase()}`);
      const data = await resp.json();
      setLookupResult(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLookupLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "portfolio") { loadPortfolio(); loadCorrelation(); }
    else if (activeTab === "opportunities") loadOpportunities();
  }, [activeTab]);

  const alertCount = portfolio.filter(h => (h.sell_triggers_active?.length ?? 0) > 0).length;

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-3 text-xs">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800/60 pb-2">
        <div className="flex items-center gap-4">
          <span className="text-[10px] tracking-widest uppercase text-gray-600">Long-Term Pipeline</span>
          <span className="text-gray-700 hidden sm:block">Valuation 25 · Growth 30 · Quality 25 · Moat 20</span>
          {alertCount > 0 && (
            <span className="text-red-500 text-[10px]">⚠ {alertCount} sell trigger{alertCount > 1 ? "s" : ""} active</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-1.5 text-gray-600 hover:text-gray-400 border border-gray-800 hover:border-gray-600 rounded px-2 py-1 text-[10px] transition"
          >
            <Upload className="w-3 h-3" /> Import CSV
          </button>
          <button
            onClick={() => activeTab === "portfolio" ? loadPortfolio() : loadOpportunities()}
            className="flex items-center gap-1.5 text-gray-600 hover:text-gray-400 border border-gray-800 hover:border-gray-600 rounded px-2 py-1 text-[10px] transition"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
      </div>

      {/* Quick lookup */}
      <div className="flex items-center gap-2">
        <Target className="w-3 h-3 text-gray-600 flex-shrink-0" />
        <input
          value={searchSymbol}
          onChange={e => setSearchSymbol(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && handleLookup()}
          placeholder="Quick score lookup — type symbol and press Enter"
          className="flex-1 bg-transparent border-b border-gray-800 text-gray-300 text-[11px] placeholder-gray-700 focus:outline-none focus:border-gray-600 py-1 font-mono max-w-sm"
        />
        <button
          onClick={handleLookup}
          disabled={lookupLoading}
          className="text-gray-600 hover:text-gray-400 text-[10px] border border-gray-800 hover:border-gray-600 rounded px-2 py-0.5 transition disabled:opacity-40"
        >
          {lookupLoading ? "…" : "Score"}
        </button>
        </div>

        {lookupResult && (
          <div className="mt-3 p-3 bg-gray-800/50 rounded-lg">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-white font-bold text-lg">{lookupResult.symbol}</span>
              <span className={`text-2xl font-bold ${
                lookupResult.total_score >= 75 ? "text-green-400" :
                lookupResult.total_score >= 65 ? "text-blue-400" :
                lookupResult.total_score >= 40 ? "text-gray-300" : "text-red-400"
              }`}>{lookupResult.total_score?.toFixed(0)}/100</span>
              <TierBadge tier={lookupResult.tier} />
              {lookupResult.leaps_candidate && <span className="text-purple-300 text-xs">⭐ LEAPS candidate</span>}
              {lookupResult.covered_call_opportunity && <span className="text-amber-300 text-xs">💰 Covered call</span>}
            </div>
            <div className="grid grid-cols-4 gap-3 mt-2 text-xs text-gray-400">
              <div>Valuation: <span className="text-blue-400">{lookupResult.valuation_pts?.toFixed(0)}/25</span></div>
              <div>Growth: <span className="text-green-400">{lookupResult.growth_pts?.toFixed(0)}/30</span></div>
              <div>Quality: <span className="text-purple-400">{lookupResult.quality_pts?.toFixed(0)}/25</span></div>
              <div>Moat: <span className="text-amber-400">{lookupResult.moat_pts?.toFixed(0)}/20</span></div>
            </div>
            {lookupResult.piotroski !== null && (
              <div className="text-xs text-gray-400 mt-1">
                Piotroski: <span className={lookupResult.piotroski >= 7 ? "text-green-400" : lookupResult.piotroski <= 3 ? "text-red-400" : "text-gray-300"}>{lookupResult.piotroski}/9</span>
                {lookupResult.fcf_yield !== null && ` · FCF yield: ${(lookupResult.fcf_yield * 100).toFixed(1)}%`}
                {lookupResult.peg_ratio !== null && ` · PEG: ${lookupResult.peg_ratio?.toFixed(1)}x`}
              </div>
            )}
          </div>
        )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-900 border border-gray-700 rounded-xl p-1 w-fit">
        {[
          { id: "portfolio" as ActiveTab, label: "My Portfolio", icon: Shield },
          { id: "opportunities" as ActiveTab, label: "Opportunities", icon: Zap },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
              activeTab === id
                ? "bg-blue-700 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="bg-gray-900 border border-gray-700 rounded-xl p-8 flex items-center justify-center text-gray-400 gap-2">
          <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
          Loading LT scores...
        </div>
      ) : activeTab === "portfolio" ? (
        <>
          <PortfolioTable holdings={portfolio} />
          {portfolio.length >= 2 && (
            <CorrelationPanel data={correlation} loading={corrLoading} />
          )}
        </>
      ) : (
        <OpportunitiesView data={opportunities} />
      )}

      {showUpload && (
        <CsvUploadModal
          onClose={() => setShowUpload(false)}
          onImported={() => { setShowUpload(false); loadPortfolio(); }}
        />
      )}
    </div>
  );
}

function PortfolioTable({ holdings }: { holdings: HoldingRow[] }) {
  if (holdings.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-8 text-center text-gray-500">
        No holdings yet. Import your Robinhood CSV to get started.
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
              <th className="px-4 py-3 text-left">Symbol</th>
              <th className="px-4 py-3 text-left">LT Score</th>
              <th className="px-4 py-3 text-left">
                <div className="flex flex-col gap-0.5 text-xs">
                  <span>Val / Gro / Qual / Moat</span>
                  <span className="text-gray-600 font-normal">25 / 30 / 25 / 20</span>
                </div>
              </th>
              <th className="px-4 py-3 text-left">Key Metrics</th>
              <th className="px-4 py-3 text-left">Trends</th>
              <th className="px-4 py-3 text-left">Q+M Gate</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {holdings.map(lt => (
              <LTScoreRow key={lt.symbol} lt={lt} showDetails={true} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-5 py-3 border-t border-gray-800 text-xs text-gray-500">
        <span className="text-gray-300">Quality + Momentum gate:</span> Both must confirm for full position size (AQR research).
        Either alone = half position. <span className="text-gray-300">LT score &lt; 40</span> = bullish options blocked.
        <span className="text-gray-300 ml-3">⭐ LEAPS:</span> score &gt;75 + IVR &lt;30.
        <span className="text-gray-300 ml-2">💰 CC:</span> score &gt;65 + IVR &gt;60.
      </div>
    </div>
  );
}

function OpportunitiesView({ data }: {
  data: {
    leaps_candidates: HoldingRow[];
    long_candidates: HoldingRow[];
    covered_call_opportunities: HoldingRow[];
  } | null
}) {
  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* LEAPS Candidates */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Star className="w-4 h-4 text-purple-400" />
          <h3 className="text-white font-semibold">LEAPS Candidates</h3>
          <span className="text-gray-500 text-sm">(LT score &gt;75 + IVR &lt;30 = buy deep ITM call, 18-24 months)</span>
        </div>
        {data.leaps_candidates.length === 0 ? (
          <p className="text-gray-500 text-sm">None currently — waiting for LT score &gt;75 + low IVR confluence.</p>
        ) : (
          <OpportunityTable rows={data.leaps_candidates} />
        )}
      </section>

      {/* Long Candidates */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-green-400" />
          <h3 className="text-white font-semibold">Long Candidates</h3>
          <span className="text-gray-500 text-sm">(LT score 65-75)</span>
        </div>
        {data.long_candidates.length === 0 ? (
          <p className="text-gray-500 text-sm">No long candidates in current scanner universe.</p>
        ) : (
          <OpportunityTable rows={data.long_candidates} />
        )}
      </section>

      {/* Covered Call Opportunities */}
      {data.covered_call_opportunities.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-amber-400">💰</span>
            <h3 className="text-white font-semibold">Covered Call Opportunities</h3>
            <span className="text-gray-500 text-sm">(Portfolio holdings: LT score &gt;65 + IVR &gt;60)</span>
          </div>
          <div className="grid gap-2">
            {data.covered_call_opportunities.map(h => (
              <div key={h.symbol} className="bg-gray-900 border border-amber-800/40 rounded-lg px-4 py-3 flex items-center justify-between">
                <div>
                  <span className="text-white font-semibold">{h.symbol}</span>
                  <span className="text-gray-400 text-sm ml-3">{h.shares} shares @ ${h.avg_cost_basis?.toFixed(2)}</span>
                </div>
                <div className="text-amber-300 text-sm">
                  LT {h.total_score?.toFixed(0)}/100 · Sell 30-45 DTE calls at Δ0.20-0.30
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function OpportunityTable({ rows }: { rows: HoldingRow[] }) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
            <th className="px-4 py-3 text-left">Symbol</th>
            <th className="px-4 py-3 text-left">LT Score</th>
            <th className="px-4 py-3 text-left">Tier</th>
            <th className="px-4 py-3 text-left">Piotroski</th>
            <th className="px-4 py-3 text-left">FCF Yield</th>
            <th className="px-4 py-3 text-left">Revenue</th>
            <th className="px-4 py-3 text-left">Q+M Gate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {rows.map(lt => (
            <tr key={lt.symbol} className="hover:bg-gray-800/50 transition-colors">
              <td className="px-4 py-3 text-white font-semibold">{lt.symbol}</td>
              <td className="px-4 py-3">
                <span className={`font-bold ${lt.total_score >= 75 ? "text-green-400" : "text-blue-400"}`}>
                  {lt.total_score?.toFixed(0)}
                </span>
              </td>
              <td className="px-4 py-3"><TierBadge tier={lt.tier} /></td>
              <td className="px-4 py-3 text-gray-300">{lt.piotroski ?? "—"}/9</td>
              <td className="px-4 py-3 text-gray-300">
                {lt.fcf_yield !== null ? `${(lt.fcf_yield * 100).toFixed(1)}%` : "—"}
              </td>
              <td className="px-4 py-3">
                <span className={
                  lt.revenue_acceleration === "accelerating" ? "text-green-400" :
                  lt.revenue_acceleration === "decelerating" ? "text-red-400" : "text-gray-400"
                }>{lt.revenue_acceleration}</span>
              </td>
              <td className="px-4 py-3"><QualityMomentumBadge tier={lt.quality_momentum_tier ?? 0} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pairwise Correlation Panel
// ---------------------------------------------------------------------------

function corrColor(v: number | null): string {
  if (v === null) return "bg-gray-800 text-gray-600";
  const abs = Math.abs(v);
  if (abs >= 1.0) return "bg-gray-700 text-gray-400";   // diagonal
  if (abs >= 0.85) return "bg-red-900/70 text-red-300";
  if (abs >= 0.75) return "bg-orange-900/60 text-orange-300";
  if (abs >= 0.60) return "bg-yellow-900/40 text-yellow-300";
  if (abs >= 0.30) return "bg-gray-800 text-gray-300";
  return "bg-gray-900 text-gray-500";
}

function CorrelationPanel({ data, loading }: { data: CorrelationData | null; loading: boolean }) {
  const [collapsed, setCollapsed] = useState(false);

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4 flex items-center gap-2 text-gray-500 text-sm">
        <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
        Computing 60-day pairwise correlations...
      </div>
    );
  }

  if (!data || data.symbols.length < 2) return null;

  const avgCorr = data.avg_correlation;
  const isHealthy = avgCorr !== null && avgCorr <= 0.55;
  const extremePairs = data.high_correlation_pairs.filter(p => p.level === "extreme" || p.level === "high");

  return (
    <div className={`bg-gray-900 rounded-xl overflow-hidden border ${
      data.warning ? "border-orange-800/60" : "border-gray-800"
    }`}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-3 border-b border-gray-800 cursor-pointer hover:bg-gray-800/30 transition"
        onClick={() => setCollapsed(v => !v)}
      >
        <div className="flex items-center gap-2.5">
          <GitBranch className="w-4 h-4 text-blue-400" />
          <span className="text-white font-semibold text-sm">Portfolio Correlation (60-day)</span>
          {avgCorr !== null && (
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
              isHealthy
                ? "bg-green-900/30 text-green-400 border-green-800"
                : "bg-orange-900/30 text-orange-400 border-orange-800"
            }`}>
              Avg {(avgCorr * 100).toFixed(0)}% {isHealthy ? "✓ healthy" : "⚠ high"}
            </span>
          )}
          {extremePairs.length > 0 && (
            <span className="text-xs text-red-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              {extremePairs.length} high-corr pair{extremePairs.length > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <span className="text-gray-500 text-xs">{collapsed ? "▼ expand" : "▲ collapse"}</span>
      </div>

      {!collapsed && (
        <div className="p-5 space-y-5">
          {/* Warning banner */}
          {data.warning && (
            <div className="bg-orange-900/20 border border-orange-800/50 rounded-lg px-4 py-2.5 text-orange-300 text-sm flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              {data.warning}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Correlation heatmap matrix */}
            {data.symbols.length <= 10 && (
              <div>
                <div className="text-gray-500 text-xs font-medium mb-2 uppercase tracking-wide">Correlation Matrix</div>
                <div className="overflow-x-auto">
                  <table className="text-xs font-mono">
                    <thead>
                      <tr>
                        <th className="w-16" />
                        {data.symbols.map(s => (
                          <th key={s} className="px-1.5 py-1 text-gray-400 font-medium text-center">{s}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.symbols.map(s1 => (
                        <tr key={s1}>
                          <td className="px-2 py-1 text-gray-400 font-medium text-right pr-3">{s1}</td>
                          {data.symbols.map(s2 => {
                            const v = data.matrix[s1]?.[s2] ?? null;
                            return (
                              <td
                                key={s2}
                                className={`px-1.5 py-1 text-center rounded tabular-nums ${corrColor(s1 === s2 ? 1 : v)}`}
                                title={`${s1}/${s2}: ${v?.toFixed(3) ?? "N/A"}`}
                              >
                                {s1 === s2 ? "—" : v !== null ? v.toFixed(2) : "N/A"}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex gap-3 mt-2 text-xs text-gray-600">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-red-900/70 inline-block" />≥0.85</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-orange-900/60 inline-block" />≥0.75</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-yellow-900/40 inline-block" />≥0.60</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-gray-800 inline-block" />lower</span>
                </div>
              </div>
            )}

            {/* Flagged pairs */}
            <div>
              <div className="text-gray-500 text-xs font-medium mb-2 uppercase tracking-wide">
                Flagged Pairs {data.high_correlation_pairs.length > 0 ? `(${data.high_correlation_pairs.length})` : ""}
              </div>
              {data.high_correlation_pairs.length === 0 ? (
                <div className="text-green-400 text-sm flex items-center gap-1.5">
                  ✓ No pairs above 0.60 — portfolio is well-diversified
                </div>
              ) : (
                <div className="space-y-2">
                  {data.high_correlation_pairs.map((p, i) => (
                    <div key={i} className={`flex items-center justify-between rounded-lg px-3 py-2 border ${
                      p.level === "extreme" ? "bg-red-900/20 border-red-800/50" :
                      p.level === "high" ? "bg-orange-900/20 border-orange-800/40" :
                      "bg-yellow-900/10 border-yellow-800/30"
                    }`}>
                      <div className="flex items-center gap-2">
                        <span className="text-white font-semibold text-sm">{p.symbol1}</span>
                        <span className="text-gray-500 text-xs">↔</span>
                        <span className="text-white font-semibold text-sm">{p.symbol2}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${
                          p.level === "extreme" ? "bg-red-900/30 text-red-400 border-red-800" :
                          p.level === "high" ? "bg-orange-900/30 text-orange-400 border-orange-800" :
                          "bg-yellow-900/20 text-yellow-400 border-yellow-800"
                        }`}>{p.level}</span>
                      </div>
                      <div className="text-right">
                        <div className={`font-bold text-sm ${
                          p.level === "extreme" ? "text-red-400" :
                          p.level === "high" ? "text-orange-400" : "text-yellow-400"
                        }`}>{(p.correlation * 100).toFixed(0)}%</div>
                        {p.level === "extreme" && (
                          <div className="text-xs text-red-500">−40% size rec.</div>
                        )}
                        {p.level === "high" && (
                          <div className="text-xs text-orange-500">reduce one</div>
                        )}
                      </div>
                    </div>
                  ))}
                  <div className="text-gray-600 text-xs mt-1">
                    Pairs &gt;0.75 → consider 40% size haircut on newer position (portfolio construction rule).
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
