import { NextResponse } from "next/server";

export async function DELETE(_req: Request, { params }: { params: { symbol: string } }) {
  return NextResponse.json({ ok: true, symbol: params.symbol.toUpperCase() });
}
