"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { RefreshCw, Plus, Trash2, Eye, X } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

interface TickerState {
  symbol: string; added_at: string; last_refreshed: string;
  current_score: number; prev_score: number; current_direction: string;
  current_price: number; iv_rank: number; regime: string;
  total_trades: number; win_rate: number; avg_r_multiple: number;
  score_history: { ts: string; score: number }[];
  active_alerts: { type: string; message: string; severity: string }[];
  ticker_lessons: { lesson: string; r_multiple: number; regime: string; date: string }[];
  notes: string;
}

function ScoreSparkline({ history }: { history: { score: number }[] }) {
  if (history.length < 3) return null;
  const vals = history.slice(-16).map(h => h.score);
  const min = Math.min(...vals); const max = Math.max(...vals);
  const range = max - min || 1;
  const w = 56; const h = 16;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * w},${h - ((v - min) / range) * (h - 2) - 1}`).join(" ");
  const last = vals[vals.length - 1];
  const color = last >= 70 ? "#4ade80" : last >= 50 ? "#eab308" : "#f87171";
  return (
    <svg width={w} height={h}><polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" /></svg>
  );
}

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<TickerState[]>([]);
  const [adding, setAdding]       = useState(false);
  const [newSym, setNewSym]       = useState("");
  const [newNote, setNewNote]     = useState("");
  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [selected, setSelected]   = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/watchlist`);
      const d = await r.json();
      setWatchlist(d.watchlist || []);
    } catch { /* backend offline */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!newSym) return;
    await fetch(`${API}/watchlist/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: newSym.toUpperCase(), notes: newNote }),
    });
    setNewSym(""); setNewNote(""); setAdding(false); load();
  };

  const remove = async (sym: string) => {
    await fetch(`${API}/watchlist/${sym}`, { method: "DELETE" });
    if (selected === sym) setSelected(null);
    load();
  };

  const refresh = async (sym: string) => {
    setRefreshing(sym);
    await fetch(`${API}/watchlist/${sym}/refresh`, { method: "POST" });
    await load(); setRefreshing(null);
  };

  const detail = watchlist.find(w => w.symbol === selected);

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-300 text-xs overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 flex-shrink-0">
        <span className="text-[10px] tracking-widest uppercase text-gray-600">
          Watchlist · {watchlist.length} symbols · per-ticker agents, refresh every 30 min
        </span>
        <button
          onClick={() => setAdding(v => !v)}
          className="flex items-center gap-1.5 text-[10px] text-gray-500 hover:text-gray-300 border border-gray-800 hover:border-gray-600 rounded px-2 py-1 transition"
        >
          <Plus className="w-3 h-3" /> Add symbol
        </button>
      </div>

      {/* Add form */}
      {adding && (
        <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-800 bg-gray-900/50 flex-shrink-0">
          <input value={newSym} onChange={e => setNewSym(e.target.value.toUpperCase())}
            placeholder="NVDA" maxLength={8}
            className="bg-gray-800 border border-gray-700 text-gray-100 rounded px-2 py-1 text-xs font-mono w-20 focus:outline-none focus:border-gray-500" />
          <input value={newNote} onChange={e => setNewNote(e.target.value)}
            placeholder="Notes (optional)"
            className="bg-gray-800 border border-gray-700 text-gray-100 rounded px-2 py-1 text-xs flex-1 focus:outline-none focus:border-gray-500" />
          <button onClick={add} className="text-green-500 hover:text-green-400 text-[10px] border border-green-900 hover:border-green-700 rounded px-2 py-1 transition">Add</button>
          <button onClick={() => setAdding(false)} className="text-gray-600 hover:text-gray-400 transition"><X className="w-3 h-3" /></button>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 overflow-hidden flex">

        {/* Table */}
        <div className="flex-1 overflow-y-auto">
          {watchlist.length === 0 ? (
            <div className="px-4 py-8 text-gray-700 text-[11px]">
              No symbols watched yet. Add tickers to monitor with dedicated agents.
            </div>
          ) : (
            <table className="w-full">
              <thead className="sticky top-0 bg-gray-950 z-10 border-b border-gray-800/60">
                <tr className="text-[10px] text-gray-700 uppercase tracking-widest">
                  <th className="text-left px-4 py-2 font-normal">Symbol</th>
                  <th className="text-left px-3 py-2 font-normal">Score</th>
                  <th className="text-left px-3 py-2 font-normal w-16">Trend</th>
                  <th className="text-left px-3 py-2 font-normal">Dir</th>
                  <th className="text-right px-3 py-2 font-normal">Price</th>
                  <th className="text-right px-3 py-2 font-normal">IVR</th>
                  <th className="text-right px-3 py-2 font-normal hidden md:table-cell">WR</th>
                  <th className="text-right px-3 py-2 font-normal hidden md:table-cell">Avg R</th>
                  <th className="text-left px-3 py-2 font-normal hidden lg:table-cell">Alert</th>
                  <th className="px-3 py-2 font-normal w-16"></th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map(t => {
                  const delta = t.current_score - t.prev_score;
                  const isSelected = selected === t.symbol;
                  return (
                    <tr
                      key={t.symbol}
                      onClick={() => setSelected(isSelected ? null : t.symbol)}
                      className={`border-b border-gray-800/30 cursor-pointer transition ${isSelected ? "bg-gray-800/30" : "hover:bg-gray-800/15"}`}
                    >
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1.5">
                          <span className="text-gray-200 font-medium">{t.symbol}</span>
                        </div>
                        <div className="text-gray-700 text-[10px]">{t.regime?.replace(/_/g, " ")}</div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-baseline gap-1">
                          <span className={`font-mono ${t.current_score >= 70 ? "text-green-400" : t.current_score >= 50 ? "text-yellow-500" : "text-red-400"}`}>
                            {t.current_score.toFixed(0)}
                          </span>
                          {t.prev_score > 0 && delta !== 0 && (
                            <span className={`text-[10px] font-mono ${delta > 0 ? "text-green-500" : "text-red-500"}`}>
                              {delta > 0 ? "▲" : "▼"}{Math.abs(delta).toFixed(1)}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <ScoreSparkline history={t.score_history} />
                      </td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] font-mono ${
                          t.current_direction === "bullish" ? "text-green-400" :
                          t.current_direction === "bearish" ? "text-red-400" : "text-gray-600"
                        }`}>
                          {t.current_direction === "bullish" ? "▲" : t.current_direction === "bearish" ? "▼" : "—"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-gray-300">
                        {t.current_price > 0 ? `$${t.current_price.toFixed(2)}` : "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-gray-500">
                        {t.iv_rank > 0 ? `${t.iv_rank.toFixed(0)}%` : "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono hidden md:table-cell">
                        <span className={t.win_rate >= 60 ? "text-green-400" : t.win_rate >= 40 ? "text-yellow-500" : "text-gray-600"}>
                          {t.total_trades > 0 ? `${t.win_rate.toFixed(0)}%` : "—"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono hidden md:table-cell">
                        <span className={t.avg_r_multiple >= 1 ? "text-green-400" : t.avg_r_multiple > 0 ? "text-gray-400" : "text-gray-600"}>
                          {t.total_trades > 0 ? `${t.avg_r_multiple.toFixed(2)}R` : "—"}
                        </span>
                      </td>
                      <td className="px-3 py-2 hidden lg:table-cell">
                        {t.active_alerts[0] && (
                          <span className={`text-[10px] truncate max-w-[160px] block ${
                            t.active_alerts[0].severity === "warning" ? "text-yellow-600" : "text-blue-600"
                          }`}>
                            {t.active_alerts[0].message}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2 justify-end" onClick={e => e.stopPropagation()}>
                          <Link href={`/analysis/${t.symbol}`} className="text-gray-700 hover:text-gray-400 transition" title="Analysis">
                            <Eye className="w-3.5 h-3.5" />
                          </Link>
                          <button onClick={() => refresh(t.symbol)} disabled={refreshing === t.symbol}
                            className="text-gray-700 hover:text-green-500 transition" title="Refresh">
                            <RefreshCw className={`w-3.5 h-3.5 ${refreshing === t.symbol ? "animate-spin" : ""}`} />
                          </button>
                          <button onClick={() => remove(t.symbol)}
                            className="text-gray-700 hover:text-red-500 transition" title="Remove">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Detail panel */}
        {selected && detail && (
          <div className="w-72 border-l border-gray-800 flex flex-col overflow-hidden flex-shrink-0">
            <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800 flex-shrink-0">
              <span className="text-[10px] tracking-widest uppercase text-gray-600">{detail.symbol}</span>
              <div className="flex items-center gap-2">
                <Link href={`/analysis/${detail.symbol}`} className="text-gray-700 hover:text-gray-400 text-[10px] transition">
                  full analysis →
                </Link>
                <button onClick={() => setSelected(null)} className="text-gray-700 hover:text-gray-400 transition">
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
              {/* Stats */}
              <div className="grid grid-cols-3 gap-2">
                {[
                  ["WR", detail.total_trades > 0 ? `${detail.win_rate.toFixed(0)}%` : "—", detail.win_rate >= 60 ? "text-green-400" : "text-gray-400"],
                  ["Avg R", detail.total_trades > 0 ? `${detail.avg_r_multiple.toFixed(2)}R` : "—", detail.avg_r_multiple >= 1 ? "text-green-400" : "text-gray-400"],
                  ["Trades", String(detail.total_trades), "text-gray-400"],
                ].map(([label, val, color]) => (
                  <div key={label}>
                    <div className="text-[10px] text-gray-700 uppercase tracking-wide">{label}</div>
                    <div className={`font-mono text-[12px] ${color}`}>{val}</div>
                  </div>
                ))}
              </div>

              {/* Lessons */}
              {detail.ticker_lessons.length > 0 && (
                <div>
                  <div className="text-[10px] tracking-widest uppercase text-gray-700 mb-1.5">{detail.symbol} Lessons</div>
                  <div className="space-y-2">
                    {detail.ticker_lessons.map((l, i) => (
                      <div key={i} className="text-[10px] text-gray-500 leading-relaxed">
                        <span className={`font-mono mr-1.5 ${l.r_multiple >= 0 ? "text-green-500" : "text-red-500"}`}>
                          {l.r_multiple >= 0 ? "+" : ""}{l.r_multiple.toFixed(2)}R
                        </span>
                        {l.lesson}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Notes */}
              {detail.notes && (
                <div>
                  <div className="text-[10px] tracking-widest uppercase text-gray-700 mb-1">Notes</div>
                  <div className="text-gray-500 text-[11px] leading-relaxed">{detail.notes}</div>
                </div>
              )}

              <div className="text-gray-800 text-[10px]">
                refreshed {detail.last_refreshed ? new Date(detail.last_refreshed).toLocaleTimeString() : "never"}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
