"use client";

import { useState, useEffect } from "react";
import {
  BookOpen, Target, DollarSign, ShieldCheck, TrendingUp, Clock,
  ChevronDown, ChevronUp, AlertTriangle, CheckCircle, Edit3, X, Save,
  Zap, BarChart2, History,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

interface StreamRules {
  label: string; goal: string;
  entry_conditions: string[]; structure_rules: string[];
  dte: string; position_size: string;
  profit_target: string; stop_loss: string; exit_rules: string[];
}

interface RiskGuardrail {
  value: number; unit: string; note: string;
  bid_ask_pct?: number; open_interest?: number;
}

interface StrategyVersion {
  version: string; date: string; author: string; change_type: string;
  summary: string; changes: string[];
  performance: { win_rate: number | null; avg_r: number | null; trades: number; period: string };
  rationale: string;
}

interface PendingReview {
  id: string; proposed_by: string; proposed_date: string;
  description: string; evidence: string; status: string;
}

interface StrategyData {
  current: {
    version: string; effective_date: string; status: string; authored_by: string; summary: string;
    streams: { alpha: StreamRules; income: StreamRules };
    risk_guardrails: Record<string, RiskGuardrail>;
    position_sizing: { method: string; base_size_pct: number; max_size_pct: number; formula: string; kelly_fraction: number; note: string };
    confirmation_requirements: { min_independent_signals: number; independent_categories: string[]; anti_crowding: string; false_breakout_filter: string };
  };
  versions: StrategyVersion[];
  pending_review: PendingReview[];
}

const CHANGE_COLORS: Record<string, string> = {
  initial: "bg-blue-900/30 text-blue-400 border-blue-700/50",
  feature: "bg-purple-900/30 text-purple-400 border-purple-700/50",
  tightening: "bg-yellow-900/30 text-yellow-400 border-yellow-700/50",
  enhancement: "bg-green-900/30 text-green-400 border-green-700/50",
  ic_adjustment: "bg-orange-900/30 text-orange-400 border-orange-700/50",
};

export default function StrategyPage() {
  const [data, setData] = useState<StrategyData | null>(null);
  const [activeTab, setActiveTab] = useState<"current" | "history" | "pending">("current");
  const [expandedVersion, setExpandedVersion] = useState<string | null>("v1.4");
  const [editingGuardrail, setEditingGuardrail] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editNote, setEditNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedKey, setSavedKey] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/strategy`).then(r => r.json()).then(setData);
  }, []);

  const saveOverride = async (key: string) => {
    setSaving(true);
    await fetch(`${API}/strategy`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value: editValue, note: editNote, author: "V/N" }),
    });
    setSaving(false);
    setEditingGuardrail(null);
    setSavedKey(key);
    setTimeout(() => setSavedKey(null), 3000);
  };

  if (!data) return <div className="p-6 text-gray-500">Loading strategy...</div>;

  const { current, versions, pending_review } = data;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <BookOpen className="w-6 h-6 text-blue-400" />
            <h1 className="text-2xl font-bold text-white">Trading Strategy</h1>
            <span className="bg-green-900/40 border border-green-700/50 text-green-400 text-xs font-bold px-2.5 py-1 rounded-full">
              {current.version} ACTIVE
            </span>
          </div>
          <p className="text-gray-400 text-sm mt-1 max-w-2xl">{current.summary}</p>
          <p className="text-gray-500 text-xs mt-1">
            Effective {current.effective_date} · Updated by {current.authored_by}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b border-gray-800 pb-0">
        {([
          { key: "current", label: "Current Strategy", icon: Target },
          { key: "history", label: `Version History (${versions.length})`, icon: History },
          { key: "pending", label: `Pending Review (${pending_review.length})`, icon: AlertTriangle },
        ] as const).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition -mb-px ${
              activeTab === key
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-gray-400 hover:text-gray-300"
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* ── TAB: CURRENT STRATEGY ── */}
      {activeTab === "current" && (
        <div className="space-y-6">
          {/* Dual stream cards */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <StreamCard stream={current.streams.alpha} color="purple" icon={<Target className="w-4 h-4" />} />
            <StreamCard stream={current.streams.income} color="emerald" icon={<DollarSign className="w-4 h-4" />} />
          </div>

          {/* Entry confirmation requirements */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-4 h-4 text-blue-400" />
              <span className="text-gray-200 font-semibold text-sm">Entry Confirmation Requirements</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-gray-500 text-xs mb-1.5">Minimum independent signals</div>
                <div className="text-white font-bold text-lg">≥ {current.confirmation_requirements.min_independent_signals}</div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {current.confirmation_requirements.independent_categories.map(c => (
                    <span key={c} className="bg-gray-800 text-gray-400 text-xs px-2 py-0.5 rounded font-mono">{c}</span>
                  ))}
                </div>
              </div>
              <div className="space-y-3">
                <div>
                  <div className="text-gray-500 text-xs mb-0.5">Anti-crowding rule</div>
                  <div className="text-gray-300 text-xs">{current.confirmation_requirements.anti_crowding}</div>
                </div>
                <div>
                  <div className="text-gray-500 text-xs mb-0.5">False breakout filter</div>
                  <div className="text-gray-300 text-xs">{current.confirmation_requirements.false_breakout_filter}</div>
                </div>
              </div>
            </div>
          </div>

          {/* Position sizing */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <BarChart2 className="w-4 h-4 text-yellow-400" />
              <span className="text-gray-200 font-semibold text-sm">Position Sizing — {current.position_sizing.method}</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <SizingCard label="Base size" value={`${current.position_sizing.base_size_pct}%`} />
              <SizingCard label="Max size" value={`${current.position_sizing.max_size_pct}%`} />
              <SizingCard label="Kelly fraction" value={`${current.position_sizing.kelly_fraction}×`} sub="(half-Kelly)" />
              <SizingCard label="Formula" value={current.position_sizing.formula} mono />
            </div>
            <div className="bg-yellow-900/20 border border-yellow-700/40 rounded px-3 py-2 text-yellow-300 text-xs">
              {current.position_sizing.note}
            </div>
          </div>

          {/* Risk guardrails */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck className="w-4 h-4 text-red-400" />
              <span className="text-gray-200 font-semibold text-sm">Risk Guardrails</span>
              <span className="text-gray-500 text-xs ml-1">— click any value to propose an override</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {Object.entries(current.risk_guardrails).map(([key, rail]) => (
                <GuardrailRow
                  key={key}
                  ruleKey={key}
                  rail={rail}
                  editing={editingGuardrail === key}
                  saved={savedKey === key}
                  editValue={editValue}
                  editNote={editNote}
                  onEdit={() => { setEditingGuardrail(key); setEditValue(String(rail.value ?? rail.bid_ask_pct)); setEditNote(""); }}
                  onCancel={() => setEditingGuardrail(null)}
                  onSave={() => saveOverride(key)}
                  onChangeValue={setEditValue}
                  onChangeNote={setEditNote}
                  saving={saving}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── TAB: VERSION HISTORY ── */}
      {activeTab === "history" && (
        <div className="space-y-4">
          <div className="text-gray-400 text-sm mb-2">
            Every strategy change is recorded here with reasoning. You can question or add notes to any version.
          </div>

          {/* Performance summary chart */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-2">
            <div className="text-gray-200 font-semibold text-sm mb-3">Win Rate by Version</div>
            <div className="flex items-end gap-3">
              {versions.filter(v => v.performance.win_rate !== null).map(v => {
                const h = ((v.performance.win_rate! - 50) / 20) * 100;
                return (
                  <div key={v.version} className="flex-1 text-center">
                    <div className="flex items-end justify-center h-16 mb-1">
                      <div
                        className="w-full bg-blue-600/70 rounded-t"
                        style={{ height: `${Math.max(8, h)}%` }}
                      />
                    </div>
                    <div className="text-white font-bold text-sm">{v.performance.win_rate}%</div>
                    <div className="text-gray-500 text-xs">{v.version}</div>
                  </div>
                );
              })}
              <div className="flex-1 text-center opacity-40">
                <div className="flex items-end justify-center h-16 mb-1">
                  <div className="w-full border-2 border-dashed border-gray-600 rounded-t" style={{ height: "40%" }} />
                </div>
                <div className="text-gray-500 font-bold text-sm">?</div>
                <div className="text-gray-600 text-xs">v1.5</div>
              </div>
            </div>
          </div>

          {versions.map(v => (
            <div key={v.version} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <button
                className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-gray-800/40 transition"
                onClick={() => setExpandedVersion(expandedVersion === v.version ? null : v.version)}
              >
                <span className={`text-xs font-bold px-2 py-0.5 rounded border ${CHANGE_COLORS[v.change_type] || "text-gray-400"}`}>
                  {v.version}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded border ${CHANGE_COLORS[v.change_type] || "text-gray-400 border-gray-700"}`}>
                  {v.change_type.replace("_", " ")}
                </span>
                <span className="text-gray-300 text-sm flex-1">{v.summary}</span>
                <span className="text-gray-500 text-xs flex-shrink-0">{v.date}</span>
                {expandedVersion === v.version
                  ? <ChevronUp className="w-4 h-4 text-gray-500 flex-shrink-0" />
                  : <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />}
              </button>

              {expandedVersion === v.version && (
                <div className="px-4 pb-4 border-t border-gray-800">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3">
                    {/* Changes */}
                    <div className="md:col-span-2 space-y-2">
                      <div className="text-gray-500 text-xs font-medium uppercase tracking-wide">Changes</div>
                      <ul className="space-y-1">
                        {v.changes.map((c, i) => (
                          <li key={i} className="text-gray-300 text-sm flex items-start gap-2">
                            <span className="text-blue-400 mt-0.5 flex-shrink-0">→</span>
                            {c}
                          </li>
                        ))}
                      </ul>
                      <div className="mt-3 bg-gray-800/60 rounded p-3">
                        <div className="text-gray-500 text-xs font-medium mb-1">Rationale</div>
                        <div className="text-gray-300 text-sm">{v.rationale}</div>
                      </div>
                    </div>

                    {/* Performance */}
                    <div className="bg-gray-800/50 rounded-xl p-3">
                      <div className="text-gray-500 text-xs font-medium uppercase tracking-wide mb-2">Performance this version</div>
                      {v.performance.win_rate !== null ? (
                        <div className="space-y-1.5">
                          <PerfRow label="Win Rate" value={`${v.performance.win_rate}%`}
                            color={v.performance.win_rate >= 65 ? "text-green-400" : "text-yellow-400"} />
                          <PerfRow label="Avg R" value={`${v.performance.avg_r}R`}
                            color={(v.performance.avg_r ?? 0) >= 1.2 ? "text-green-400" : "text-yellow-400"} />
                          <PerfRow label="Trades" value={v.performance.trades} color="text-gray-300" />
                          <div className="text-gray-600 text-xs pt-1">{v.performance.period}</div>
                        </div>
                      ) : (
                        <div className="text-gray-500 text-xs">Active — no completed data yet</div>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 text-gray-500 text-xs">
                    By {v.author} · {v.date}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── TAB: PENDING REVIEW ── */}
      {activeTab === "pending" && (
        <div className="space-y-4">
          <div className="text-gray-400 text-sm mb-2">
            Proposed changes to the strategy based on new research or IC data. V/N review and approve or reject before any change is applied.
          </div>

          {pending_review.map(item => (
            <div key={item.id} className="bg-gray-900 border border-yellow-700/40 rounded-xl p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
                  <span className="text-white font-medium text-sm">Proposed: {item.description.split("—")[0].trim()}</span>
                </div>
                <span className="text-yellow-500 text-xs bg-yellow-900/30 border border-yellow-700/40 px-2 py-0.5 rounded">
                  {item.status.replace("_", " ")}
                </span>
              </div>
              <p className="text-gray-300 text-sm mb-2">{item.description}</p>
              <div className="bg-gray-800/50 rounded p-2 text-gray-400 text-xs mb-3">
                <span className="text-gray-500">Evidence: </span>{item.evidence}
              </div>
              <div className="flex gap-2 text-xs text-gray-500 mb-3">
                <span>Proposed by {item.proposed_by} · {item.proposed_date}</span>
              </div>
              <div className="flex gap-2">
                <button className="bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                  <CheckCircle className="w-3 h-3" /> Approve &amp; Apply to v{(parseFloat(data.current.version.slice(1)) + 0.1).toFixed(1)}
                </button>
                <button className="bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                  <X className="w-3 h-3" /> Reject
                </button>
                <button className="text-gray-500 hover:text-gray-300 px-3 py-1.5 text-xs">
                  Defer
                </button>
              </div>
            </div>
          ))}

          {/* Research-derived pending items */}
          <div className="bg-gray-900 border border-yellow-700/40 rounded-xl p-4">
            <div className="flex items-start gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
              <span className="text-white font-medium text-sm">Proposed: Half-Kelly position sizing (from 0.25× to 0.50× Kelly)</span>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Current implementation uses quarter-Kelly (0.25×). Research (2025 NBER + Tasty) shows half-Kelly achieves ~75% of optimal growth with meaningfully lower drawdown — better risk/reward than quarter-Kelly which is overly conservative.
            </p>
            <div className="bg-gray-800/50 rounded p-2 text-gray-400 text-xs mb-3">
              <span className="text-gray-500">Evidence: </span>Full Kelly = max growth but huge drawdown. Half-Kelly = 75% of optimal growth, ~50% less drawdown. Quarter-Kelly = low drawdown but significantly sub-optimal. Professional standard is half-Kelly.
            </div>
            <div className="flex gap-2">
              <button className="bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                <CheckCircle className="w-3 h-3" /> Approve
              </button>
              <button className="bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                <X className="w-3 h-3" /> Keep quarter-Kelly (more conservative)
              </button>
            </div>
          </div>

          <div className="bg-gray-900 border border-yellow-700/40 rounded-xl p-4">
            <div className="flex items-start gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
              <span className="text-white font-medium text-sm">Proposed: Deprecate congressional (STOCK Act) trading as alpha signal</span>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              NBER 2025 research paper (w35041) shows STOCK Act Congressional portfolios underperform or match market benchmarks — legislators track public retail sentiment, not private information. OGE executive-branch disclosures (Trump, Cabinet) remain valid alpha signal; Congressional is the weak one.
            </p>
            <div className="bg-gray-800/50 rounded p-2 text-gray-400 text-xs mb-3">
              <span className="text-gray-500">Evidence: </span>NBER w35041 "Capital in the Capitol: Congressional Trades Resemble Uninformed Retail Trading" (2025). Keep OGE executive disclosures (high-value), remove Congressional STOCK Act from scoring.
            </div>
            <div className="flex gap-2">
              <button className="bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                <CheckCircle className="w-3 h-3" /> Approve — focus only on OGE
              </button>
              <button className="bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                <X className="w-3 h-3" /> Keep both
              </button>
            </div>
          </div>

          <div className="bg-gray-900 border border-yellow-700/40 rounded-xl p-4">
            <div className="flex items-start gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
              <span className="text-white font-medium text-sm">Proposed: Add OPEX Vanna/Charm proximity flag</span>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Charm (delta decay with time) and Vanna (delta change with IV) create systematic dealer rebalancing flows around monthly/quarterly OPEX. Adding an "OPEX proximity" flag (≤5 days to monthly expiry) would warn that mechanical flows may override analysis signals.
            </p>
            <div className="bg-gray-800/50 rounded p-2 text-gray-400 text-xs mb-3">
              <span className="text-gray-500">Evidence: </span>SpotGamma shows 78% accuracy on SPX range prediction. Charm accumulates overnight, creates opening print biases on OPEX days. GEX/Vanna/Charm most reliable on large-cap indexes (SPX/SPY), less so on individual stocks.
            </div>
            <div className="flex gap-2">
              <button className="bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                <CheckCircle className="w-3 h-3" /> Approve — add OPEX flag to analysis
              </button>
              <button className="bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5">
                <X className="w-3 h-3" /> Defer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StreamCard({ stream, color, icon }: { stream: StreamRules; color: "purple" | "emerald"; icon: React.ReactNode }) {
  const [expanded, setExpanded] = useState(false);
  const border = color === "purple" ? "border-purple-900/60" : "border-emerald-900/50";
  const header = color === "purple"
    ? "bg-purple-900/30 text-purple-300"
    : "bg-emerald-900/30 text-emerald-300";

  return (
    <div className={`bg-gray-900 border ${border} rounded-xl overflow-hidden`}>
      <div className={`px-4 py-3 ${header} flex items-center justify-between`}>
        <div className="flex items-center gap-2 font-semibold text-sm">
          {icon}
          {stream.label}
        </div>
        <span className="text-xs opacity-70">{stream.goal}</span>
      </div>
      <div className="p-4 space-y-3">
        <div>
          <div className="text-gray-500 text-xs font-medium mb-1.5">Entry Conditions</div>
          <ul className="space-y-1">
            {stream.entry_conditions.map((c, i) => (
              <li key={i} className="text-gray-300 text-xs flex items-start gap-1.5">
                <span className="text-green-400 mt-0.5">✓</span> {c}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-gray-500 text-xs font-medium mb-1.5">Structure Rules</div>
          <ul className="space-y-1">
            {stream.structure_rules.map((r, i) => (
              <li key={i} className="text-gray-300 text-xs flex items-start gap-1.5">
                <span className="text-blue-400 mt-0.5">→</span> {r}
              </li>
            ))}
          </ul>
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-gray-500 mb-0.5">DTE</div>
            <div className="text-white font-mono">{stream.dte}</div>
          </div>
          <div>
            <div className="text-gray-500 mb-0.5">Size</div>
            <div className="text-white font-mono">{stream.position_size}</div>
          </div>
          <div>
            <div className="text-gray-500 mb-0.5">Profit target</div>
            <div className="text-green-400 font-mono">{stream.profit_target}</div>
          </div>
          <div>
            <div className="text-gray-500 mb-0.5">Stop loss</div>
            <div className="text-red-400 font-mono">{stream.stop_loss}</div>
          </div>
        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="text-gray-500 hover:text-gray-300 text-xs flex items-center gap-1 transition"
        >
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          Exit rules
        </button>

        {expanded && (
          <ul className="space-y-1 border-t border-gray-800 pt-2">
            {stream.exit_rules.map((r, i) => (
              <li key={i} className="text-gray-300 text-xs flex items-start gap-1.5">
                <Clock className="w-3 h-3 text-yellow-400 mt-0.5 flex-shrink-0" /> {r}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function GuardrailRow({
  ruleKey, rail, editing, saved, editValue, editNote, saving,
  onEdit, onCancel, onSave, onChangeValue, onChangeNote,
}: {
  ruleKey: string; rail: RiskGuardrail; editing: boolean; saved: boolean;
  editValue: string; editNote: string; saving: boolean;
  onEdit: () => void; onCancel: () => void; onSave: () => void;
  onChangeValue: (v: string) => void; onChangeNote: (v: string) => void;
}) {
  const label = ruleKey.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  const value = rail.value !== undefined ? rail.value : (rail.bid_ask_pct ?? "—");
  const unit = rail.unit || (rail.bid_ask_pct ? "%" : "");

  return (
    <div className={`rounded-lg p-3 border transition ${
      editing ? "border-blue-600 bg-blue-900/10" : saved ? "border-green-700 bg-green-900/10" : "border-gray-800 bg-gray-800/30"
    }`}>
      {!editing ? (
        <div className="flex items-center justify-between">
          <div>
            <div className="text-gray-400 text-xs mb-0.5">{label}</div>
            <div className="flex items-baseline gap-1">
              <span className="text-white font-bold">{value}</span>
              <span className="text-gray-500 text-xs">{unit}</span>
              {saved && <span className="text-green-400 text-xs ml-1">✓ Saved</span>}
            </div>
            <div className="text-gray-600 text-xs mt-0.5">{rail.note}</div>
          </div>
          <button
            onClick={onEdit}
            className="text-gray-600 hover:text-blue-400 transition p-1"
            title="Propose override"
          >
            <Edit3 className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="text-gray-400 text-xs font-medium">{label}</div>
          <div className="flex items-center gap-2">
            <input
              value={editValue}
              onChange={e => onChangeValue(e.target.value)}
              className="bg-gray-800 border border-blue-600 text-white rounded px-2 py-1 text-sm w-24 font-mono"
              placeholder="new value"
            />
            <span className="text-gray-500 text-xs">{unit}</span>
          </div>
          <input
            value={editNote}
            onChange={e => onChangeNote(e.target.value)}
            placeholder="Reason for change..."
            className="bg-gray-800 border border-gray-700 text-white rounded px-2 py-1 text-xs w-full"
          />
          <div className="flex gap-2">
            <button
              onClick={onSave}
              disabled={saving}
              className="bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white px-2 py-1 rounded text-xs flex items-center gap-1"
            >
              <Save className="w-3 h-3" /> Save
            </button>
            <button onClick={onCancel} className="text-gray-500 text-xs px-2 py-1 hover:text-gray-300">Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

function SizingCard({ label, value, sub, mono }: { label: string; value: string | number; sub?: string; mono?: boolean }) {
  return (
    <div className="bg-gray-800/50 rounded p-2.5 text-center">
      <div className="text-gray-500 text-xs mb-0.5">{label}</div>
      <div className={`text-white text-sm font-bold ${mono ? "font-mono text-xs leading-tight" : ""}`}>{value}</div>
      {sub && <div className="text-gray-500 text-xs">{sub}</div>}
    </div>
  );
}

function PerfRow({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className={`font-bold ${color}`}>{value}</span>
    </div>
  );
}
