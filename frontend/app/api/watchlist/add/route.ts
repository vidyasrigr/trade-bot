import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  const symbol = (body.symbol as string || "").toUpperCase();
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 });

  const newEntry = {
    symbol, added_at: new Date().toISOString(),
    last_refreshed: new Date().toISOString(),
    current_score: 50.0, prev_score: 0.0, current_direction: "neutral",
    current_price: 0.0, iv_rank: 50.0, regime: "unknown",
    total_trades: 0, wins: 0, losses: 0, win_rate: 0.0, avg_r_multiple: 0.0,
    active_alerts: [], score_history: [], ticker_lessons: [], factor_overrides: {},
    notes: body.notes || "",
  };

  return NextResponse.json({ ok: true, symbol, state: newEntry });
}
