"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { RefreshCw, X, ChevronRight } from "lucide-react";

const API      = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const API_ROOT = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace("/api", "");

// ── Types ────────────────────────────────────────────────────────────────────

interface Pick {
  symbol: string; sector?: string; total_score: number; conviction_score: number;
  direction: "bullish" | "bearish" | "neutral"; stream: "alpha" | "income";
  order_ticket?: { strategy?: string; expiry?: string; strike?: number };
  trade_thesis?: string; price?: number; change_pct?: number;
  projected_profit?: number; max_loss?: number;
}
interface LTPick {
  symbol: string; total_score: number; conviction_score?: number; tier?: string;
  leaps_candidate?: boolean; covered_call_flag?: boolean;
  fcf_yield?: number; entry_low?: number; entry_high?: number;
  target_price?: number; stop_price?: number; timeline?: string;
  tranche_levels?: number[]; price?: number; change_pct?: number;
}
interface Holding {
  symbol: string; shares: number; avg_cost_basis?: number;
  current_price?: number; unrealized_pnl?: number; unrealized_pnl_pct?: number;
  lt_score?: number; sell_trigger_active?: boolean;
}
interface Trade {
  id: number; symbol: string; strategy?: string;
  current_pnl?: number; current_pnl_pct?: number;
}

// ── Mock LT data (shown when backend has no LT scores yet) ───────────────────

const MOCK_LT: LTPick[] = [
  {
    symbol: "AVGO", total_score: 72, conviction_score: 68, tier: "long",
    leaps_candidate: true, entry_low: 335, entry_high: 345,
    target_price: 520, stop_price: 295, timeline: "12–18 mo",
    tranche_levels: [345, 335, 320, 305], price: 392, change_pct: 0.1,
  },
  {
    symbol: "MRVL", total_score: 68, conviction_score: 71, tier: "long",
    leaps_candidate: false, entry_low: 78, entry_high: 85,
    target_price: 120, stop_price: 65, timeline: "9–12 mo",
    tranche_levels: [85, 78, 70], price: 91, change_pct: 2.3,
  },
];

// ── Sparkline helpers ─────────────────────────────────────────────────────────

function seededRng(seed: number) {
  let s = seed | 0;
  return () => { s = Math.imul(1664525, s) + 1013904223 | 0; return (s >>> 0) / 4294967296; };
}
function symbolSeed(sym: string) {
  return [...sym].reduce((h, c) => Math.imul(31, h) + c.charCodeAt(0) | 0, 0);
}
function buildSparkPoints(sym: string, changePct: number, w: number, h: number): string {
  const rng   = seededRng(symbolSeed(sym));
  const n     = 24;
  const trend = (changePct / n) * (h * 0.35);
  let   y     = h * 0.5;
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    y = Math.max(3, Math.min(h - 3, y - trend + (rng() - 0.5) * 5));
    pts.push([(i / (n - 1)) * w, y]);
  }
  return pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
}

function Sparkline({ symbol, changePct, w = 80, h = 26 }: {
  symbol: string; changePct?: number; w?: number; h?: number;
}) {
  const pct    = changePct ?? 0;
  const pts    = buildSparkPoints(symbol, pct, w, h);
  const color  = pct >= 0 ? "#4ade80" : "#f87171";
  const fill   = pct >= 0 ? "#4ade8014" : "#f8717114";
  const last   = pts.split(" ").pop()?.split(",") ?? ["0", "0"];
  const fillPt = `${w},${h} 0,${h}`;
  return (
    <svg width={w} height={h} className="flex-shrink-0 overflow-visible">
      <line x1={0} y1={h / 2} x2={w} y2={h / 2}
        stroke="#374151" strokeDasharray="2 2" strokeWidth="0.6" />
      <polygon points={`0,${h/2} ${pts} ${fillPt}`}
        fill={fill} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4"
        strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2" fill={color} />
    </svg>
  );
}

// ── Pill ──────────────────────────────────────────────────────────────────────

function ScorePill({ score, conv }: { score: number; conv?: number }) {
  const color = score >= 70 ? "text-green-400 border-green-800/60"
              : score >= 55 ? "text-yellow-500 border-yellow-800/60"
              : "text-gray-500 border-gray-700";
  return (
    <span className={`inline-flex items-center gap-1 border rounded px-1.5 py-0.5 font-mono text-[10px] ${color}`}>
      {score.toFixed(0)}
      {conv != null && <><span className="opacity-40">|</span><span className="opacity-70">{conv.toFixed(0)}</span></>}
    </span>
  );
}

// ── Direction inline ──────────────────────────────────────────────────────────

function DirSymbol({ d }: { d: string }) {
  return (
    <span className={`text-[9px] ml-1 ${
      d === "bullish" ? "text-green-400" : d === "bearish" ? "text-red-400" : "text-gray-700"
    }`}>
      {d === "bullish" ? "▲" : d === "bearish" ? "▼" : ""}
    </span>
  );
}

// ── Options spread legs builder ───────────────────────────────────────────────

function buildLegs(sym: string, strategy?: string, expiry?: string, strike?: number): string {
  const e = expiry ? expiry.replace("2026-", "Jun").replace(/-/g, "/") : "–";
  const s = strike ?? 0;
  if (!strategy) return "–";
  if (strategy.includes("bull_call") || strategy.includes("bull call"))
    return `+1 ${sym} ${e} $${s}C / -1 ${sym} ${e} $${s + 5}C`;
  if (strategy.includes("bear_put") || strategy.includes("bear put"))
    return `-1 ${sym} ${e} $${s + 5}P / +1 ${sym} ${e} $${s}P`;
  if (strategy.includes("iron_condor") || strategy.includes("iron condor"))
    return `-1 ${sym} ${e} $${s - 5}P / +1 ${sym} ${e} $${s - 10}P / -1 ${sym} ${e} $${s + 5}C / +1 ${sym} ${e} $${s + 10}C`;
  if (strategy.includes("long_call") || strategy.includes("long call"))
    return `+1 ${sym} ${e} $${s}C`;
  if (strategy.includes("long_put") || strategy.includes("long put"))
    return `+1 ${sym} ${e} $${s}P`;
  return `${strategy.replace(/_/g, " ")} · ${e}`;
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [tab, setTab]           = useState<"options" | "lt">("options");
  const [panelOpen, setPanelOpen] = useState(false);

  const [picks, setPicks]       = useState<Pick[]>([]);
  const [ltPicks, setLtPicks]   = useState<LTPick[]>([]);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [trades, setTrades]     = useState<Trade[]>([]);
  const [counts, setCounts]     = useState({ s1: 0, s2: 0, s3: 0 });
  const [scannedAt, setScannedAt] = useState("");
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [loading, setLoading]   = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const h = await fetch(`${API_ROOT}/health`, { signal: AbortSignal.timeout(3000) });
      setBackendUp(h.ok);
    } catch { setBackendUp(false); }

    const [scanRes, ltRes, holdRes, tradeRes] = await Promise.allSettled([
      fetch(`${API}/scanner/results`),
      fetch(`${API}/lt/opportunities`),
      fetch(`${API}/portfolio/holdings`),
      fetch(`${API}/trades/paper?status=open`),
    ]);
    if (scanRes.status === "fulfilled" && scanRes.value.ok) {
      const d = await scanRes.value.json();
      setPicks((d.results || []).slice(0, 12));
      setScannedAt(d.scanned_at || "");
      setCounts(d.stage_counts || { s1: 0, s2: 0, s3: 0 });
    }
    if (ltRes.status === "fulfilled" && ltRes.value.ok) {
      const d = await ltRes.value.json();
      const all = [...(d.leaps_candidates || []), ...(d.long_candidates || [])];
      setLtPicks(all.length > 0 ? all.slice(0, 10) : MOCK_LT);
    } else {
      setLtPicks(MOCK_LT);
    }
    if (holdRes.status === "fulfilled" && holdRes.value.ok) {
      const d = await holdRes.value.json();
      setHoldings(d.holdings || []);
    }
    if (tradeRes.status === "fulfilled" && tradeRes.value.ok) {
      const d = await tradeRes.value.json();
      setTrades((d.trades || []).filter((t: Trade & { status: string }) => t.status === "open"));
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const now = new Date();
  const et  = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const etH = et.getHours() + et.getMinutes() / 60;
  const mkt = now.getDay() >= 1 && now.getDay() <= 5 && etH >= 9.5 && etH < 16;
  const totalPnl = holdings.reduce((s, h) => s + (h.unrealized_pnl ?? 0), 0);

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-300 overflow-hidden text-xs select-none">

      {/* ── Status bar ── */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-gray-800 flex-shrink-0 gap-4">
        <div className="flex items-center gap-4 text-[11px]">
          <span className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${mkt ? "bg-green-400 animate-pulse" : "bg-gray-700"}`} />
            <span className={mkt ? "text-green-400" : "text-gray-600"}>{mkt ? "Market Open" : "Market Closed"}</span>
          </span>
          {counts.s1 > 0 && (
            <span className="text-gray-700 hidden sm:block">
              {counts.s1}<span className="mx-0.5 text-gray-800">›</span>{counts.s2}<span className="mx-0.5 text-gray-800">›</span>{counts.s3}<span className="mx-0.5 text-gray-800">›</span><span className="text-green-500">{picks.length}</span>
            </span>
          )}
          {holdings.length > 0 && (
            <span className={`font-mono hidden md:block ${totalPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
              {totalPnl >= 0 ? "+" : ""}${Math.abs(totalPnl).toLocaleString(undefined, { maximumFractionDigits: 0 })} unrealized
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          {scannedAt && <span className="text-gray-700 hidden sm:block">{new Date(scannedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${backendUp ? "bg-green-600" : backendUp === false ? "bg-red-600 animate-pulse" : "bg-gray-700"}`} />
            <span className="text-gray-700">{backendUp === false ? "offline" : "api"}</span>
          </span>
          <button onClick={load} className="text-gray-700 hover:text-gray-400 transition p-0.5">
            <RefreshCw className="w-3 h-3" />
          </button>
          <button
            onClick={() => setPanelOpen(v => !v)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border transition ${panelOpen ? "border-gray-600 text-gray-300" : "border-gray-800 text-gray-500 hover:border-gray-600 hover:text-gray-300"}`}
          >
            Holdings {holdings.length > 0 && <span className="text-gray-600">{holdings.length}</span>}
            <ChevronRight className={`w-3 h-3 transition-transform ${panelOpen ? "rotate-180" : ""}`} />
          </button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex border-b border-gray-800 flex-shrink-0">
        {(["options", "lt"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-2 text-[11px] tracking-wide transition border-b-2 -mb-px ${
              tab === t
                ? "border-green-500 text-green-400"
                : "border-transparent text-gray-600 hover:text-gray-400"
            }`}
          >
            {t === "options" ? "Options Picks" : "LT & Investments"}
          </button>
        ))}
        {trades.length > 0 && (
          <Link href="/trades"
            className="ml-auto px-4 py-2 text-[11px] text-gray-600 hover:text-gray-400 transition flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            {trades.length} open {trades.length === 1 ? "position" : "positions"}
          </Link>
        )}
      </div>

      {/* ── Content + Holdings panel ── */}
      <div className="flex-1 overflow-hidden flex">

        {/* Main table */}
        <div className="flex-1 overflow-y-auto">
          {tab === "options" ? (
            loading ? <TableSkeleton /> : picks.length === 0
              ? <Empty msg="No scan results yet." sub="Start the backend and run the scanner." href="/scanner" link="Open scanner →" />
              : (
                <table className="w-full">
                  <thead className="sticky top-0 bg-gray-950 z-10 border-b border-gray-800/60">
                    <tr className="text-[10px] text-gray-700 uppercase tracking-widest">
                      <TH w="w-6">#</TH>
                      <TH>Symbol</TH>
                      <TH>Score</TH>
                      <TH>Strategy · Legs</TH>
                      <TH right>Price</TH>
                      <TH w="w-24">Trend</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {picks.map((p, i) => {
                      const legs = buildLegs(p.symbol, p.order_ticket?.strategy, p.order_ticket?.expiry, p.order_ticket?.strike);
                      const expStr = p.order_ticket?.expiry ? `Exp ${p.order_ticket.expiry}` : "";
                      const proj = p.projected_profit;
                      const loss = p.max_loss;
                      return (
                        <tr key={p.symbol} className="border-b border-gray-800/25 hover:bg-gray-800/15 transition group align-top">
                          <TD muted mono>{i + 1}</TD>
                          <TD>
                            <div className="flex items-center gap-0.5">
                              <Link href={`/analysis/${p.symbol}`} className="text-gray-100 font-medium hover:text-white transition">
                                {p.symbol}
                              </Link>
                              <DirSymbol d={p.direction} />
                            </div>
                            <div className="text-gray-700 text-[10px] mt-0.5 flex items-center gap-1.5">
                              <span className={p.stream === "alpha" ? "text-purple-500" : "text-emerald-600"}>
                                {p.stream === "alpha" ? "α" : "$"}
                              </span>
                              {p.sector?.split(" ")[0]}
                            </div>
                          </TD>
                          <TD>
                            <ScorePill score={p.total_score} conv={p.conviction_score} />
                          </TD>
                          <TD>
                            <div className="text-gray-300 text-[11px]">
                              {p.order_ticket?.strategy?.replace(/_/g, " ")}
                              {expStr && <span className="text-gray-600 ml-1.5 font-mono">{expStr}</span>}
                            </div>
                            <div className="text-gray-600 text-[10px] mt-0.5 font-mono truncate max-w-xs">{legs}</div>
                          </TD>
                          <TD right>
                            <div className="font-mono text-gray-200">
                              {p.price != null ? `$${p.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}
                            </div>
                            {p.change_pct != null && (
                              <div className={`font-mono text-[10px] ${p.change_pct >= 0 ? "text-green-500" : "text-red-500"}`}>
                                {p.change_pct >= 0 ? "+" : ""}{p.change_pct.toFixed(1)}%
                              </div>
                            )}
                          </TD>
                          <TD>
                            <Sparkline symbol={p.symbol} changePct={p.change_pct} />
                          </TD>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )
          ) : (
            /* LT Tab */
            loading ? <TableSkeleton /> : (
              <table className="w-full">
                <thead className="sticky top-0 bg-gray-950 z-10 border-b border-gray-800/60">
                  <tr className="text-[10px] text-gray-700 uppercase tracking-widest">
                    <TH w="w-6">#</TH>
                    <TH>Symbol</TH>
                    <TH>Score</TH>
                    <TH>Entry · Target · Stop</TH>
                    <TH>Tranches</TH>
                    <TH>Timeline</TH>
                    <TH right>Price</TH>
                    <TH w="w-24">Trend</TH>
                  </tr>
                </thead>
                <tbody>
                  {ltPicks.map((p, i) => (
                    <tr key={p.symbol} className="border-b border-gray-800/25 hover:bg-gray-800/15 transition group align-top">
                      <TD muted mono>{i + 1}</TD>
                      <TD>
                        <div className="flex items-center gap-0.5">
                          <Link href={`/analysis/${p.symbol}`} className="text-gray-100 font-medium hover:text-white transition">
                            {p.symbol}
                          </Link>
                          {(p.change_pct ?? 0) !== 0 && <DirSymbol d={(p.change_pct ?? 0) >= 0 ? "bullish" : "bearish"} />}
                        </div>
                        <div className="text-gray-700 text-[10px] mt-0.5 flex items-center gap-1.5">
                          {p.leaps_candidate && <span className="text-blue-500">LEAPS</span>}
                          {p.covered_call_flag && <span className="text-amber-500">CC</span>}
                          <span>{p.tier?.replace(/_/g, " ")}</span>
                        </div>
                      </TD>
                      <TD>
                        <ScorePill score={p.total_score} conv={p.conviction_score} />
                      </TD>
                      <TD>
                        <div className="text-[11px] flex items-center gap-1.5 flex-wrap">
                          {p.entry_low != null && (
                            <span>Entry <span className="text-gray-200 font-mono">${p.entry_low}–${p.entry_high}</span></span>
                          )}
                          {p.target_price != null && (
                            <span className="text-green-600">Target <span className="text-green-400 font-mono">${p.target_price}</span></span>
                          )}
                          {p.stop_price != null && (
                            <span className="text-red-700">Stop <span className="text-red-500 font-mono">${p.stop_price}</span></span>
                          )}
                        </div>
                        {p.target_price != null && p.entry_high != null && (
                          <div className="text-[10px] text-gray-600 mt-0.5 font-mono">
                            Upside {(((p.target_price - p.entry_high) / p.entry_high) * 100).toFixed(0)}%
                            {p.leaps_candidate && " · Buy deep ITM call Δ0.70+ 18–24mo out"}
                          </div>
                        )}
                      </TD>
                      <TD>
                        {p.tranche_levels && p.tranche_levels.length > 0 ? (
                          <div className="flex flex-col gap-0.5">
                            {p.tranche_levels.map((lvl, ti) => (
                              <span key={ti} className="text-[10px] font-mono text-gray-500">
                                T{ti + 1} <span className="text-gray-400">${lvl}</span>
                              </span>
                            ))}
                          </div>
                        ) : <span className="text-gray-700">—</span>}
                      </TD>
                      <TD>
                        <span className="text-gray-500">{p.timeline ?? "—"}</span>
                      </TD>
                      <TD right>
                        <div className="font-mono text-gray-200">
                          {p.price != null ? `$${p.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}
                        </div>
                        {p.change_pct != null && (
                          <div className={`font-mono text-[10px] ${p.change_pct >= 0 ? "text-green-500" : "text-red-500"}`}>
                            {p.change_pct >= 0 ? "+" : ""}{p.change_pct.toFixed(1)}%
                          </div>
                        )}
                      </TD>
                      <TD>
                        <Sparkline symbol={p.symbol} changePct={p.change_pct} />
                      </TD>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>

        {/* ── Holdings slide panel ── */}
        <div className={`flex-shrink-0 border-l border-gray-800 bg-gray-950 flex flex-col overflow-hidden transition-all duration-200 ${panelOpen ? "w-72" : "w-0"}`}>
          {panelOpen && (
            <>
              <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800 flex-shrink-0">
                <span className="text-[10px] tracking-widest uppercase text-gray-600">Holdings</span>
                <button onClick={() => setPanelOpen(false)} className="text-gray-700 hover:text-gray-400 transition">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              {holdings.length === 0 ? (
                <div className="px-3 py-4 text-gray-700 text-[11px]">
                  No holdings — import CSV or connect Robinhood.
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto divide-y divide-gray-800/40">
                  {holdings.map(h => {
                    const pnl    = h.unrealized_pnl ?? 0;
                    const pnlPct = h.unrealized_pnl_pct
                      ?? (h.avg_cost_basis && h.current_price
                        ? ((h.current_price - h.avg_cost_basis) / h.avg_cost_basis) * 100
                        : null);
                    const pos    = pnl >= 0;
                    const price  = h.current_price ?? h.avg_cost_basis ?? 0;
                    const value  = price * h.shares;
                    return (
                      <div key={h.symbol} className="flex items-center gap-2 px-3 py-2.5 hover:bg-gray-800/20 transition">
                        <div className="flex-shrink-0 w-14">
                          <div className="flex items-center gap-0.5">
                            <span className="text-gray-100 font-medium text-[12px]">{h.symbol}</span>
                            {h.sell_trigger_active && <span className="text-red-500 text-[9px]">⚠</span>}
                          </div>
                          <div className="text-gray-700 text-[10px]">{h.shares} sh</div>
                        </div>
                        <div className="flex-1">
                          <Sparkline symbol={h.symbol} changePct={pnlPct ?? 0} w={80} h={28} />
                        </div>
                        <div className={`flex-shrink-0 text-right rounded px-2 py-1 font-mono text-[11px] ${
                          pos ? "bg-green-900/40 text-green-400" : "bg-red-900/30 text-red-400"
                        }`}>
                          <div>${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                          {pnlPct != null && (
                            <div className="text-[9px] opacity-75">{pos ? "+" : ""}{pnlPct.toFixed(1)}%</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Paper positions at bottom */}
              {trades.length > 0 && (
                <>
                  <div className="border-t border-gray-800 px-3 py-1.5 flex-shrink-0">
                    <span className="text-[10px] tracking-widest uppercase text-gray-600">Paper Positions</span>
                  </div>
                  <div className="divide-y divide-gray-800/40 overflow-y-auto max-h-40">
                    {trades.map(t => {
                      const pos = (t.current_pnl ?? 0) >= 0;
                      return (
                        <div key={t.id} className="flex items-center justify-between px-3 py-2 hover:bg-gray-800/20 transition">
                          <div>
                            <div className="text-gray-200 font-medium text-[12px]">{t.symbol}</div>
                            <div className="text-gray-700 text-[10px]">{t.strategy?.replace(/_/g, " ")}</div>
                          </div>
                          <div className={`font-mono text-[11px] ${pos ? "text-green-400" : "text-red-400"}`}>
                            {pos ? "+" : ""}${Math.abs(t.current_pnl ?? 0).toFixed(0)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Table helpers ─────────────────────────────────────────────────────────────

function TH({ children, right, w, className = "" }: {
  children?: React.ReactNode; right?: boolean; w?: string; className?: string;
}) {
  return (
    <th className={`px-3 py-2 font-normal text-left ${right ? "text-right" : ""} ${w ?? ""} ${className}`}>
      {children}
    </th>
  );
}

function TD({ children, right, muted, mono, className = "" }: {
  children?: React.ReactNode; right?: boolean; muted?: boolean; mono?: boolean; className?: string;
}) {
  return (
    <td className={`px-3 py-2 ${right ? "text-right" : ""} ${muted ? "text-gray-600" : ""} ${mono ? "font-mono" : ""} ${className}`}>
      {children}
    </td>
  );
}

function TableSkeleton() {
  return (
    <div className="p-4 space-y-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-10 bg-gray-800/40 rounded animate-pulse" style={{ opacity: 1 - i * 0.12 }} />
      ))}
    </div>
  );
}

function Empty({ msg, sub, href, link }: { msg: string; sub?: string; href?: string; link?: string }) {
  return (
    <div className="p-6 text-gray-700">
      <div className="text-[12px]">{msg}</div>
      {sub && <div className="text-[11px] mt-1 text-gray-800">{sub}</div>}
      {href && link && <Link href={href} className="text-blue-800 hover:text-blue-600 text-[11px] mt-2 block">{link}</Link>}
    </div>
  );
}
