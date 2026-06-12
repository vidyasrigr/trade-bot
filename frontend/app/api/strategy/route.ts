import { NextResponse } from "next/server";
import { STRATEGY_DATA } from "@/lib/mockData";

export async function GET() {
  return NextResponse.json(STRATEGY_DATA);
}

export async function PATCH(req: Request) {
  // In production: save override to DB with author + timestamp
  const body = await req.json();
  return NextResponse.json({ ok: true, applied: body });
}
