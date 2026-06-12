import { NextResponse } from "next/server";
import { POLITICAL_DISCLOSURES } from "@/lib/mockData";

export async function GET() {
  const disclosures = POLITICAL_DISCLOSURES.disclosures.map(d => ({
    id: d.id,
    official_name: d.filer,
    official_role: "President of the United States",
    symbol: d.ticker,
    transaction_type: d.transaction_type,
    amount_range: d.amount_range,
    transaction_date: d.trade_date,
    disclosure_date: d.disclosure_date,
    subsequent_govt_event: d.related_event,
    price_at_trade: d.price_at_trade,
    price_now: d.price_now,
    pct_move: d.pct_move,
    signal_strength: d.signal_strength,
  }));

  return NextResponse.json({
    disclosures,
    total_transactions_q1_2026: POLITICAL_DISCLOSURES.total_transactions_q1_2026,
    tracking_since: POLITICAL_DISCLOSURES.tracking_since,
  });
}
