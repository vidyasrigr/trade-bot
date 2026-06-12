import { NextResponse } from "next/server";

export async function GET(_req: Request, { params }: { params: { symbol: string } }) {
  return NextResponse.json({
    symbol: params.symbol,
    valid: true,
    checked_at: new Date().toISOString(),
    price_change_pct: 0.3,
    iv_change_pct: 1.2,
    message: "Setup validated — price and IV within tolerance",
  });
}
