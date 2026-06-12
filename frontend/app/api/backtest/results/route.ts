import { NextResponse } from "next/server";
import { BACKTEST_RESULTS } from "@/lib/mockData";

export async function GET() {
  return NextResponse.json(BACKTEST_RESULTS);
}
