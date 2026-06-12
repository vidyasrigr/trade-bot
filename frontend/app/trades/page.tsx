"use client";

import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Trade {
  id: number; symbol: string; strategy: string; direction: string;
  expiry: string; strike: number; contracts: number; entry_price: number;
  exit_price: number | null; realized_pnl: number | null; r_multiple: number | null;
  current_pnl?: number | null; current_pnl_pct?: number | null;
  status: string; opened_at: string; closed_at: string | null;
}

export default function TradesPage() {
  const [trades, setTrades]   = useState<Trade[]>([]);
  const [filter, setFilter]   = useState<"all" | "open" | "closed">("all");
  const [closing, setClosing] = useState<number | null>(null);
  const [exitPrice, setExitPrice] = useState("");

  const load = async () => {
    try {
      const r = await fetch(`${API}/trades/paper?status=${filter}`);
      const d = await r.json();
      setTrades(d.trades || []);
    } catch { /* offline */ }
  };

  useEffect(() => { load(); }, [filter]);

  const close = async (id: number) => {
    await fetch(`${API}/trades/paper/${id}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exit_price: parseFloat(exitPrice), exit_reason: "manual" }),
    });
    setClosing(null); setExitPrice(""); load();
  };

  const open   = trades.filter(t => t.status === "open").length;
  const wins   = trades.filter(t => (t.realized_pnl ?? 0) > 0).length;
  const losses = trades.filter(t => (t.realized_pnl ?? 0) < 0).length;
  const pnl    = trades.reduce((s, t) => s + (t.realized_pnl ?? 0), 0);

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-300 text-xs overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-5 text-[11px]">
          <span className="text-[10px] tracking-widest uppercase text-gray-600">Paper Trades</span>
          <span className="text-gray-600">{open} open</span>
          <span className="text-green-600">{wins}W</span>
          <span className="text-red-600">{losses}L</span>
          <span className={`font-mono ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {pnl >= 0 ? "+" : ""}${Math.abs(pnl).toFixed(0)} total P&amp;L
          </span>
        </div>
        <div className="flex gap-1">
          {(["all", "open", "closed"] as const).map(f => (
            <button key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-0.5 rounded text-[10px] capitalize transition border ${
                filter === f
                  ? "border-gray-600 text-gray-300"
                  : "border-gray-800 text-gray-600 hover:border-gray-700 hover:text-gray-400"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        {trades.length === 0 ? (
          <div className="px-4 py-8 text-gray-700 text-[11px]">
            No trades yet. Approve a setup from the scanner to open a paper trade.
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-gray-950 z-10 border-b border-gray-800/60">
              <tr className="text-[10px] text-gray-700 uppercase tracking-widest">
                <th className="text-left px-4 py-2 font-normal">Symbol</th>
                <th className="text-left px-3 py-2 font-normal">Strategy</th>
                <th className="text-left px-3 py-2 font-normal">Dir</th>
                <th className="text-right px-3 py-2 font-normal">Entry</th>
                <th className="text-right px-3 py-2 font-normal">Strike</th>
                <th className="text-left px-3 py-2 font-normal">Expiry</th>
                <th className="text-right px-3 py-2 font-normal">P&amp;L</th>
                <th className="text-right px-3 py-2 font-normal hidden md:table-cell">R</th>
                <th className="text-left px-3 py-2 font-normal hidden lg:table-cell">Opened</th>
                <th className="px-3 py-2 font-normal w-28"></th>
              </tr>
            </thead>
            <tbody>
              {trades.map(t => {
                const pnlVal = t.realized_pnl ?? t.current_pnl ?? null;
                const pnlPct = t.current_pnl_pct ?? null;
                const pos = (pnlVal ?? 0) >= 0;
                const isClosing = closing === t.id;
                return (
                  <tr key={t.id} className="border-b border-gray-800/30 hover:bg-gray-800/15 transition">
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                          t.status === "open" ? "bg-blue-500" :
                          (t.realized_pnl ?? 0) > 0 ? "bg-green-500" : "bg-red-500"
                        }`} />
                        <span className="text-gray-200 font-medium">{t.symbol}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-gray-500">{t.strategy?.replace(/_/g, " ")}</td>
                    <td className="px-3 py-2">
                      <span className={`font-mono text-[10px] ${
                        t.direction === "bullish" ? "text-green-400" :
                        t.direction === "bearish" ? "text-red-400" : "text-gray-600"
                      }`}>
                        {t.direction === "bullish" ? "▲" : t.direction === "bearish" ? "▼" : "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-500">
                      @{t.entry_price}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-500">
                      ${t.strike}
                    </td>
                    <td className="px-3 py-2 font-mono text-gray-500">{t.expiry}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {pnlVal != null ? (
                        <div>
                          <span className={pos ? "text-green-400" : "text-red-400"}>
                            {pos ? "+" : ""}${Math.abs(pnlVal).toFixed(0)}
                          </span>
                          {pnlPct != null && (
                            <div className={`text-[10px] ${pos ? "text-green-600" : "text-red-600"}`}>
                              {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%
                            </div>
                          )}
                        </div>
                      ) : <span className="text-gray-700">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right font-mono hidden md:table-cell">
                      {t.r_multiple != null ? (
                        <span className={t.r_multiple >= 1 ? "text-green-400" : t.r_multiple > 0 ? "text-gray-400" : "text-red-400"}>
                          {t.r_multiple.toFixed(2)}R
                        </span>
                      ) : <span className="text-gray-700">—</span>}
                    </td>
                    <td className="px-3 py-2 text-gray-700 hidden lg:table-cell font-mono">
                      {t.opened_at ? new Date(t.opened_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-3 py-2">
                      {t.status === "open" && (
                        isClosing ? (
                          <div className="flex items-center gap-1.5">
                            <input
                              type="number" placeholder="exit $"
                              value={exitPrice} onChange={e => setExitPrice(e.target.value)}
                              className="bg-gray-800 border border-gray-700 text-gray-100 rounded px-2 py-0.5 text-[10px] w-16 font-mono focus:outline-none focus:border-gray-600"
                            />
                            <button onClick={() => close(t.id)}
                              className="text-red-500 hover:text-red-400 text-[10px] border border-red-900/50 hover:border-red-700 rounded px-1.5 py-0.5 transition">
                              Close
                            </button>
                            <button onClick={() => setClosing(null)}
                              className="text-gray-700 hover:text-gray-500 text-[10px] transition">✕</button>
                          </div>
                        ) : (
                          <button onClick={() => setClosing(t.id)}
                            className="text-gray-700 hover:text-gray-400 text-[10px] border border-gray-800 hover:border-gray-600 rounded px-2 py-0.5 transition">
                            close
                          </button>
                        )
                      )}
                      {t.status !== "open" && t.closed_at && (
                        <span className="text-gray-700 font-mono text-[10px]">{new Date(t.closed_at).toLocaleDateString()}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
