import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "started",
    message: "Scan queued. Stage 1 pre-screen running on 4,823 symbols.",
    estimated_seconds: 480,
  });
}
