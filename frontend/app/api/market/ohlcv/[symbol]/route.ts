import { NextResponse } from "next/server";
import { generateOHLCV } from "@/lib/mockData";

export async function GET(_req: Request, { params }: { params: { symbol: string } }) {
  const candles = generateOHLCV(params.symbol.toUpperCase(), 90);
  // Return both formats: chart expects ohlcv[].date; SSE client expects candles[].time
  const ohlcv = candles.map(c => ({ ...c, date: c.time }));
  return NextResponse.json({ symbol: params.symbol.toUpperCase(), candles, ohlcv });
}
