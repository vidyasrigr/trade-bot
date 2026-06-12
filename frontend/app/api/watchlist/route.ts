import { NextResponse } from "next/server";
import { WATCHLIST_STATE } from "@/lib/mockData";

let _watchlist = [...WATCHLIST_STATE];

export async function GET() {
  return NextResponse.json({ watchlist: _watchlist, count: _watchlist.length });
}
