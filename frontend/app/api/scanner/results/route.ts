import { NextResponse } from "next/server";
import { SCANNER_RESULTS } from "@/lib/mockData";

function classifyStream(conviction: number, ivPct: number, direction: string): "alpha" | "income" {
  // High IV + bearish → sell premium (income)
  if (direction === "bearish" && ivPct >= 55) return "income";
  // Very high IV regardless → sell premium
  if (ivPct >= 65) return "income";
  // High conviction + reasonable IV → directional OTM buy (alpha)
  if (conviction >= 78) return "alpha";
  // Low IV → cheap options, buy directional (alpha)
  if (ivPct < 45) return "alpha";
  return "income";
}

export async function GET() {
  const results = SCANNER_RESULTS.results.map(r => {
    const iv_percentile = 35 + (r.total_score % 40);
    const stream = classifyStream(r.conviction, iv_percentile, r.direction);
    return {
      symbol: r.symbol,
      name: r.name,
      sector: r.sector,
      total_score: r.total_score,
      conviction_score: r.conviction,
      direction: r.direction,
      vol_regime: "bull_trend",
      iv_percentile,
      trade_thesis: r.catalyst,
      catalyst_flags: Object.fromEntries(r.stage3_flags.map(f => [f, true])),
      stream,
      order_ticket: {
        strategy: stream === "income"
          ? (r.direction === "bearish" ? "bear_call_spread" : "iron_condor")
          : (r.direction === "bearish" ? "bear_put_spread" : "bull_call_spread"),
        expiry: stream === "alpha" ? "2026-06-13" : "2026-06-06",
        strike: Math.round(r.price * (r.direction === "bearish" ? 0.97 : 1.03)),
      },
      price: r.price,
      change_pct: r.change_pct,
    };
  });

  return NextResponse.json({
    results,
    stage_counts: { s1: 312, s2: 74, s3: 21 },
    scanned_at: SCANNER_RESULTS.scan_date,
    total_scanned: SCANNER_RESULTS.total_scanned,
  });
}
