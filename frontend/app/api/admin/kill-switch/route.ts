import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  return NextResponse.json({
    ok: true,
    status: body.active ? "halted" : "active",
    reason: body.active ? (body.reason || "Manual override") : null,
  });
}
