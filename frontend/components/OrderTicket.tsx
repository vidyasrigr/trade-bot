"use client";

import { useState } from "react";
import { CheckCircle, AlertTriangle, ShieldAlert } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface TicketProps {
  ticket: Record<string, unknown>;
  symbol: string;
}

// Multi-leg structure definitions
const MULTI_LEG_STRATEGIES = new Set([
  "bull_call_spread", "bear_put_spread", "bull_put_spread", "bear_call_spread",
  "iron_condor", "iron_butterfly", "calendar_spread", "diagonal_spread",
  "strangle", "straddle",
]);

const STRATEGY_LABELS: Record<string, string> = {
  bull_call_spread: "Bull Call Spread",
  bear_put_spread:  "Bear Put Spread",
  bull_put_spread:  "Bull Put Spread",
  bear_call_spread: "Bear Call Spread",
  iron_condor:      "Iron Condor",
  iron_butterfly:   "Iron Butterfly",
  calendar_spread:  "Calendar Spread",
  long_call:        "Long Call",
  long_put:         "Long Put",
  naked_put:        "Naked Put",
  covered_call:     "Covered Call",
  straddle:         "Straddle",
  strangle:         "Strangle",
};

export function OrderTicket({ ticket, symbol }: TicketProps) {
  const [freshness, setFreshness] = useState<{ valid?: boolean; ok?: boolean; message?: string } | null>(null);
  const [checking, setChecking] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [breakerError, setBreakerError] = useState<string | null>(null);

  const checkFreshness = async () => {
    setChecking(true);
    const resp = await fetch(`${API}/trades/freshness/${symbol}`);
    const data = await resp.json();
    // normalize: backend uses "valid", mock uses "ok"
    setFreshness({ ...data, ok: data.valid ?? data.ok ?? true });
    setChecking(false);
  };

  const openTrade = async () => {
    setBreakerError(null);
    const resp = await fetch(`${API}/trades/paper/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        strategy: ticket.strategy || "long_call",
        direction: ticket.direction || "bullish",
        expiry: ticket.expiry || "",
        strike: ticket.long_strike || ticket.strike || 0,
        option_type: (ticket.direction as string) === "bearish" ? "P" : "C",
        contracts: ticket.suggested_contracts || 1,
        entry_price: ticket.mid || ticket.ask || ticket.bid || 0,
        max_loss: ticket.max_loss || 500,
        max_profit: ticket.max_profit || 1000,
      }),
    });

    if (resp.status === 403) {
      const err = await resp.json();
      setBreakerError(err.detail?.reason || "Circuit breaker active — no new trades allowed");
      return;
    }

    const data = await resp.json();
    if (data.trade_id || data.status === "opened") setSubmitted(true);
  };

  const strategy  = (ticket.strategy as string) || "";
  const direction = (ticket.direction as string) || "";
  const expiry    = ticket.expiry as string;
  const longStrike  = (ticket.long_strike || ticket.strike) as number;
  const shortStrike = ticket.second_strike as number;
  const bid       = ticket.bid as number;
  const ask       = ticket.ask as number;
  const mid       = ticket.mid as number;
  const maxProfit = ticket.max_profit as number;
  const maxLoss   = ticket.max_loss as number;
  const targetDelta = ticket.target_delta as number;
  const contracts = (ticket.suggested_contracts as number) || 1;
  const thesis    = ticket.thesis_summary as string;
  const isMultiLeg = MULTI_LEG_STRATEGIES.has(strategy);

  return (
    <div className="bg-gray-900 border border-green-800/50 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-green-900/20 border-b border-green-800/50 flex items-center justify-between">
        <span className="text-green-400 font-bold text-sm">Order Ticket for N</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          direction === "bullish" ? "bg-green-900/40 text-green-400" :
          direction === "bearish" ? "bg-red-900/40 text-red-400" :
          "bg-gray-800 text-gray-400"
        }`}>{direction || "—"}</span>
      </div>

      <div className="p-4 space-y-3">
        {/* Strategy header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-white font-bold text-base">{symbol}</div>
            <div className="text-blue-400 text-sm font-medium">
              {STRATEGY_LABELS[strategy] || strategy}
            </div>
          </div>
          <div className="text-right">
            <div className="text-gray-400 text-xs">Expiry</div>
            <div className="text-white font-mono text-sm">{expiry || "—"}</div>
          </div>
        </div>

        {/* Multi-leg structure diagram */}
        {isMultiLeg ? (
          <MultiLegDisplay
            strategy={strategy}
            longStrike={longStrike}
            shortStrike={shortStrike}
            direction={direction}
            bid={bid}
            ask={ask}
            mid={mid}
            maxProfit={maxProfit}
            maxLoss={maxLoss}
          />
        ) : (
          /* Single-leg layout */
          <div className="grid grid-cols-3 gap-2">
            <TicketField label="Strike" value={longStrike ? `$${longStrike}` : undefined} mono />
            <TicketField label="Target Δ" value={targetDelta?.toFixed(2)} mono />
            <TicketField label="Contracts" value={contracts} mono />
            {bid && ask && (
              <TicketField label="Bid / Ask" value={`$${bid} / $${ask}`} mono />
            )}
            {mid && <TicketField label="Mid" value={`$${mid}`} mono />}
          </div>
        )}

        {/* Risk/reward summary */}
        {(maxProfit || maxLoss) && (
          <div className="grid grid-cols-3 gap-2 bg-gray-800/50 rounded-lg p-3">
            <div>
              <div className="text-gray-500 text-xs">Max Profit</div>
              <div className="text-green-400 font-bold text-sm">
                {maxProfit ? `$${maxProfit.toLocaleString()}` : "Unlimited"}
              </div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">Max Loss</div>
              <div className="text-red-400 font-bold text-sm">
                {maxLoss ? `$${maxLoss.toLocaleString()}` : "Unlimited"}
              </div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">R/R</div>
              <div className="text-white font-bold text-sm">
                {maxProfit && maxLoss ? `${(maxProfit / maxLoss).toFixed(1)}:1` : "—"}
              </div>
            </div>
          </div>
        )}

        {/* Stream badge + return projection */}
        {ticket.return_projection != null && (
          <ReturnProjectionCard projection={ticket.return_projection as ReturnProjectionData} />
        )}

        {/* Exit rules */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-green-900/15 border border-green-800/40 rounded p-2">
            <div className="text-gray-500 mb-0.5">Take Profit</div>
            <div className="text-green-400 font-medium">50% of max profit</div>
          </div>
          <div className="bg-red-900/15 border border-red-800/40 rounded p-2">
            <div className="text-gray-500 mb-0.5">Stop Loss</div>
            <div className="text-red-400 font-medium">
              {strategy.includes("spread") || strategy === "iron_condor"
                ? "2× credit received"
                : "50% of debit paid"}
            </div>
          </div>
        </div>

        {/* Thesis */}
        {thesis && (
          <div className="bg-gray-800/40 rounded p-3">
            <div className="text-gray-500 text-xs mb-1">Thesis</div>
            <div className="text-gray-300 text-xs leading-relaxed line-clamp-3">{thesis}</div>
          </div>
        )}

        {/* Circuit breaker error */}
        {breakerError && (
          <div className="flex items-start gap-2 bg-red-900/20 border border-red-700/50 rounded p-2 text-red-400 text-xs">
            <ShieldAlert className="w-3 h-3 mt-0.5 flex-shrink-0" />
            <span>{breakerError}</span>
          </div>
        )}

        {/* Freshness indicator */}
        {freshness && (
          <div className={`flex items-center gap-2 text-xs rounded p-2 ${
            freshness.ok ? "bg-green-900/20 text-green-400" : "bg-yellow-900/20 text-yellow-400"
          }`}>
            {freshness.ok
              ? <CheckCircle className="w-3 h-3" />
              : <AlertTriangle className="w-3 h-3" />}
            {freshness.message || (freshness.ok ? "Setup validated" : "Setup may be stale — re-analyze")}
          </div>
        )}

        {/* Actions */}
        {!submitted ? (
          <div className="flex gap-2">
            <button
              onClick={checkFreshness}
              disabled={checking}
              className="flex-1 bg-gray-700 hover:bg-gray-600 text-white text-sm py-2 rounded-lg transition"
            >
              {checking ? "Checking..." : "Validate"}
            </button>
            <button
              onClick={openTrade}
              disabled={freshness?.ok === false}
              className="flex-1 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm py-2 rounded-lg font-semibold transition"
            >
              Open Paper Trade
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2 justify-center text-green-400 text-sm py-2">
            <CheckCircle className="w-4 h-4" />
            Trade logged — tell N to execute
          </div>
        )}
      </div>
    </div>
  );
}

// Multi-leg structure visualizer
function MultiLegDisplay({
  strategy, longStrike, shortStrike, direction,
  bid, ask, mid, maxProfit, maxLoss,
}: {
  strategy: string; longStrike: number; shortStrike: number; direction: string;
  bid: number; ask: number; mid: number; maxProfit: number; maxLoss: number;
}) {
  const legs = buildLegs(strategy, longStrike, shortStrike, direction);

  return (
    <div className="space-y-2">
      <div className="text-gray-500 text-xs font-medium uppercase tracking-wider">Legs</div>
      <div className="space-y-1.5">
        {legs.map((leg, i) => (
          <div key={i} className={`flex items-center justify-between rounded px-3 py-2 text-sm ${
            leg.action === "BUY"
              ? "bg-green-900/20 border border-green-800/40"
              : "bg-red-900/20 border border-red-800/40"
          }`}>
            <div className="flex items-center gap-2">
              <span className={`font-bold w-8 text-xs ${
                leg.action === "BUY" ? "text-green-400" : "text-red-400"
              }`}>{leg.action}</span>
              <span className="text-white font-mono">
                {leg.qty}× {leg.expiry_label} ${leg.strike} {leg.type}
              </span>
            </div>
            <span className="text-gray-400 text-xs font-mono">{leg.price_hint}</span>
          </div>
        ))}
      </div>
      {/* Net debit/credit */}
      <div className="flex items-center justify-between text-xs px-1">
        <span className="text-gray-500">Net {mid > 0 ? "debit" : "credit"}</span>
        <span className={`font-mono font-bold ${mid >= 0 ? "text-red-400" : "text-green-400"}`}>
          {mid ? `$${Math.abs(mid).toFixed(2)}/contract` : "—"}
        </span>
      </div>
    </div>
  );
}

interface LegDef {
  action: "BUY" | "SELL";
  qty: number;
  strike: number;
  type: string;
  expiry_label: string;
  price_hint: string;
}

function buildLegs(strategy: string, longStrike: number, shortStrike: number, direction: string): LegDef[] {
  const exp = "Jun 20";
  const s1 = longStrike || 0;
  const s2 = shortStrike || (s1 ? s1 * 1.04 : 0);

  switch (strategy) {
    case "bull_call_spread":
      return [
        { action: "BUY",  qty: 1, strike: s1, type: "CALL", expiry_label: exp, price_hint: "debit leg" },
        { action: "SELL", qty: 1, strike: s2, type: "CALL", expiry_label: exp, price_hint: "credit leg" },
      ];
    case "bear_put_spread":
      return [
        { action: "BUY",  qty: 1, strike: s2, type: "PUT", expiry_label: exp, price_hint: "debit leg" },
        { action: "SELL", qty: 1, strike: s1, type: "PUT", expiry_label: exp, price_hint: "credit leg" },
      ];
    case "bull_put_spread":
      return [
        { action: "SELL", qty: 1, strike: s2, type: "PUT", expiry_label: exp, price_hint: "credit leg" },
        { action: "BUY",  qty: 1, strike: s1, type: "PUT", expiry_label: exp, price_hint: "hedge leg" },
      ];
    case "bear_call_spread":
      return [
        { action: "SELL", qty: 1, strike: s1, type: "CALL", expiry_label: exp, price_hint: "credit leg" },
        { action: "BUY",  qty: 1, strike: s2, type: "CALL", expiry_label: exp, price_hint: "hedge leg" },
      ];
    case "iron_condor":
      return [
        { action: "SELL", qty: 1, strike: s2, type: "CALL", expiry_label: exp, price_hint: "short call" },
        { action: "BUY",  qty: 1, strike: Math.round(s2 * 1.03), type: "CALL", expiry_label: exp, price_hint: "long call wing" },
        { action: "SELL", qty: 1, strike: s1, type: "PUT",  expiry_label: exp, price_hint: "short put" },
        { action: "BUY",  qty: 1, strike: Math.round(s1 * 0.97), type: "PUT",  expiry_label: exp, price_hint: "long put wing" },
      ];
    case "straddle":
      return [
        { action: "BUY", qty: 1, strike: s1, type: "CALL", expiry_label: exp, price_hint: "call leg" },
        { action: "BUY", qty: 1, strike: s1, type: "PUT",  expiry_label: exp, price_hint: "put leg" },
      ];
    default:
      return [
        { action: "BUY", qty: 1, strike: s1, type: direction === "bearish" ? "PUT" : "CALL",
          expiry_label: exp, price_hint: "single leg" },
      ];
  }
}

// ── Return Projection ─────────────────────────────────────────────────────────

interface ScenarioData {
  name: string;
  underlying_move_pct: number;
  option_price_exit: number;
  return_pct: number;
  probability: number;
}

interface ReturnProjectionData {
  stream: string;
  entry_price: number;
  target_price_10x: number;
  target_price_50pct: number;
  expected_value_pct: number;
  confidence_pct: number;
  stream_rationale: string;
  scenarios: ScenarioData[];
}

function ReturnProjectionCard({ projection }: { projection: ReturnProjectionData }) {
  const isAlpha = projection.stream === "alpha";
  const ev = projection.expected_value_pct;
  const evColor = ev >= 50 ? "text-green-400" : ev >= 0 ? "text-yellow-400" : "text-red-400";

  return (
    <div className={`rounded-lg border p-3 space-y-2.5 ${
      isAlpha
        ? "border-purple-700/50 bg-purple-900/10"
        : "border-blue-700/50 bg-blue-900/10"
    }`}>
      {/* Stream header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
            isAlpha
              ? "bg-purple-900/40 text-purple-300 border border-purple-700/50"
              : "bg-blue-900/40 text-blue-300 border border-blue-700/50"
          }`}>
            {isAlpha ? "🎰 Alpha Stream" : "💰 Income Stream"}
          </span>
        </div>
        <div className="text-right">
          <span className="text-gray-500 text-xs">EV </span>
          <span className={`font-bold text-sm ${evColor}`}>
            {ev >= 0 ? "+" : ""}{ev.toFixed(0)}%
          </span>
          <span className="text-gray-600 text-xs ml-1">@ {projection.confidence_pct.toFixed(0)}% conf</span>
        </div>
      </div>

      {/* Scenarios */}
      <div className="space-y-1">
        {projection.scenarios.map(s => {
          const pctColor = s.return_pct >= 50 ? "text-green-400" : s.return_pct >= 0 ? "text-yellow-400" : "text-red-400";
          const barWidth = Math.min(100, Math.abs(s.probability) * 100);
          return (
            <div key={s.name} className="flex items-center gap-2 text-xs">
              <span className={`w-8 font-medium capitalize ${
                s.name === "bull" ? "text-green-400" : s.name === "bear" ? "text-red-400" : "text-gray-400"
              }`}>{s.name}</span>
              {/* Probability bar */}
              <div className="w-16 h-1.5 bg-gray-800 rounded-full flex-shrink-0">
                <div
                  className={`h-1.5 rounded-full ${
                    s.name === "bull" ? "bg-green-500" : s.name === "bear" ? "bg-red-500" : "bg-yellow-500"
                  }`}
                  style={{ width: `${barWidth}%` }}
                />
              </div>
              <span className="text-gray-500 w-8">{(s.probability * 100).toFixed(0)}%</span>
              <span className="text-gray-400 font-mono w-12">${s.option_price_exit.toFixed(2)}</span>
              <span className={`font-bold font-mono ml-auto ${pctColor}`}>
                {s.return_pct >= 0 ? "+" : ""}{s.return_pct.toFixed(0)}%
              </span>
            </div>
          );
        })}
      </div>

      {/* Target prices */}
      <div className="grid grid-cols-2 gap-2 pt-1 border-t border-gray-800/50">
        <div>
          <div className="text-gray-500 text-xs">10× target price</div>
          <div className="text-purple-300 font-mono font-bold text-sm">${projection.target_price_10x.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-gray-500 text-xs">{isAlpha ? "50% gain" : "30-50%/wk target"}</div>
          <div className="text-blue-300 font-mono font-bold text-sm">${projection.target_price_50pct.toFixed(2)}</div>
        </div>
      </div>
    </div>
  );
}

function TicketField({
  label, value, mono = false, valueClass = "text-white",
}: {
  label: string;
  value: string | number | undefined;
  mono?: boolean;
  valueClass?: string;
}) {
  return (
    <div>
      <div className="text-gray-500 text-xs mb-0.5">{label}</div>
      <div className={`text-sm font-medium ${valueClass} ${mono ? "font-mono" : ""}`}>
        {value !== undefined && value !== null && value !== "" ? value : "—"}
      </div>
    </div>
  );
}
