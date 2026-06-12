import { NextResponse } from "next/server";
import { PAPER_TRADES } from "@/lib/mockData";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") || "all";

  const trades = status === "all"
    ? PAPER_TRADES.trades
    : PAPER_TRADES.trades.filter(t => t.status === status);

  return NextResponse.json({ trades });
}
