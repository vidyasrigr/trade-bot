import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    halted: false,
    active_breakers: [],
    warnings: [
      "Semis sector at 8.4% of deployed risk — well within 35% limit",
    ],
    reason: "",
    kill_switch: { active: false, reason: null },
    portfolio_snapshot: {
      portfolio_value: 150000,
      daily_pnl: 1032,
      daily_pnl_pct: 0.69,
      open_positions: 3,
      max_positions: 10,
      deployed_pct: 22.0,
    },
  });
}
