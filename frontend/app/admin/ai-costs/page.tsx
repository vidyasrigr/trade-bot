"use client";

import { useState, useEffect, useCallback } from "react";
import { Cpu, TrendingUp, Zap, Activity, RefreshCw } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

type Period = "hourly" | "daily" | "weekly";

interface Summary {
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_calls: number;
}

interface ModelRow {
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

interface AgentRow {
  agent: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

interface TimelineRow {
  bucket: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

interface CostData {
  period: Period;
  summary: Summary;
  by_model: ModelRow[];
  by_agent: AgentRow[];
  timeline: TimelineRow[];
  error?: string;
}

const MODEL_LABELS: Record<string, string> = {
  "claude-sonnet-4-6": "Sonnet 4.6",
  "claude-sonnet-4-7": "Sonnet 4.7",
  "claude-opus-4-6": "Opus 4.6",
  "claude-opus-4-7": "Opus 4.7",
  "claude-haiku-4-5-20251001": "Haiku 4.5",
  "llama3.1:8b": "Llama 3.1 8B",
  "deepseek-r1:7b": "DeepSeek R1 7B",
  "deepseek-r1:14b": "DeepSeek R1 14B",
  "nomic-embed-text": "Nomic Embed",
};

const MODEL_COLORS: Record<string, string> = {
  "claude-sonnet-4-6": "text-purple-400",
  "claude-sonnet-4-7": "text-purple-400",
  "claude-opus-4-6": "text-orange-400",
  "claude-opus-4-7": "text-orange-400",
  "claude-haiku-4-5-20251001": "text-blue-400",
  "llama3.1:8b": "text-green-400",
  "deepseek-r1:7b": "text-green-400",
  "deepseek-r1:14b": "text-green-400",
  "nomic-embed-text": "text-green-400",
};

function fmt(model: string) {
  return MODEL_LABELS[model] ?? model;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function fmtCost(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.001) return `$${(n * 1000).toFixed(4)}m`;
  return `$${n.toFixed(4)}`;
}

function CostBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 bg-gray-800 rounded-full h-1.5 flex-shrink-0">
        <div
          className="bg-green-500 h-1.5 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-gray-300 text-xs font-mono w-16 text-right">{fmtCost(value)}</span>
    </div>
  );
}

export default function AiCostsPage() {
  const [period, setPeriod] = useState<Period>("daily");
  const [data, setData] = useState<CostData | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async (p: Period) => {
    setLoading(true);
    try {
      const resp = await fetch(`${API}/admin/ai-costs?period=${p}`);
      const json = await resp.json();
      setData(json);
      setLastUpdated(new Date());
    } catch {
      setData({ period: p, summary: { total_cost_usd: 0, total_input_tokens: 0, total_output_tokens: 0, total_calls: 0 }, by_model: [], by_agent: [], timeline: [], error: "Failed to fetch" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(period); }, [period, load]);

  // Auto-refresh every 60s
  useEffect(() => {
    const id = setInterval(() => load(period), 60_000);
    return () => clearInterval(id);
  }, [period, load]);

  const maxModelCost = data ? Math.max(...data.by_model.map(r => r.cost_usd), 0.000001) : 1;
  const maxTimelineCost = data ? Math.max(...data.timeline.map(r => r.cost_usd), 0.000001) : 1;

  const PERIOD_LABELS: Record<Period, string> = {
    hourly: "Last 24 Hours (by hour)",
    daily: "Last 7 Days (by day)",
    weekly: "Last 4 Weeks (by week)",
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Cpu className="w-7 h-7 text-purple-400" />
          <div>
            <h1 className="text-2xl font-bold text-white">AI Usage & Costs</h1>
            <p className="text-gray-400 text-sm mt-0.5">Token consumption and API spend across all models</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-gray-600 text-xs">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => load(period)}
            disabled={loading}
            className="flex items-center gap-1.5 text-gray-400 hover:text-white text-xs px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Period tabs */}
      <div className="flex gap-1 mb-6 bg-gray-900 p-1 rounded-lg w-fit">
        {(["hourly", "daily", "weekly"] as Period[]).map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`px-4 py-1.5 rounded text-sm font-medium transition capitalize ${
              period === p
                ? "bg-gray-700 text-white"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      {data?.error && (
        <div className="mb-4 bg-red-900/20 border border-red-700/50 rounded-lg px-4 py-3 text-red-400 text-sm">
          {data.error} — backend may be offline
        </div>
      )}

      {/* Summary cards */}
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <SummaryCard
              icon={<TrendingUp className="w-4 h-4 text-green-400" />}
              label="Total Cost"
              value={fmtCost(data.summary.total_cost_usd)}
              sub={PERIOD_LABELS[period]}
            />
            <SummaryCard
              icon={<Zap className="w-4 h-4 text-blue-400" />}
              label="Input Tokens"
              value={fmtTokens(data.summary.total_input_tokens)}
              sub="Prompt tokens"
            />
            <SummaryCard
              icon={<Zap className="w-4 h-4 text-purple-400" />}
              label="Output Tokens"
              value={fmtTokens(data.summary.total_output_tokens)}
              sub="Completion tokens"
            />
            <SummaryCard
              icon={<Activity className="w-4 h-4 text-orange-400" />}
              label="API Calls"
              value={data.summary.total_calls.toLocaleString()}
              sub="Claude calls only"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            {/* By model */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="text-gray-200 font-semibold text-sm mb-3">Cost by Model</div>
              {data.by_model.length === 0 ? (
                <div className="text-gray-600 text-xs py-4 text-center">No data yet</div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-600 border-b border-gray-800">
                      <th className="text-left py-1.5 font-medium">Model</th>
                      <th className="text-right py-1.5 font-medium">Calls</th>
                      <th className="text-right py-1.5 font-medium">In</th>
                      <th className="text-right py-1.5 font-medium">Out</th>
                      <th className="text-right py-1.5 font-medium pr-1">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_model.map(row => (
                      <tr key={row.model} className="border-b border-gray-800/50 last:border-0">
                        <td className={`py-2 font-medium ${MODEL_COLORS[row.model] ?? "text-gray-300"}`}>
                          {fmt(row.model)}
                        </td>
                        <td className="text-right text-gray-400 py-2">{row.calls}</td>
                        <td className="text-right text-gray-400 py-2">{fmtTokens(row.input_tokens)}</td>
                        <td className="text-right text-gray-400 py-2">{fmtTokens(row.output_tokens)}</td>
                        <td className="py-2 pl-3">
                          <CostBar value={row.cost_usd} max={maxModelCost} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* By agent */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="text-gray-200 font-semibold text-sm mb-3">Cost by Agent</div>
              {data.by_agent.length === 0 ? (
                <div className="text-gray-600 text-xs py-4 text-center">No data yet</div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-600 border-b border-gray-800">
                      <th className="text-left py-1.5 font-medium">Agent</th>
                      <th className="text-left py-1.5 font-medium">Model</th>
                      <th className="text-right py-1.5 font-medium">Calls</th>
                      <th className="text-right py-1.5 font-medium">Tokens</th>
                      <th className="text-right py-1.5 font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_agent.map(row => (
                      <tr key={row.agent} className="border-b border-gray-800/50 last:border-0">
                        <td className="py-2 text-gray-300 font-medium">
                          {row.agent.replace(/_/g, " ")}
                        </td>
                        <td className={`py-2 ${MODEL_COLORS[row.model] ?? "text-gray-500"}`}>
                          {fmt(row.model)}
                        </td>
                        <td className="text-right text-gray-400 py-2">{row.calls}</td>
                        <td className="text-right text-gray-400 py-2">
                          {fmtTokens(row.input_tokens + row.output_tokens)}
                        </td>
                        <td className="text-right font-mono text-gray-300 py-2">
                          {fmtCost(row.cost_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Timeline */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="text-gray-200 font-semibold text-sm mb-3">
              Timeline — {PERIOD_LABELS[period]}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-600 border-b border-gray-800">
                    <th className="text-left py-1.5 font-medium">
                      {period === "hourly" ? "Hour" : period === "daily" ? "Date" : "Week of"}
                    </th>
                    <th className="text-right py-1.5 font-medium">Calls</th>
                    <th className="text-right py-1.5 font-medium">Input</th>
                    <th className="text-right py-1.5 font-medium">Output</th>
                    <th className="text-right py-1.5 font-medium">Total Tokens</th>
                    <th className="py-1.5 font-medium pl-4">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {data.timeline.map(row => (
                    <tr key={row.bucket} className="border-b border-gray-800/40 last:border-0 hover:bg-gray-800/30">
                      <td className="py-2 text-gray-400 font-mono">{row.bucket}</td>
                      <td className="text-right text-gray-500 py-2">{row.calls || "—"}</td>
                      <td className="text-right text-gray-500 py-2">{row.input_tokens ? fmtTokens(row.input_tokens) : "—"}</td>
                      <td className="text-right text-gray-500 py-2">{row.output_tokens ? fmtTokens(row.output_tokens) : "—"}</td>
                      <td className="text-right text-gray-400 py-2">
                        {row.input_tokens + row.output_tokens ? fmtTokens(row.input_tokens + row.output_tokens) : "—"}
                      </td>
                      <td className="py-2 pl-4">
                        {row.cost_usd > 0
                          ? <CostBar value={row.cost_usd} max={maxTimelineCost} />
                          : <span className="text-gray-700">—</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pricing reference */}
          <div className="mt-4 bg-gray-900/50 border border-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 font-semibold text-xs mb-2">Pricing Reference (per 1M tokens)</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { model: "Sonnet 4.6/4.7", in: "$3.00", out: "$15.00", color: "text-purple-400" },
                { model: "Opus 4.6/4.7",   in: "$15.00", out: "$75.00", color: "text-orange-400" },
                { model: "Haiku 4.5",       in: "$0.80", out: "$4.00",  color: "text-blue-400" },
                { model: "Ollama (local)",  in: "Free",  out: "Free",   color: "text-green-400" },
              ].map(p => (
                <div key={p.model} className="text-xs">
                  <div className={`font-medium mb-0.5 ${p.color}`}>{p.model}</div>
                  <div className="text-gray-600">In: {p.in} · Out: {p.out}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {!data && loading && (
        <div className="text-gray-500 text-sm py-12 text-center">Loading...</div>
      )}
    </div>
  );
}

function SummaryCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: string; sub: string;
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-gray-500 text-xs">{label}</span>
      </div>
      <div className="text-white text-xl font-bold">{value}</div>
      <div className="text-gray-600 text-xs mt-0.5">{sub}</div>
    </div>
  );
}
