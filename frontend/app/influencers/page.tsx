"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, TrendingUp, TrendingDown, Zap } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

interface LatestPick {
  ticker: string; direction: string; date: string; outcome: string;
  reasoning_type: string; pre_video_call_volume_ratio: number;
}
interface Channel {
  channel_id: string; name: string;
  credibility_score: number; total_calls: number; correct: number; incorrect: number;
  specialty: string; latest_pick: LatestPick;
  black_sheep: boolean; black_sheep_signal?: string; description: string;
}

export default function InfluencersPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [crowding, setCrowding] = useState<{tickers: string[]; message: string}[]>([]);
  const [flowAlerts, setFlowAlerts] = useState<{ticker: string; message: string}[]>([]);
  const [filter, setFilter] = useState<"all" | "black_sheep" | "top">("all");

  useEffect(() => {
    fetch(`${API}/influencers`).then(r => r.json()).then(d => {
      setChannels(d.channels || []);
      setCrowding(d.crowding_alerts || []);
      setFlowAlerts(d.pre_video_flow_alerts || []);
    });
  }, []);

  const filtered = [...channels]
    .filter(c => filter === "black_sheep" ? c.black_sheep : filter === "top" ? c.credibility_score >= 0.75 : true)
    .sort((a, b) => b.credibility_score - a.credibility_score);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">YouTube Influencer Signal Board</h1>
        <p className="text-gray-400 text-sm mt-1">
          Every call tracked to outcome. Credibility scored after 50+ calls. Black Sheep = fade signal.
          Requires Ollama on RTX 5080 for live transcript processing.
        </p>
      </div>

      {crowding.map((a, i) => (
        <div key={i} className="mb-3 bg-yellow-900/20 border border-yellow-700/50 rounded-lg px-4 py-2 text-yellow-300 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {a.message}
          <div className="ml-auto flex gap-1">
            {a.tickers.map(t => (
              <Link key={t} href={`/analysis/${t}`} className="text-yellow-400 font-mono text-xs bg-yellow-900/30 px-1.5 py-0.5 rounded hover:underline">${t}</Link>
            ))}
          </div>
        </div>
      ))}
      {flowAlerts.map((a, i) => (
        <div key={i} className="mb-3 bg-red-900/20 border border-red-700/50 rounded-lg px-4 py-2 text-red-300 text-sm flex items-center gap-2">
          <Zap className="w-4 h-4 flex-shrink-0" />
          <span className="font-semibold">Pre-Video Flow Alert:</span> {a.message}
        </div>
      ))}

      <div className="flex gap-2 mb-4">
        {(["all", "top", "black_sheep"] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              filter === f ? "bg-blue-700 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}>
            {f === "black_sheep" ? "⚠️ Black Sheep" : f === "top" ? "⭐ Top Tier (≥75%)" : "All"}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {filtered.map(c => (
          <div key={c.channel_id} className={`bg-gray-900 border rounded-xl p-4 ${c.black_sheep ? "border-red-800/60" : "border-gray-800"}`}>
            <div className="flex items-start gap-4">
              <CredibilityRing score={c.credibility_score} calls={c.total_calls} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-white font-bold">{c.name}</span>
                  {c.black_sheep && <span className="text-xs bg-red-900/40 text-red-400 border border-red-700/50 px-2 py-0.5 rounded-full">⚠️ Black Sheep — Fade Signal</span>}
                  {c.credibility_score >= 0.80 && !c.black_sheep && <span className="text-xs bg-yellow-900/30 text-yellow-400 px-1.5 py-0.5 rounded-full">⭐ Top Tier</span>}
                </div>
                <div className="text-gray-400 text-xs mb-1">{c.specialty}</div>
                <div className="text-gray-300 text-xs leading-relaxed">{c.description}</div>

                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                  <span className="text-gray-500">Latest:</span>
                  <Link href={`/analysis/${c.latest_pick.ticker}`} className="text-blue-400 font-mono font-bold hover:underline">${c.latest_pick.ticker}</Link>
                  {c.latest_pick.direction === "bullish"
                    ? <span className="text-green-400 flex items-center gap-0.5"><TrendingUp className="w-3 h-3" /> Bull</span>
                    : <span className="text-red-400 flex items-center gap-0.5"><TrendingDown className="w-3 h-3" /> Bear</span>}
                  <span className="text-gray-500">{c.latest_pick.date}</span>
                  <OutcomeBadge outcome={c.latest_pick.outcome} />
                  {c.latest_pick.pre_video_call_volume_ratio > 1.5 && (
                    <span className="text-yellow-400 flex items-center gap-1">
                      <Zap className="w-3 h-3" />{c.latest_pick.pre_video_call_volume_ratio.toFixed(1)}× pre-video flow
                    </span>
                  )}
                </div>
              </div>

              <div className="w-28 flex-shrink-0">
                <div className="text-gray-500 text-xs mb-1">W / L</div>
                <div className="flex h-2.5 rounded overflow-hidden">
                  <div className="bg-green-600" style={{ width: `${c.correct / c.total_calls * 100}%` }} />
                  <div className="bg-red-800" style={{ width: `${c.incorrect / c.total_calls * 100}%` }} />
                </div>
                <div className="flex justify-between text-xs mt-0.5">
                  <span className="text-green-400">{c.correct}W</span>
                  <span className="text-red-400">{c.incorrect}L</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CredibilityRing({ score, calls }: { score: number; calls: number }) {
  const pct = score * 100;
  const color = pct >= 75 ? "#22c55e" : pct >= 50 ? "#f59e0b" : "#ef4444";
  const r = 22, circ = 2 * Math.PI * r, dash = (pct / 100) * circ;
  return (
    <div className="flex-shrink-0 text-center w-16">
      <div className="relative inline-flex items-center justify-center">
        <svg width="52" height="52" viewBox="0 0 52 52">
          <circle cx="26" cy="26" r={r} fill="none" stroke="#1f2937" strokeWidth="4" />
          <circle cx="26" cy="26" r={r} fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" transform="rotate(-90 26 26)" />
        </svg>
        <span className="absolute text-xs font-bold" style={{ color }}>{pct.toFixed(0)}%</span>
      </div>
      <div className="text-gray-600 text-xs">{calls} calls</div>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  if (outcome === "win") return <span className="text-green-400 font-medium">✓ Win</span>;
  if (outcome === "loss") return <span className="text-red-400 font-medium">✗ Loss</span>;
  return <span className="text-gray-500">Open</span>;
}
