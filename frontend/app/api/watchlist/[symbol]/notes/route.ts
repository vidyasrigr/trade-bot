import { NextResponse } from "next/server";

export async function PATCH(_req: Request, { params }: { params: { symbol: string } }) {
  return NextResponse.json({ ok: true, symbol: params.symbol.toUpperCase() });
}
