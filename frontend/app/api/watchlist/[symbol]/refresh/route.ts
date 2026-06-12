import { NextResponse } from "next/server";
import { WATCHLIST_STATE } from "@/lib/mockData";

export async function POST(_req: Request, { params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  const existing = WATCHLIST_STATE.find(w => w.symbol === symbol);
  if (existing) {
    const scoreChange = (Math.random() - 0.4) * 8;
    return NextResponse.json({
      ok: true,
      state: { ...existing, current_score: Math.min(100, Math.max(0, existing.current_score + scoreChange)), last_refreshed: new Date().toISOString() },
    });
  }
  return NextResponse.json({ ok: true, state: { symbol, current_score: 50, last_refreshed: new Date().toISOString() } });
}
