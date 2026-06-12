import { NextResponse } from "next/server";
import { JOURNAL_ENTRIES } from "@/lib/mockData";

export async function GET() {
  const entries = JOURNAL_ENTRIES.map(e => ({
    id: e.id,
    symbol: e.symbol,
    regime: e.regime_at_entry,
    lesson: e.lesson,
    r_multiple: e.r_multiple,
    factors_that_worked: e.factors_that_fired,
    factors_that_failed: e.factors_that_missed,
    created_at: e.created_at,
  }));
  return NextResponse.json({ entries });
}
