import { NextResponse } from "next/server";
import { IC_WEIGHTS } from "@/lib/mockData";

export async function GET() {
  const weights = IC_WEIGHTS.map(w => ({
    category: w.category,
    regime: w.regime,
    ic_score: w.ic_score,
    weight_multiplier: w.multiplier,
    sample_count: w.trade_count,
  }));
  return NextResponse.json({ weights, current_regime: "bull_trend" });
}
