import { NextResponse } from "next/server";

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const body = await request.json();
  const entryPrice = 5.00; // mock entry
  const exitPrice = body.exit_price as number;
  const contracts = 2;
  const pnl = (exitPrice - entryPrice) * contracts * 100;

  return NextResponse.json({
    success: true,
    trade_id: parseInt(params.id),
    realized_pnl: parseFloat(pnl.toFixed(2)),
    r_multiple: parseFloat((pnl / (entryPrice * contracts * 100)).toFixed(2)),
    message: `Trade #${params.id} closed at $${exitPrice}`,
  });
}
