import { NextResponse } from "next/server";

// ── Math helpers ──────────────────────────────────────────────────────────────

function normalCDF(x: number): number {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
  const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x) / Math.sqrt(2);
  const t = 1 / (1 + p * ax);
  const y = 1 - (((((a5*t + a4)*t) + a3)*t + a2)*t + a1)*t * Math.exp(-ax*ax);
  return 0.5 * (1 + sign * y);
}

function bsCall(S: number, K: number, T: number, sigma: number): number {
  if (T <= 0 || sigma <= 0) return Math.max(0, S - K);
  const d1 = (Math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return S * normalCDF(d1) - K * normalCDF(d2);
}

function bsDelta(S: number, K: number, T: number, sigma: number): number {
  if (T <= 0) return S > K ? 1 : 0;
  const d1 = (Math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * Math.sqrt(T));
  return normalCDF(d1);
}

// P(stock >= target_price in DTE days given lognormal with sigma)
function probReach(S: number, target: number, T: number, sigma: number): number {
  if (target <= S) return 100;
  if (T <= 0 || sigma <= 0) return 0;
  const d2 = (Math.log(S / target) + (-0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
  return Math.round(normalCDF(d2) * 100);
}

// ── Symbol universe ───────────────────────────────────────────────────────────

const SYMBOL_DATA: Record<string, { price: number; hv: number; trend_score: number; iv_pct: number; direction: string }> = {
  INTC:  { price: 107.93, hv: 0.854, trend_score: 78, iv_pct: 75, direction: "bullish" },
  NVDA:  { price: 1247.5, hv: 0.62,  trend_score: 84, iv_pct: 68, direction: "bullish" },
  PLTR:  { price: 43.80,  hv: 0.71,  trend_score: 74, iv_pct: 44, direction: "bullish" },
  OKLO:  { price: 52.30,  hv: 0.95,  trend_score: 67, iv_pct: 31, direction: "bullish" },
  IONQ:  { price: 38.60,  hv: 1.20,  trend_score: 71, iv_pct: 38, direction: "bullish" },
  RDW:   { price: 24.15,  hv: 1.45,  trend_score: 69, iv_pct: 52, direction: "bullish" },
  RACE:  { price: 418.70, hv: 0.38,  trend_score: 38, iv_pct: 71, direction: "bearish" },
  LLY:   { price: 1053.2, hv: 0.42,  trend_score: 77, iv_pct: 42, direction: "bullish" },
  ASTS:  { price: 31.80,  hv: 1.30,  trend_score: 61, iv_pct: 46, direction: "bullish" },
  SPY:   { price: 595.0,  hv: 0.18,  trend_score: 65, iv_pct: 22, direction: "bullish" },
  QQQ:   { price: 515.0,  hv: 0.22,  trend_score: 67, iv_pct: 25, direction: "bullish" },
};

const DEFAULT_DATA = { price: 150.0, hv: 0.45, trend_score: 60, iv_pct: 45, direction: "bullish" };

// ── Route ─────────────────────────────────────────────────────────────────────

export async function GET(req: Request, { params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  const data = SYMBOL_DATA[symbol] || DEFAULT_DATA;
  const { price: S, hv: sigma_annual, trend_score, iv_pct, direction } = data;

  // Use IV slightly above HV (typical premium)
  const iv = sigma_annual * (iv_pct > 60 ? 1.05 : iv_pct < 35 ? 0.90 : 0.98);

  const today = new Date();
  const expiries = [
    { label: "14d", dte: 14, date: new Date(today.getTime() + 14*86400000).toISOString().split("T")[0] },
    { label: "21d", dte: 21, date: new Date(today.getTime() + 21*86400000).toISOString().split("T")[0] },
    { label: "30d", dte: 30, date: new Date(today.getTime() + 30*86400000).toISOString().split("T")[0] },
  ];

  // Strike range: -12% to +20% ATM in ~2% steps
  const strike_offsets = direction === "bearish"
    ? [-0.20, -0.15, -0.10, -0.05, 0, 0.05, 0.10]
    : [-0.05, 0, 0.03, 0.06, 0.10, 0.14, 0.18, 0.22];

  const rows = [];

  for (const exp of expiries) {
    const T = exp.dte / 252;

    for (const offset of strike_offsets) {
      const K = Math.round(S * (1 + offset) / 0.5) * 0.5; // round to nearest $0.50
      const isCall = direction !== "bearish";

      // Option price
      let optPrice: number;
      if (isCall) {
        optPrice = bsCall(S, K, T, iv);
      } else {
        // put via put-call parity (simplified)
        optPrice = bsCall(S, K, T, iv) - S + K;
      }
      optPrice = Math.max(0.05, optPrice);
      const optMid = Math.round(optPrice * 100) / 100;

      const delta = isCall ? bsDelta(S, K, T, iv) : bsDelta(S, K, T, iv) - 1;
      const deltaAbs = Math.abs(delta);

      if (deltaAbs < 0.05 || optMid < 0.05) continue;

      // ── 30% gain target ────────────────────────────────────────────────
      // "30% gain" = option reaches 1.30× entry price
      // Before expiry (realistic): stock_move = (0.30 * optMid) / deltaAbs
      const move_for_30 = (0.30 * optMid) / deltaAbs;
      const target_stock_30 = isCall ? S + move_for_30 : S - move_for_30;
      const move_pct_30 = Math.abs(move_for_30 / S * 100);
      const prob_30 = isCall
        ? probReach(S, target_stock_30, T, iv)
        : probReach(target_stock_30, S, T, iv);  // for puts: prob stock falls to target

      // ── 100% gain target ───────────────────────────────────────────────
      const move_for_100 = (1.0 * optMid) / deltaAbs;
      const target_stock_100 = isCall ? S + move_for_100 : S - move_for_100;
      const move_pct_100 = Math.abs(move_for_100 / S * 100);
      const prob_100 = isCall
        ? probReach(S, target_stock_100, T, iv)
        : probReach(target_stock_100, S, T, iv);

      // ── Confidence score ───────────────────────────────────────────────
      let conf = 40;
      conf += Math.round((trend_score - 50) * 0.4);      // trend contribution ±8
      if (iv_pct < 35) conf += 12;                        // cheap options
      else if (iv_pct < 50) conf += 6;                    // reasonable
      else if (iv_pct > 65) conf -= 8;                    // expensive
      if (exp.dte >= 14 && exp.dte <= 21) conf += 6;     // sweet spot DTE
      else if (exp.dte < 7) conf -= 15;                   // too little time
      if (deltaAbs >= 0.35 && deltaAbs <= 0.55) conf += 8; // ATM = best risk/reward
      else if (deltaAbs < 0.15) conf -= 10;               // far OTM = speculative
      conf += Math.round(prob_30 * 0.15);                 // probability contribution
      conf = Math.max(10, Math.min(95, conf));

      // ── Recommendation flag ────────────────────────────────────────────
      const recommended = conf >= 60 && prob_30 >= 35 && exp.dte >= 14 && deltaAbs >= 0.25;

      rows.push({
        expiry: exp.date,
        dte: exp.dte,
        strike: K,
        type: isCall ? "call" : "put",
        option_price: optMid,
        iv_pct: Math.round(iv * 100),
        delta: Math.round(deltaAbs * 100) / 100,

        // 30% target
        target_price_30: Math.round(target_stock_30 * 100) / 100,
        move_pct_30: Math.round(move_pct_30 * 10) / 10,
        prob_30,
        conf_30: conf,

        // 100% target
        target_price_100: Math.round(target_stock_100 * 100) / 100,
        move_pct_100: Math.round(move_pct_100 * 10) / 10,
        prob_100: Math.max(2, prob_100),
        conf_100: Math.max(10, conf - 18),

        recommended,
        rationale: recommended
          ? `${exp.dte}d ${isCall ? "call" : "put"}, Δ${Math.round(deltaAbs*100)}: ${prob_30}% chance of +30% with ${move_pct_30.toFixed(1)}% underlying move needed`
          : "",
      });
    }
  }

  // Sort: recommended first, then by conf_30 desc
  rows.sort((a, b) => {
    if (a.recommended !== b.recommended) return a.recommended ? -1 : 1;
    return b.conf_30 - a.conf_30;
  });

  return NextResponse.json({
    symbol,
    current_price: S,
    iv_pct,
    hv20_pct: Math.round(sigma_annual * 100),
    direction,
    iv_vs_hv: iv_pct > sigma_annual * 100 ? "rich" : "cheap",
    rows,
    note: iv_pct > 65
      ? `⚠️ IV at ${iv_pct}th percentile — options are EXPENSIVE. Favor spreads over naked buys to cap cost.`
      : iv_pct < 35
      ? `✅ IV at ${iv_pct}th percentile — options are CHEAP. Good time to buy directional premium.`
      : `ℹ️ IV at ${iv_pct}th percentile — moderate pricing. Debit spreads balance cost vs upside.`,
  });
}
