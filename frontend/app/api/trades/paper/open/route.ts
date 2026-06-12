import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  return NextResponse.json({
    success: true,
    trade_id: Math.floor(Math.random() * 1000) + 100,
    message: `Paper trade opened: ${body.symbol} ${body.strategy} @ $${body.entry_price}`,
    tradier_order_id: `PAPER-${Date.now()}`,
  });
}
