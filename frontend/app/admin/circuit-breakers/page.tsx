"use client";

import { useState, useEffect } from "react";
import { ShieldCheck, ShieldAlert, AlertTriangle, CheckCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

interface BreakerStatus {
  halted: boolean;
  active_breakers: string[];
  warnings: string[];
  reason: string;
  kill_switch: { active: boolean; reason: string | null };
  portfolio_snapshot?: {
    portfolio_value: number; daily_pnl: number; daily_pnl_pct: number;
    open_positions: number; max_positions: number; deployed_pct: number;
  };
}

export default function CircuitBreakersPage() {
  const [status, setStatus] = useState<BreakerStatus | null>(null);
  const [toggling, setToggling] = useState(false);
  const [killReason, setKillReason] = useState("Manual override");

  const load = async () => {
    const resp = await fetch(`${API}/admin/circuit-breakers`);
    const data = await resp.json();
    setStatus(data);
  };

  useEffect(() => { load(); }, []);

  const toggleKillSwitch = async (activate: boolean) => {
    setToggling(true);
    await fetch(`${API}/admin/kill-switch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: activate, reason: killReason }),
    });
    await load();
    setToggling(false);
  };

  if (!status) return <div className="p-6 text-gray-500">Loading circuit breaker status...</div>;

  const snap = status.portfolio_snapshot;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        {status.halted
          ? <ShieldAlert className="w-7 h-7 text-red-400" />
          : <ShieldCheck className="w-7 h-7 text-green-400" />}
        <div>
          <h1 className="text-2xl font-bold text-white">Circuit Breakers</h1>
          <p className="text-gray-400 text-sm mt-0.5">
            All new trade requests pass through these gates automatically.
          </p>
        </div>
        <div className={`ml-auto px-4 py-2 rounded-xl font-bold text-sm ${
          status.halted ? "bg-red-900/30 text-red-400 border border-red-700" : "bg-green-900/30 text-green-400 border border-green-700"
        }`}>
          {status.halted ? "🛑 HALTED" : "✅ ACTIVE"}
        </div>
      </div>

      {/* Halt reason */}
      {status.halted && status.reason && (
        <div className="mb-4 bg-red-900/20 border border-red-700/50 rounded-xl p-4 text-red-300 text-sm">
          <div className="font-bold mb-1 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Halt Reason</div>
          {status.reason}
        </div>
      )}

      {/* Warnings */}
      {status.warnings.length > 0 && (
        <div className="mb-4 space-y-2">
          {status.warnings.map((w, i) => (
            <div key={i} className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg px-4 py-2 text-yellow-300 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />{w}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Active breakers */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="text-gray-200 font-semibold text-sm mb-3">Breaker Status</div>
          {[
            { id: "KILL_SWITCH", label: "Kill Switch", desc: "Manual override" },
            { id: "DAILY_LOSS_CAP", label: "Daily Loss Cap", desc: "5% of portfolio" },
            { id: "MAX_DRAWDOWN", label: "Max Drawdown", desc: "15% from peak" },
            { id: "POSITION_LIMIT", label: "Position Limit", desc: "Max 10 concurrent" },
          ].map(b => {
            const active = status.active_breakers.includes(b.id);
            return (
              <div key={b.id} className={`flex items-center gap-3 py-2 border-b border-gray-800/50 last:border-0 ${active ? "opacity-100" : "opacity-60"}`}>
                {active
                  ? <ShieldAlert className="w-4 h-4 text-red-400 flex-shrink-0" />
                  : <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />}
                <div className="flex-1">
                  <div className={`text-sm font-medium ${active ? "text-red-300" : "text-gray-300"}`}>{b.label}</div>
                  <div className="text-gray-500 text-xs">{b.desc}</div>
                </div>
                <span className={`text-xs font-bold ${active ? "text-red-400" : "text-green-400"}`}>
                  {active ? "TRIGGERED" : "OK"}
                </span>
              </div>
            );
          })}
        </div>

        {/* Portfolio snapshot */}
        {snap && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="text-gray-200 font-semibold text-sm mb-3">Portfolio Snapshot</div>
            <div className="space-y-2">
              <SnapRow label="Portfolio Value" value={`$${snap.portfolio_value.toLocaleString()}`} />
              <SnapRow label="Daily P&L" value={`${snap.daily_pnl >= 0 ? "+" : ""}$${snap.daily_pnl.toLocaleString()} (${snap.daily_pnl_pct >= 0 ? "+" : ""}${snap.daily_pnl_pct.toFixed(2)}%)`}
                color={snap.daily_pnl >= 0 ? "text-green-400" : "text-red-400"} />
              <SnapRow label="Open Positions" value={`${snap.open_positions} / ${snap.max_positions}`} />
              <SnapRow label="Capital Deployed" value={`${snap.deployed_pct.toFixed(1)}%`}
                color={snap.deployed_pct > 25 ? "text-yellow-400" : "text-green-400"} />
            </div>
          </div>
        )}
      </div>

      {/* Kill switch control */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="text-gray-200 font-semibold text-sm mb-3">Manual Kill Switch</div>
        <p className="text-gray-400 text-xs mb-4">
          Immediately halts all new trade approvals. Use if you see anomalous behavior or need to step away.
          Persists for 24h; you must manually deactivate.
        </p>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="text-gray-500 text-xs block mb-1">Reason</label>
            <input
              value={killReason}
              onChange={e => setKillReason(e.target.value)}
              className="bg-gray-800 border border-gray-700 text-white rounded px-3 py-2 text-sm w-full"
            />
          </div>
          {status.kill_switch.active ? (
            <button onClick={() => toggleKillSwitch(false)} disabled={toggling}
              className="bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
              {toggling ? "Deactivating..." : "Resume Trading"}
            </button>
          ) : (
            <button onClick={() => toggleKillSwitch(true)} disabled={toggling}
              className="bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
              {toggling ? "Activating..." : "Activate Kill Switch"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function SnapRow({ label, value, color = "text-white" }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-gray-400">{label}</span>
      <span className={`font-medium ${color}`}>{value}</span>
    </div>
  );
}
