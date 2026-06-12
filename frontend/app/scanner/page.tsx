"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { RefreshCw, TrendingUp, TrendingDown, Minus, Zap, Target, DollarSign } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface ScanResult {
  symbol: string;
  name: string;
  sector: string;
  total_score: number;
  conviction_score: number;
  direction: "bullish" | "bearish" | "neutral";
  vol_regime: string;
  iv_percentile: number;
  trade_thesis: string;
  catalyst_flags: Record<string, unknown>;
  stream: "alpha" | "income";
  order_ticket: {
    strategy: string;
    expiry: string;
    strike: number;
  };
  price: number;
  change_pct: number;
}

type StreamFilter = "all" | "alpha" | "income";

export default function ScannerPage() {
  const [results, setResults] = useState<ScanResult[]>([]);
  const [stageCounts, setStageCounts] = useState({ s1: 0, s2: 0, s3: 0 });
  const [scannedAt, setScannedAt] = useState<string>("");
  const [scanning, setScanning] = useState(false);
  const [streamFilter, setStreamFilter] = useState<StreamFilter>("all");

  const fetchResults = async () => {
    const resp = await fetch(`${API}/scanner/results`);
    const data = await resp.json();
    setResults(data.results || []);
    setStageCounts(data.stage_counts || { s1: 0, s2: 0, s3: 0 });
    setScannedAt(data.scanned_at || "");
  };

  const triggerScan = async () => {
    setScanning(true);
    await fetch(`${API}/scanner/run`);
    setTimeout(() => {
      fetchResults();
      setScanning(false);
    }, 5000);
  };

  useEffect(() => { fetchResults(); }, []);

  const filtered = streamFilter === "all" ? results : results.filter(r => r.stream === streamFilter);
  const alphaCount = results.filter(r => r.stream === "alpha").length;
  const incomeCount = results.filter(r => r.stream === "income").length;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Signal Scanner</h1>
          <p className="text-gray-400 text-sm mt-1">
            5-stage funnel: {stageCounts.s1} → {stageCounts.s2} → {stageCounts.s3} → {results.length} setups
            {scannedAt && ` · Scanned ${new Date(scannedAt).toLocaleTimeString()}`}
          </p>
        </div>
        <button
          onClick={triggerScan}
          disabled={scanning}
          className="flex items-center gap-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition"
        >
          <RefreshCw className={`w-4 h-4 ${scanning ? "animate-spin" : ""}`} />
          {scanning ? "Scanning..." : "Run Scan"}
        </button>
      </div>

      {/* Stream filter tabs */}
      <div className="flex gap-2 mb-5">
        <button
          onClick={() => setStreamFilter("all")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
            streamFilter === "all" ? "bg-gray-700 text-white" : "bg-gray-900 text-gray-400 hover:bg-gray-800"
          }`}
        >
          All Setups ({results.length})
        </button>
        <button
          onClick={() => setStreamFilter("alpha")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
            streamFilter === "alpha"
              ? "bg-purple-900 text-purple-200 border border-purple-600"
              : "bg-gray-900 text-gray-400 hover:bg-gray-800 border border-gray-800"
          }`}
        >
          <Target className="w-3.5 h-3.5" />
          Alpha Stream ({alphaCount})
          <span className="text-xs opacity-70">10×–100×</span>
        </button>
        <button
          onClick={() => setStreamFilter("income")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
            streamFilter === "income"
              ? "bg-emerald-900 text-emerald-200 border border-emerald-600"
              : "bg-gray-900 text-gray-400 hover:bg-gray-800 border border-gray-800"
          }`}
        >
          <DollarSign className="w-3.5 h-3.5" />
          Income Stream ({incomeCount})
          <span className="text-xs opacity-70">30–50%/wk</span>
        </button>
      </div>

      {/* Stream description banner */}
      {streamFilter === "alpha" && (
        <div className="mb-4 bg-purple-900/20 border border-purple-700/40 rounded-xl px-4 py-3 text-purple-300 text-sm flex items-center gap-3">
          <Target className="w-4 h-4 flex-shrink-0" />
          <span>
            <strong>Alpha Stream</strong> — High-conviction directional plays targeting 10×–100× returns.
            OTM short-dated options (≤21 DTE, entry ≤$1.00), strong catalyst required. High risk, asymmetric reward.
          </span>
        </div>
      )}
      {streamFilter === "income" && (
        <div className="mb-4 bg-emerald-900/20 border border-emerald-700/40 rounded-xl px-4 py-3 text-emerald-300 text-sm flex items-center gap-3">
          <DollarSign className="w-4 h-4 flex-shrink-0" />
          <span>
            <strong>Income Stream</strong> — Consistent premium collection targeting 30–50%/week.
            Near-ATM spreads and iron condors (≤14 DTE, IV rank ≥50). High probability, defined risk.
          </span>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="text-center py-24 text-gray-500">
          <p className="text-lg">No scan results yet.</p>
          <p className="text-sm mt-2">Click "Run Scan" to start the 5-stage signal funnel.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((r, i) => (
            <Link
              key={r.symbol}
              href={`/analysis/${r.symbol}`}
              className={`block bg-gray-900 rounded-xl p-4 transition cursor-pointer border ${
                r.stream === "alpha"
                  ? "border-purple-900/60 hover:border-purple-700"
                  : "border-emerald-900/50 hover:border-emerald-700"
              }`}
            >
              <div className="flex items-center gap-4">
                <div className="w-6 text-gray-600 font-mono text-sm">#{i + 1}</div>

                {/* Stream badge */}
                <StreamBadge stream={r.stream} />

                {/* Symbol */}
                <div className="w-24">
                  <div className="text-white font-bold text-lg">{r.symbol}</div>
                  <div className="text-gray-500 text-xs">{r.sector}</div>
                </div>

                {/* Score */}
                <div className="w-20">
                  <ScoreBar score={r.total_score} />
                  <div className="text-gray-400 text-xs mt-0.5">score</div>
                </div>

                {/* Direction */}
                <div className="w-16 text-center">
                  <DirectionBadge direction={r.direction} />
                </div>

                {/* IV percentile */}
                <div className="w-16 text-center">
                  <div className={`font-semibold text-sm ${
                    r.iv_percentile >= 60 ? "text-orange-400" : r.iv_percentile >= 40 ? "text-yellow-400" : "text-blue-400"
                  }`}>{r.iv_percentile?.toFixed(0)}%</div>
                  <div className="text-gray-500 text-xs">IV%ile</div>
                </div>

                {/* Price + change */}
                <div className="w-24 hidden md:block">
                  <div className="text-white font-mono text-sm">${r.price?.toLocaleString()}</div>
                  <div className={`text-xs ${r.change_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {r.change_pct >= 0 ? "+" : ""}{r.change_pct?.toFixed(1)}%
                  </div>
                </div>

                {/* Strategy + thesis */}
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-300 truncate">
                    {r.order_ticket?.strategy && (
                      <span className="text-blue-400 font-mono mr-2 text-xs">{r.order_ticket.strategy.replace(/_/g, " ")}</span>
                    )}
                    {r.trade_thesis?.split("\n")[0]?.replace("THESIS:", "").trim()}
                  </div>
                  <div className="text-gray-500 text-xs mt-0.5">
                    Exp {r.order_ticket?.expiry} · ${r.order_ticket?.strike} strike
                  </div>
                </div>

                {/* Catalyst */}
                {r.catalyst_flags && Object.keys(r.catalyst_flags).length > 0 && (
                  <div className="hidden lg:flex items-center gap-1">
                    <Zap className="w-3.5 h-3.5 text-yellow-400" />
                    <span className="text-yellow-400 text-xs">
                      {Object.keys(r.catalyst_flags).slice(0, 2).join(", ").replace(/_/g, " ")}
                    </span>
                  </div>
                )}

                {/* Conviction */}
                <div className="text-right w-16 flex-shrink-0">
                  <div className={`font-bold text-sm ${
                    r.conviction_score >= 80 ? "text-green-400" :
                    r.conviction_score >= 65 ? "text-yellow-400" : "text-gray-400"
                  }`}>{r.conviction_score?.toFixed(0)}</div>
                  <div className="text-gray-500 text-xs">conviction</div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function StreamBadge({ stream }: { stream: "alpha" | "income" }) {
  if (stream === "alpha") return (
    <div className="flex-shrink-0 flex items-center gap-1 bg-purple-900/40 border border-purple-700/50 text-purple-300 px-2 py-1 rounded-lg text-xs font-bold">
      <Target className="w-3 h-3" /> ALPHA
    </div>
  );
  return (
    <div className="flex-shrink-0 flex items-center gap-1 bg-emerald-900/40 border border-emerald-700/50 text-emerald-300 px-2 py-1 rounded-lg text-xs font-bold">
      <DollarSign className="w-3 h-3" /> INCOME
    </div>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score);
  const color = pct >= 70 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div>
      <div className="text-white font-bold text-base">{pct}</div>
      <div className="w-16 h-1.5 bg-gray-800 rounded-full mt-1">
        <div className={`${color} h-1.5 rounded-full`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DirectionBadge({ direction }: { direction: string }) {
  if (direction === "bullish") return (
    <span className="inline-flex items-center gap-1 text-green-400 bg-green-900/30 px-2 py-1 rounded text-xs font-medium">
      <TrendingUp className="w-3 h-3" /> Bull
    </span>
  );
  if (direction === "bearish") return (
    <span className="inline-flex items-center gap-1 text-red-400 bg-red-900/30 px-2 py-1 rounded text-xs font-medium">
      <TrendingDown className="w-3 h-3" /> Bear
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-gray-400 bg-gray-800/50 px-2 py-1 rounded text-xs font-medium">
      <Minus className="w-3 h-3" /> Neutral
    </span>
  );
}
