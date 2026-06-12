// Shared mock data for all API routes

export const SCANNER_RESULTS = {
  scan_date: "2026-05-30T18:00:00Z",
  stage: 4,
  total_scanned: 4823,
  results: [
    {
      symbol: "NVDA", name: "NVIDIA Corporation", sector: "Semis/AI Chips",
      total_score: 84.2, direction: "bullish", conviction: 91,
      top_signals: ["IV Rank 68th pct", "Unusual call flow 3.2x avg", "GTC catalyst"],
      catalyst: "GTC 2026 Blackwell Ultra announcement May 28",
      stage3_flags: ["earnings_beat", "unusual_flow", "analyst_upgrade"],
      price: 1247.50, change_pct: 3.8,
    },
    {
      symbol: "INTC", name: "Intel Corporation", sector: "Semis/AI Chips",
      total_score: 79.1, direction: "bullish", conviction: 83,
      top_signals: ["Apple foundry deal confirmed", "ATH breakout", "Vol regime bullish"],
      catalyst: "Apple M5 foundry contract confirmed — 26yr ATH",
      stage3_flags: ["breakout", "analyst_upgrade", "political_alpha"],
      price: 89.40, change_pct: 5.2,
    },
    {
      symbol: "LLY", name: "Eli Lilly", sector: "Biotech/Pharma",
      total_score: 77.4, direction: "bullish", conviction: 79,
      top_signals: ["Medicare expansion Jul 2026", "GLP-1 dominant", "IV 42nd pct"],
      catalyst: "Medicare GLP-1 coverage expansion — July 2026",
      stage3_flags: ["catalyst_event", "earnings_beat"],
      price: 1053.20, change_pct: 1.9,
    },
    {
      symbol: "PLTR", name: "Palantir Technologies", sector: "AI Software",
      total_score: 73.8, direction: "bullish", conviction: 77,
      top_signals: ["$2B+ govt AI contracts", "Presidential alpha", "Strong OI"],
      catalyst: "DoD AIP+ contract expansion Q2 2026",
      stage3_flags: ["political_alpha", "govt_contract", "unusual_flow"],
      price: 43.80, change_pct: 2.4,
    },
    {
      symbol: "IONQ", name: "IonQ Inc", sector: "Quantum",
      total_score: 71.2, direction: "bullish", conviction: 74,
      top_signals: ["IBM CHIPS Act spillover", "Breakout from base", "Tech rotation"],
      catalyst: "IBM +12.7% quantum sector momentum",
      stage3_flags: ["sector_momentum", "breakout"],
      price: 38.60, change_pct: 7.1,
    },
    {
      symbol: "RDW", name: "Redwire Corporation", sector: "Space Economy",
      total_score: 68.5, direction: "bullish", conviction: 71,
      top_signals: ["SpaceX halo effect", "Call volume 176% avg", "DoD contract"],
      catalyst: "SpaceX S-1 filed May 20 — halo in full force",
      stage3_flags: ["ipo_halo", "unusual_flow", "govt_contract"],
      price: 24.15, change_pct: 4.3,
    },
    {
      symbol: "OKLO", name: "Oklo Inc", sector: "Nuclear/Energy",
      total_score: 66.9, direction: "bullish", conviction: 68,
      top_signals: ["DOE backing AI power grid", "Low IV 31st pct", "SMR momentum"],
      catalyst: "DOE $2B nuclear funding for AI data center power",
      stage3_flags: ["catalyst_event", "sector_momentum"],
      price: 52.30, change_pct: 3.1,
    },
    {
      symbol: "RACE", name: "Ferrari NV", sector: "Auto/EV",
      total_score: 62.1, direction: "bearish", conviction: 65,
      top_signals: ["Luce EV reveal dilution", "IV Rank 71st pct — sell premium", "Luxury brand bleed"],
      catalyst: "Ferrari Luce EV unveiled — luxury brand dilution put pattern",
      stage3_flags: ["catalyst_event", "pattern_signal"],
      price: 418.70, change_pct: -8.2,
    },
    {
      symbol: "ASTS", name: "AST SpaceMobile", sector: "Space Economy",
      total_score: 61.4, direction: "bullish", conviction: 63,
      top_signals: ["SpaceX halo", "Commercial satellite launch", "Low float squeeze"],
      catalyst: "Block 2 BlueBird satellite constellation launch",
      stage3_flags: ["ipo_halo", "catalyst_event"],
      price: 31.80, change_pct: 5.7,
    },
  ],
};

export const PAPER_TRADES = {
  trades: [
    {
      id: 1, symbol: "PLTR", strategy: "bull_call_spread", direction: "bullish",
      expiry: "2026-06-20", strike: 45, contracts: 3,
      entry_price: 2.85, exit_price: null,
      realized_pnl: null, unrealized_pnl: 312, r_multiple: null,
      status: "open",
      opened_at: "2026-05-27T14:23:00Z", closed_at: null,
      thesis: "DoD AIP+ contract expansion + presidential alpha — 45/50 bull call spread",
      entry_iv_rank: 44, entry_delta: 0.42,
    },
    {
      id: 2, symbol: "OKLO", strategy: "long_call", direction: "bullish",
      expiry: "2026-06-27", strike: 55, contracts: 2,
      entry_price: 3.40, exit_price: null,
      realized_pnl: null, unrealized_pnl: 180, r_multiple: null,
      status: "open",
      opened_at: "2026-05-28T15:10:00Z", closed_at: null,
      thesis: "DOE nuclear funding catalyst + SMR sector momentum, low IV 31st pct",
      entry_iv_rank: 31, entry_delta: 0.40,
    },
    {
      id: 3, symbol: "IONQ", strategy: "long_call", direction: "bullish",
      expiry: "2026-06-20", strike: 40, contracts: 5,
      entry_price: 2.20, exit_price: null,
      realized_pnl: null, unrealized_pnl: 540, r_multiple: null,
      status: "open",
      opened_at: "2026-05-29T13:45:00Z", closed_at: null,
      thesis: "IBM quantum CHIPS Act + sector rotation, breakout from 6-week base",
      entry_iv_rank: 38, entry_delta: 0.41,
    },
    {
      id: 4, symbol: "NVDA", strategy: "long_call", direction: "bullish",
      expiry: "2026-05-17", strike: 1200, contracts: 2,
      entry_price: 18.50, exit_price: 42.70,
      realized_pnl: 840, r_multiple: 2.3,
      status: "closed",
      opened_at: "2026-05-05T14:00:00Z", closed_at: "2026-05-14T15:30:00Z",
      thesis: "GTC catalyst + Blackwell pre-announcement unusual call flow",
      entry_iv_rank: 62, entry_delta: 0.38,
    },
    {
      id: 5, symbol: "INTC", strategy: "long_call", direction: "bullish",
      expiry: "2026-05-22", strike: 80, contracts: 4,
      entry_price: 4.20, exit_price: 11.20,
      realized_pnl: 1200, r_multiple: 3.1,
      status: "closed",
      opened_at: "2026-04-28T13:30:00Z", closed_at: "2026-05-12T14:10:00Z",
      thesis: "Apple foundry deal rumor + ATH breakout confirmation",
      entry_iv_rank: 41, entry_delta: 0.40,
    },
    {
      id: 6, symbol: "RACE", strategy: "long_put", direction: "bearish",
      expiry: "2026-05-29", strike: 420, contracts: 1,
      entry_price: 9.80, exit_price: 8.00,
      realized_pnl: -180, r_multiple: -0.5,
      status: "closed",
      opened_at: "2026-05-22T14:00:00Z", closed_at: "2026-05-28T15:00:00Z",
      thesis: "Ferrari Luce EV luxury brand dilution pattern — IV 71st pct too high, put premium ate P&L",
      entry_iv_rank: 71, entry_delta: -0.38,
    },
  ],
};

export const JOURNAL_ENTRIES = [
  {
    id: 1,
    trade_id: 5,
    symbol: "INTC",
    lesson: "Apple foundry deal was the real alpha — got in 2 weeks before confirmation. Political alpha signal (presidential OGE disclosure was the early tell) combined with unusual call flow 3 days prior. This combo is repeatable: OGE purchase + unusual flow = high-confidence lead time.",
    outcome: "win",
    r_multiple: 3.1,
    factors_that_fired: ["political_alpha", "unusual_flow", "breakout"],
    factors_that_missed: [],
    created_at: "2026-05-12T16:00:00Z",
    regime_at_entry: "bull_trend",
  },
  {
    id: 2,
    trade_id: 4,
    symbol: "NVDA",
    lesson: "GTC catalyst plays work best when IV rank is between 55-70th pct — expensive enough that market has priced in *something* but not so elevated that premium decay kills you. Entered at 62nd pct, which ate into profits but still won 2.3R. Next time: if IV rank >65, consider bull call spread instead of naked long call.",
    outcome: "win",
    r_multiple: 2.3,
    factors_that_fired: ["catalyst_event", "unusual_flow", "trend"],
    factors_that_missed: ["iv_analysis"],
    created_at: "2026-05-14T16:30:00Z",
    regime_at_entry: "bull_trend",
  },
  {
    id: 3,
    trade_id: 6,
    symbol: "RACE",
    lesson: "RACE put was thesis-correct but structure was wrong. IV rank at 71st pct meant I should have SOLD the put premium (bear put spread or naked put), not bought it. Put cost $9.80, decay ate most of the move. Rule going forward: IV rank >60 → sell premium. Directional bias correct, vehicle choice wrong.",
    outcome: "loss",
    r_multiple: -0.5,
    factors_that_fired: ["catalyst_event", "iv_analysis"],
    factors_that_missed: ["trade_structure"],
    created_at: "2026-05-28T16:00:00Z",
    regime_at_entry: "high_vol",
  },
  {
    id: 4,
    trade_id: null,
    symbol: "GENERAL",
    lesson: "Cross-stock analysis insight: when 3+ semis hit the scanner simultaneously (NVDA, INTC, AMD all this week), it's a rotation signal — not three independent setups. Size each one at 50% of normal because they're correlated. Treating them as independent was a sizing mistake.",
    outcome: null,
    r_multiple: null,
    factors_that_fired: ["portfolio_correlation"],
    factors_that_missed: [],
    created_at: "2026-05-20T10:00:00Z",
    regime_at_entry: "bull_trend",
  },
  {
    id: 5,
    trade_id: null,
    symbol: "GENERAL",
    lesson: "SpaceX halo plays (RDW +165%, ASTS, RKLB) confirm the IPO halo pattern is real. RDW call volume spiked 176% three days before the S-1 announcement. Pre-announcement unusual flow is the strongest lead indicator in the system. Add: if a halo stock has >150% call volume AND the IPO filing date is within 30 days, auto-bump to Stage 4.",
    outcome: null,
    r_multiple: null,
    factors_that_fired: ["ipo_halo", "unusual_flow"],
    factors_that_missed: [],
    created_at: "2026-05-25T11:00:00Z",
    regime_at_entry: "bull_trend",
  },
];

export const IC_WEIGHTS = [
  { category: "iv_analysis", display_name: "IV & Volatility", base_weight: 0.12, ic_score: 0.082, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
  { category: "options_chain", display_name: "Options Chain Selection", base_weight: 0.10, ic_score: 0.074, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
  { category: "trend", display_name: "Trend & Market Structure", base_weight: 0.10, ic_score: 0.091, multiplier: 1.1, trade_count: 48, regime: "bull_trend" },
  { category: "fundamental", display_name: "Fundamental & Catalyst", base_weight: 0.08, ic_score: 0.068, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
  { category: "support_resistance", display_name: "Support & Resistance", base_weight: 0.08, ic_score: 0.055, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
  { category: "greeks", display_name: "Greeks", base_weight: 0.08, ic_score: 0.071, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
  { category: "macro", display_name: "Market & Macro", base_weight: 0.08, ic_score: 0.043, multiplier: 0.9, trade_count: 48, regime: "bull_trend" },
  { category: "candles", display_name: "Candlestick Patterns", base_weight: 0.07, ic_score: 0.038, multiplier: 0.8, trade_count: 48, regime: "bull_trend" },
  { category: "chart_patterns", display_name: "Chart Patterns", base_weight: 0.07, ic_score: 0.051, multiplier: 0.9, trade_count: 48, regime: "bull_trend" },
  { category: "momentum", display_name: "Volume & Momentum", base_weight: 0.07, ic_score: 0.079, multiplier: 1.1, trade_count: 48, regime: "bull_trend" },
  { category: "calendar", display_name: "Seasonality & Calendar", base_weight: 0.07, ic_score: 0.029, multiplier: 0.5, trade_count: 48, regime: "bull_trend" },
  { category: "trade_structure", display_name: "Trade Structure", base_weight: 0.05, ic_score: 0.088, multiplier: 1.1, trade_count: 48, regime: "bull_trend" },
  { category: "sentiment", display_name: "Sentiment & Smart Money", base_weight: 0.05, ic_score: 0.062, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
  { category: "liquidity", display_name: "Liquidity & Execution", base_weight: 0.05, ic_score: 0.045, multiplier: 0.9, trade_count: 48, regime: "bull_trend" },
  { category: "risk", display_name: "Risk Management", base_weight: 0.05, ic_score: 0.071, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
  { category: "dow_bias", display_name: "Day of Week Bias", base_weight: 0.04, ic_score: 0.022, multiplier: 0.5, trade_count: 48, regime: "bull_trend" },
  { category: "gex_dex", display_name: "GEX/DEX Dealer Flow", base_weight: 0.0, ic_score: 0.094, multiplier: 1.2, trade_count: 48, regime: "bull_trend" },
  { category: "options_flow", display_name: "Institutional Options Flow", base_weight: 0.0, ic_score: 0.087, multiplier: 1.2, trade_count: 48, regime: "bull_trend" },
  { category: "volatility_regime", display_name: "Volatility Regime", base_weight: 0.0, ic_score: 0.076, multiplier: 1.1, trade_count: 48, regime: "bull_trend" },
  { category: "earnings_adj_iv", display_name: "Earnings-Adjusted IV", base_weight: 0.0, ic_score: 0.069, multiplier: 1.0, trade_count: 48, regime: "bull_trend" },
];

export const POLITICAL_DISCLOSURES = {
  disclosures: [
    {
      id: 1,
      filer: "Donald J. Trump",
      ticker: "NVDA",
      transaction_type: "purchase",
      amount_range: "$500K–$1M",
      disclosure_date: "2026-04-15",
      trade_date: "2026-04-10",
      related_event: "White House AI executive order + NVDA mentioned in briefing",
      price_at_trade: 1102.00,
      price_now: 1247.50,
      pct_move: 13.2,
      signal_strength: 8,
    },
    {
      id: 2,
      filer: "Donald J. Trump",
      ticker: "PLTR",
      transaction_type: "purchase",
      amount_range: "$250K–$500K",
      disclosure_date: "2026-03-28",
      trade_date: "2026-03-20",
      related_event: "DoD AIP+ contract announcement 8 days after purchase",
      price_at_trade: 34.20,
      price_now: 43.80,
      pct_move: 28.1,
      signal_strength: 9,
    },
    {
      id: 3,
      filer: "Donald J. Trump",
      ticker: "META",
      transaction_type: "purchase",
      amount_range: "$100K–$250K",
      disclosure_date: "2026-05-01",
      trade_date: "2026-04-25",
      related_event: "Llama 4 federal contract discussions reported",
      price_at_trade: 578.00,
      price_now: 621.40,
      pct_move: 7.5,
      signal_strength: 6,
    },
  ],
  total_transactions_q1_2026: 3647,
  tracking_since: "2026-01-20",
};

// Deterministic OHLCV generator using LCG seeded by symbol
function seedRandom(symbol: string) {
  let seed = symbol.split("").reduce((a, c) => a + c.charCodeAt(0), 0) * 1234567;
  return () => {
    seed = (seed * 1664525 + 1013904223) & 0xffffffff;
    return (seed >>> 0) / 0xffffffff;
  };
}

const PRICE_CONFIGS: Record<string, { base: number; trend: number; vol: number }> = {
  NVDA: { base: 1100, trend: 0.003, vol: 0.025 },
  INTC: { base: 72, trend: 0.004, vol: 0.030 },
  LLY:  { base: 1010, trend: 0.002, vol: 0.018 },
  PLTR: { base: 36, trend: 0.003, vol: 0.035 },
  IONQ: { base: 28, trend: 0.005, vol: 0.045 },
  RDW:  { base: 16, trend: 0.006, vol: 0.055 },
  OKLO: { base: 43, trend: 0.004, vol: 0.042 },
  RACE: { base: 460, trend: -0.002, vol: 0.022 },
  ASTS: { base: 22, trend: 0.005, vol: 0.060 },
};

export function generateOHLCV(symbol: string, days = 90) {
  const config = PRICE_CONFIGS[symbol] || { base: 100, trend: 0.001, vol: 0.02 };
  const rand = seedRandom(symbol);
  const candles = [];
  let price = config.base;
  const now = new Date("2026-05-30");

  for (let i = days; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    // skip weekends
    if (date.getDay() === 0 || date.getDay() === 6) continue;

    const move = (rand() - 0.48) * config.vol + config.trend;
    const open = price;
    const close = price * (1 + move);
    const high = Math.max(open, close) * (1 + rand() * config.vol * 0.5);
    const low  = Math.min(open, close) * (1 - rand() * config.vol * 0.5);
    const volume = Math.round((500000 + rand() * 4500000) * (symbol === "NVDA" ? 8 : 1));

    candles.push({
      time: date.toISOString().split("T")[0],
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low:  parseFloat(low.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
      volume,
    });
    price = close;
  }
  return candles;
}

export const NVDA_ANALYSIS = {
  category_scores: {
    trend: {
      name: "Trend & Market Structure", weight: 0.10,
      raw_score: 9.0, weighted_score: 0.90, direction: "bullish",
      signals: [
        { name: "EMA 8/21/50/200 all aligned bullish", direction: "bullish" },
        { name: "Higher highs / higher lows confirmed", direction: "bullish" },
        { name: "Price +18% above 50-day EMA", direction: "bullish", note: "Extended — watch for mean reversion" },
        { name: "ADX 42 — strong trend", direction: "bullish" },
      ],
      summary: "Dominant uptrend intact. Four consecutive HH/HL on daily timeframe since GTC announcement.",
    },
    momentum: {
      name: "Volume & Momentum", weight: 0.07,
      raw_score: 8.5, weighted_score: 0.595, direction: "bullish",
      signals: [
        { name: "RSI 14d: 68 (approaching OB, not yet)", direction: "bullish" },
        { name: "MACD bullish crossover 3 days ago", direction: "bullish" },
        { name: "OBV rising — accumulation pattern", direction: "bullish" },
        { name: "Volume +340% on GTC announcement day", direction: "bullish" },
      ],
      summary: "Strong accumulation. Volume confirms price action. RSI not yet overbought.",
    },
    iv_analysis: {
      name: "IV & Volatility", weight: 0.12,
      raw_score: 7.5, weighted_score: 0.90, direction: "bullish",
      signals: [
        { name: "IV Rank: 68th pct — elevated but not extreme", direction: "neutral" },
        { name: "IV vs HV: IV premium 28% over 30d HV", direction: "bearish", note: "Options expensive — consider spread" },
        { name: "Call skew bullish (25Δ call > 25Δ put IV)", direction: "bullish" },
        { name: "Term structure backwardation — near-term demand", direction: "bullish" },
        { name: "Expected move (30 DTE): ±$87 (6.9%)", direction: "neutral" },
      ],
      summary: "IV elevated due to GTC hype. Premium buyers beware — bull call spread preferred over naked long call.",
    },
    options_chain: {
      name: "Options Chain Selection", weight: 0.10,
      raw_score: 8.0, weighted_score: 0.80, direction: "bullish",
      signals: [
        { name: "Call OI 5.2x put OI at ATM strike", direction: "bullish" },
        { name: "June 1250C bid-ask: $38.20/$39.10 (2.3% spread)", direction: "bullish" },
        { name: "Unusual call volume: 1250/1300 strikes 3.2x avg", direction: "bullish" },
        { name: "Recommended: Jun 20 1250/1300 bull call spread", direction: "bullish" },
      ],
      summary: "Strong call demand at OTM strikes. Spread <3% — good liquidity. Unusual flow concentrated at 1250/1300.",
    },
    fundamental: {
      name: "Fundamental & Catalyst", weight: 0.08,
      raw_score: 9.0, weighted_score: 0.72, direction: "bullish",
      signals: [
        { name: "GTC 2026: Blackwell Ultra announced May 28", direction: "bullish" },
        { name: "Q1 FY2027 EPS: $0.96 vs $0.85 est (+13%)", direction: "bullish" },
        { name: "Data center revenue $26.1B (+122% YoY)", direction: "bullish" },
        { name: "Analyst consensus: 47 Buy, 2 Hold, 0 Sell", direction: "bullish" },
        { name: "FMP price target consensus: $1,450 (+16%)", direction: "bullish" },
      ],
      summary: "Exceptional fundamentals. Blackwell Ultra launch is the next product catalyst. Analyst community overwhelmingly bullish.",
    },
    support_resistance: {
      name: "Support & Resistance", weight: 0.08,
      raw_score: 7.5, weighted_score: 0.60, direction: "bullish",
      signals: [
        { name: "Key support: $1,180 (prior ATH breakout level)", direction: "bullish" },
        { name: "VWAP: $1,212 — price above VWAP", direction: "bullish" },
        { name: "Next resistance: $1,320 (Fibonacci 1.618 ext)", direction: "neutral" },
        { name: "Gap fill risk: gap at $1,148 from May 22", direction: "bearish", note: "70% of gaps fill within 30 days" },
      ],
      summary: "Clean support at $1,180. Room to $1,320 before next major resistance. Gap below is a risk.",
    },
    greeks: {
      name: "Greeks", weight: 0.08,
      raw_score: 8.0, weighted_score: 0.64, direction: "bullish",
      signals: [
        { name: "ATM delta: 0.52 — slightly above neutral", direction: "bullish" },
        { name: "Gamma: 0.0012 — moderate acceleration zone", direction: "neutral" },
        { name: "Theta/day on Jun 1250C: -$0.87 (4.7% of premium)", direction: "bearish" },
        { name: "Vega: $2.31 — significant vol exposure", direction: "neutral" },
      ],
      summary: "Favorable delta profile. Theta manageable at 4.7%/day for swing trade. Vega exposure means IV compression risk.",
    },
    macro: {
      name: "Market & Macro", weight: 0.08,
      raw_score: 7.0, weighted_score: 0.56, direction: "bullish",
      signals: [
        { name: "SPY above 50/200 EMA — bull regime", direction: "bullish" },
        { name: "QQQ relative strength: +3.2% vs SPY MTD", direction: "bullish" },
        { name: "VIX: 14.8 — calm regime, favors directional buys", direction: "bullish" },
        { name: "10yr yield: 4.12% — stable, not headwind", direction: "neutral" },
        { name: "DXY weakening — tailwind for tech multinationals", direction: "bullish" },
      ],
      summary: "Macro backdrop favorable. Low VIX + tech sector leadership + weak dollar = ideal for NVDA directional play.",
    },
    candles: {
      name: "Candlestick Patterns", weight: 0.07,
      raw_score: 7.0, weighted_score: 0.49, direction: "bullish",
      signals: [
        { name: "Three white soldiers (May 26-28)", direction: "bullish" },
        { name: "Bullish engulfing on May 22 dip", direction: "bullish" },
        { name: "No bearish reversal patterns in 10d", direction: "bullish" },
      ],
      summary: "Clean bullish candle structure. Three white soldiers post-GTC with no reversal signals.",
    },
    chart_patterns: {
      name: "Chart Patterns", weight: 0.07,
      raw_score: 8.0, weighted_score: 0.56, direction: "bullish",
      signals: [
        { name: "Bull flag breakout — 6-week consolidation → breakout", direction: "bullish" },
        { name: "Volume confirmation on breakout: 2.8x avg", direction: "bullish" },
        { name: "Measured move target: $1,380", direction: "bullish" },
        { name: "No H&S or distribution patterns", direction: "bullish" },
      ],
      summary: "Textbook bull flag. 6-week base at $1,100–$1,165, broke out May 28 on 2.8x volume. Measured move to $1,380.",
    },
    trade_structure: {
      name: "Trade Structure", weight: 0.05,
      raw_score: 8.0, weighted_score: 0.40, direction: "bullish",
      signals: [
        { name: "IV Rank 68 → prefer spread over naked long", direction: "neutral" },
        { name: "Bull call spread: Jun 1250/1300 — defined risk", direction: "bullish" },
        { name: "Max profit $5,000 per lot at expiry above $1,300", direction: "bullish" },
        { name: "Max loss: $2,200 per lot (debit paid)", direction: "neutral" },
      ],
      summary: "IV rank warrants spread structure. 1250/1300 bull call spread optimal: defined risk, 2.3R potential.",
    },
    sentiment: {
      name: "Sentiment & Smart Money", weight: 0.05,
      raw_score: 8.5, weighted_score: 0.425, direction: "bullish",
      signals: [
        { name: "Dark pool: $48M call premium vs $12M put (4:1)", direction: "bullish" },
        { name: "Smart money flow score: 87/100", direction: "bullish" },
        { name: "WSB mentions moderate (not crowded)", direction: "neutral" },
        { name: "YT influencer mentions: 2 (below crowding threshold)", direction: "neutral" },
      ],
      summary: "Institutional money flowing in. Dark pool skew 4:1 bullish. Not yet crowded on retail channels.",
    },
    liquidity: {
      name: "Liquidity & Execution", weight: 0.05,
      raw_score: 9.0, weighted_score: 0.45, direction: "bullish",
      signals: [
        { name: "OI: 285,000 contracts on June series", direction: "bullish" },
        { name: "Bid-ask spread: 2.3% of mid — excellent", direction: "bullish" },
        { name: "Average daily options volume: $2.1B notional", direction: "bullish" },
        { name: "SmartPricing estimate: fill at mid likely", direction: "bullish" },
      ],
      summary: "Best-in-class options liquidity. Fill at mid is realistic. No liquidity risk.",
    },
    risk: {
      name: "Risk Management", weight: 0.05,
      raw_score: 7.5, weighted_score: 0.375, direction: "neutral",
      signals: [
        { name: "Suggested position: 2 lots (3% of portfolio)", direction: "neutral" },
        { name: "R/R ratio: 2.3:1 (target $840 / risk $365 per lot)", direction: "bullish" },
        { name: "Portfolio heat: 22% deployed — under 30% limit", direction: "bullish" },
        { name: "Correlated open positions: IONQ (low 0.21 corr)", direction: "neutral" },
      ],
      summary: "Risk parameters clean. Portfolio under heat limit. Low correlation to existing open positions.",
    },
    calendar: {
      name: "Seasonality & Calendar", weight: 0.07,
      raw_score: 6.5, weighted_score: 0.455, direction: "neutral",
      signals: [
        { name: "May-June historically bullish for semis (+3.1% avg)", direction: "bullish" },
        { name: "No earnings until Aug — catalyst risk cleared", direction: "bullish" },
        { name: "FOMC June 11 — moderate macro risk event", direction: "bearish" },
        { name: "Memorial Day week historically low volume", direction: "neutral" },
      ],
      summary: "Seasonal tailwind. Earnings cleared. FOMC June 11 is a known risk — expire before or plan around it.",
    },
    dow_bias: {
      name: "Day of Week Bias", weight: 0.04,
      raw_score: 6.0, weighted_score: 0.24, direction: "neutral",
      signals: [
        { name: "Friday 53% positive close rate for NVDA (3yr)", direction: "bullish" },
        { name: "Monday 48% — slight negative bias", direction: "bearish" },
        { name: "Current entry: Friday — mild favorable", direction: "bullish" },
      ],
      summary: "Minor Friday tailwind. DOW bias is low-conviction signal — supplementary only.",
    },
    gex_dex: {
      name: "GEX/DEX Dealer Flow", weight: 0.0,
      raw_score: 8.5, weighted_score: 0.0, direction: "bullish",
      signals: [
        { name: "GEX: +$2.8B — positive, dealers dampen moves", direction: "neutral" },
        { name: "DEX: +$420M net long dealer delta", direction: "bullish" },
        { name: "Vanna flow: calls in the money → dealer buy pressure", direction: "bullish" },
        { name: "GEX flip level: $1,180 — below this, moves amplify", direction: "neutral" },
      ],
      summary: "Positive GEX means market makers are a stabilizing force above $1,180. Vanna buying pressure supports upward moves.",
    },
    options_flow: {
      name: "Institutional Options Flow", weight: 0.0,
      raw_score: 9.0, weighted_score: 0.0, direction: "bullish",
      signals: [
        { name: "Block print: 500x Jun 1250C at ask — $1.95M", direction: "bullish" },
        { name: "Block print: 200x Jun 1300C at ask — $680K", direction: "bullish" },
        { name: "Put/Call ratio (OI): 0.31 — strong call skew", direction: "bullish" },
        { name: "Dark pool divergence: DP buying while price consolidates", direction: "bullish" },
      ],
      summary: "Exceptional institutional flow. Two large block call purchases at ask = directional conviction. P/C ratio 0.31.",
    },
    volatility_regime: {
      name: "Volatility Regime", weight: 0.0,
      raw_score: 7.5, weighted_score: 0.0, direction: "bullish",
      signals: [
        { name: "Current regime: BULL_TREND (VIX 14.8, SPY above 50d)", direction: "bullish" },
        { name: "Realized vol: 28% (vs 30-day HV 31%) — normalizing", direction: "neutral" },
        { name: "Regime weight: momentum IC boosted +10%", direction: "bullish" },
      ],
      summary: "Bull trend regime confirmed. Momentum and trend factors get IC weight boost. Favorable for directional calls.",
    },
    earnings_adj_iv: {
      name: "Earnings-Adjusted IV", weight: 0.0,
      raw_score: 7.0, weighted_score: 0.0, direction: "neutral",
      signals: [
        { name: "Earnings in 78 days — no near-term IV spike", direction: "bullish" },
        { name: "Earnings-adjusted IV rank: 61 (vs raw 68)", direction: "neutral" },
        { name: "Base IV (ex-earnings premium): 34%", direction: "neutral" },
      ],
      summary: "After stripping earnings component, true base IV rank is 61 — still elevated but less than raw suggests.",
    },
  },
  total_score: 84.2,
  direction: "bullish",
  conviction_score: 91,
  trader_thesis: `## Trade Thesis: NVDA — Bull Call Spread

**EDGE**: GTC 2026 Blackwell Ultra announcement (May 28) is an underappreciated catalyst. The market initially gapped up but has since consolidated in a tight bull flag — this is institutional accumulation, not distribution. Dark pool block prints (500x 1250C + 200x 1300C at the ask) confirm smart money is positioned for continuation.

**DIRECTION**: Bullish. Four-factor confirmation: trend (ADX 42, all EMAs aligned), unusual call flow (3.2x average at OTM strikes), GEX structure (positive, dealers will chase price higher above $1,265), and macro tailwind (low VIX, weak dollar, tech sector leadership).

**STRUCTURE**: Bull call spread preferred over naked long call. IV rank at 68th pct means premium is expensive — spreading reduces vega exposure by 60% while keeping directional leverage.

**TIMING**: Enter on any pullback to $1,220-$1,240 (VWAP support). June expiry (22 DTE) captures the post-GTC momentum window. Exit at 50% of max profit (~$1,275) or hold to $1,300 target.

**RISK**: Gap at $1,148 from May 22 represents 7% downside risk if macro deteriorates. FOMC June 11 is an event risk — the spread's defined nature handles this well. Max loss is the debit paid.`,
  risk_assessment: `**Portfolio Risk Check: CLEAR ✓**

- Portfolio heat: 22% deployed (limit: 30%) — 8% headroom
- Semis sector exposure: 1 position (IONQ at 3%) — adding NVDA brings to 6%, well under 35% sector limit
- Net delta: +0.18 across portfolio — adding NVDA +0.40Δ brings to +0.22 (under 0.60 cap)
- Correlation with IONQ: 0.21 (low — treated as independent positions)
- Suggested size: **2 lots** = $4,400 max risk = 2.9% of $150K paper account

**Freshness**: Data as of 2026-05-30 15:47 ET. Price $1,247.50. IV rank 68. All signals valid.`,
  order_ticket: {
    symbol: "NVDA",
    strategy: "bull_call_spread",
    direction: "bullish",
    expiry: "2026-06-20",
    short_strike: null,
    long_strike: 1250,
    second_strike: 1300,
    target_delta: 0.42,
    bid: 22.10,
    ask: 22.80,
    mid: 22.45,
    max_profit: 2755,
    max_loss: 2245,
    profit_target_pct: 50,
    stop_loss_pct: 50,
    suggested_contracts: 2,
    stream: "alpha",
    thesis_summary: "GTC Blackwell Ultra + unusual call block prints + bull flag breakout. IV 68th pct → spread structure. Enter $1,220-$1,240 VWAP support.",
    freshness_valid: true,
    freshness_checked_at: "2026-05-30T15:47:00Z",
    return_projection: {
      stream: "alpha",
      entry_price: 22.45,
      target_price_10x: 224.50,
      target_price_50pct: 33.68,
      expected_value_pct: 143.0,
      confidence_pct: 91,
      stream_rationale: "High-conviction alpha play: entry $22.45. Bull case exits at $47.80 (+113%). Base case at $28.90 (+29%). Full risk = max debit paid.",
      scenarios: [
        { name: "bear",  underlying_move_pct: -6.2, option_price_exit: 0.00, return_pct: -100.0, probability: 0.18 },
        { name: "base",  underlying_move_pct: 3.8,  option_price_exit: 28.90, return_pct: 28.7,  probability: 0.47 },
        { name: "bull",  underlying_move_pct: 9.1,  option_price_exit: 47.80, return_pct: 112.9, probability: 0.35 },
      ],
    },
  },
};

// ── Watchlist Mock Data ───────────────────────────────────────────────────────

export const WATCHLIST_STATE = [
  {
    symbol: "NVDA", added_at: "2026-05-01T00:00:00Z",
    last_refreshed: "2026-05-30T15:45:00Z",
    current_score: 84.2, prev_score: 76.5, current_direction: "bullish",
    current_price: 1247.50, iv_rank: 68.0, regime: "bull_trend",
    total_trades: 5, wins: 4, losses: 1, win_rate: 80.0, avg_r_multiple: 2.1,
    active_alerts: [{ type: "high_conviction", message: "NVDA: Score 84/100 — high-conviction bullish setup", severity: "info" }],
    score_history: Array.from({ length: 24 }, (_, i) => ({
      ts: new Date(Date.now() - (23 - i) * 30 * 60 * 1000).toISOString(),
      score: 68 + Math.round(Math.sin(i * 0.4) * 8 + i * 0.7),
      direction: "bullish",
    })),
    ticker_lessons: [
      { lesson: "GTC catalyst plays work best at IV rank 55-70. Entry at 62nd pct ate into profits but still won 2.3R.", r_multiple: 2.3, regime: "bull_trend", factors: ["catalyst_event", "trend"], date: "2026-05-14" },
      { lesson: "Always enter NVDA during VWAP pullbacks — momentum continuation beats mean reversion for this name.", r_multiple: 1.8, regime: "bull_trend", factors: ["trend", "momentum"], date: "2026-05-05" },
    ],
    factor_overrides: { trend: { ic: 0.091, count: 5 }, iv_analysis: { ic: 0.082, count: 5 } },
    notes: "Best entry: VWAP pullbacks on GTC/analyst upgrade catalysts. IV >65 → use spread, not naked call.",
  },
  {
    symbol: "PLTR", added_at: "2026-05-10T00:00:00Z",
    last_refreshed: "2026-05-30T15:45:00Z",
    current_score: 73.8, prev_score: 71.2, current_direction: "bullish",
    current_price: 43.80, iv_rank: 44.0, regime: "bull_trend",
    total_trades: 2, wins: 2, losses: 0, win_rate: 100.0, avg_r_multiple: 1.9,
    active_alerts: [],
    score_history: Array.from({ length: 24 }, (_, i) => ({
      ts: new Date(Date.now() - (23 - i) * 30 * 60 * 1000).toISOString(),
      score: 65 + Math.round(Math.sin(i * 0.3) * 5 + i * 0.4),
      direction: "bullish",
    })),
    ticker_lessons: [
      { lesson: "Presidential OGE purchase → follow with 30-60 DTE calls. Timing is 8-14 days ahead of govt deal.", r_multiple: 2.8, regime: "bull_trend", factors: ["political_alpha", "unusual_flow"], date: "2026-05-12" },
    ],
    factor_overrides: { political_alpha: { ic: 0.12, count: 2 } },
    notes: "Monitor OGE filings weekly. Political alpha + unusual flow is the repeatable edge on PLTR.",
  },
  {
    symbol: "IONQ", added_at: "2026-05-20T00:00:00Z",
    last_refreshed: "2026-05-30T15:45:00Z",
    current_score: 71.2, prev_score: 63.8, current_direction: "bullish",
    current_price: 38.60, iv_rank: 38.0, regime: "bull_trend",
    total_trades: 1, wins: 1, losses: 0, win_rate: 100.0, avg_r_multiple: 0.0,
    active_alerts: [{ type: "score_change", delta: 7.4, severity: "info", message: "IONQ: Score moved +7.4 points → 71.2/100" }],
    score_history: Array.from({ length: 24 }, (_, i) => ({
      ts: new Date(Date.now() - (23 - i) * 30 * 60 * 1000).toISOString(),
      score: 55 + Math.round(i * 0.7 + Math.sin(i * 0.5) * 4),
      direction: i > 16 ? "bullish" : "neutral",
    })),
    ticker_lessons: [],
    factor_overrides: {},
    notes: "Quantum sector momentum play. Watch for IBM / Google quantum news. Low float = sharp moves.",
  },
  {
    symbol: "RACE", added_at: "2026-05-22T00:00:00Z",
    last_refreshed: "2026-05-30T15:45:00Z",
    current_score: 62.1, prev_score: 70.3, current_direction: "bearish",
    current_price: 418.70, iv_rank: 71.0, regime: "high_vol",
    total_trades: 1, wins: 0, losses: 1, win_rate: 0.0, avg_r_multiple: -0.5,
    active_alerts: [],
    score_history: Array.from({ length: 24 }, (_, i) => ({
      ts: new Date(Date.now() - (23 - i) * 30 * 60 * 1000).toISOString(),
      score: 72 - Math.round(i * 0.4 + Math.sin(i * 0.6) * 3),
      direction: "bearish",
    })),
    ticker_lessons: [
      { lesson: "IV rank 71 → sell premium (bear put spread), not buy puts. Bought wrong vehicle — thesis correct but lost.", r_multiple: -0.5, regime: "high_vol", factors: ["iv_analysis"], date: "2026-05-28" },
    ],
    factor_overrides: { trade_structure: { ic: 0.10, count: 1 } },
    notes: "Luxury brand + forced EV reveal = bearish pattern. Always use spreads on IV >65. Don't buy straight puts.",
  },
];

// ── Influencers Mock Data ─────────────────────────────────────────────────────

export const INFLUENCERS_DATA = {
  channels: [
    {
      channel_id: "UC_InvestorsEdge", name: "Investors Edge", platform: "YouTube",
      credibility_score: 0.81, total_calls: 94, correct: 76, incorrect: 18,
      specialty: "Large-cap momentum, semis", tracked_since: "2025-06-01",
      latest_pick: { ticker: "NVDA", direction: "bullish", date: "2026-05-28", outcome: "open",
        reasoning_type: "quantitative", pre_video_call_volume_ratio: 1.3 },
      black_sheep: false,
      description: "Strong track record on semis and AI infrastructure names. Uses technical + earnings flow.",
    },
    {
      channel_id: "UC_OptionAlpha", name: "Options Flow Pro", platform: "YouTube",
      credibility_score: 0.73, total_calls: 61, correct: 45, incorrect: 16,
      specialty: "Options flow, unusual activity", tracked_since: "2025-08-01",
      latest_pick: { ticker: "PLTR", direction: "bullish", date: "2026-05-25", outcome: "win",
        reasoning_type: "flow_analysis", pre_video_call_volume_ratio: 2.1 },
      black_sheep: false,
      description: "Focuses on unusual options volume and dark pool. Pre-video flow ratio of 2.1 on PLTR flagged.",
    },
    {
      channel_id: "UC_MomentumMike", name: "Momentum Mike", platform: "YouTube",
      credibility_score: 0.54, total_calls: 38, correct: 21, incorrect: 17,
      specialty: "Meme stocks, high volatility", tracked_since: "2025-10-01",
      latest_pick: { ticker: "ASTS", direction: "bullish", date: "2026-05-29", outcome: "open",
        reasoning_type: "narrative", pre_video_call_volume_ratio: 0.9 },
      black_sheep: false,
      description: "Decent win rate but primarily narrative-driven. Apply 20% score discount when 3+ channels agree.",
    },
    {
      channel_id: "UC_PumpDetector", name: "Penny Stock Hunter", platform: "YouTube",
      credibility_score: 0.22, total_calls: 55, correct: 12, incorrect: 43,
      specialty: "Small-cap, OTC, meme", tracked_since: "2025-07-01",
      latest_pick: { ticker: "RKLB", direction: "bullish", date: "2026-05-30", outcome: "open",
        reasoning_type: "hype", pre_video_call_volume_ratio: 3.8 },
      black_sheep: true,
      black_sheep_signal: "Credibility 0.22 + strong bullish call + pre-video call flow 3.8× avg = potential fade/pump signal",
      description: "⚠️ BLACK SHEEP: Low credibility + strong recent call + elevated pre-video options flow. Consider contrarian fade.",
    },
    {
      channel_id: "UC_QuantEdge", name: "Quant Edge", platform: "YouTube",
      credibility_score: 0.87, total_calls: 112, correct: 98, incorrect: 14,
      specialty: "Factor models, earnings plays, IV strategies", tracked_since: "2025-05-01",
      latest_pick: { ticker: "LLY", direction: "bullish", date: "2026-05-27", outcome: "win",
        reasoning_type: "quantitative", pre_video_call_volume_ratio: 1.1 },
      black_sheep: false,
      description: "Highest credibility in tracking. Quantitative basis for all calls. Consistent with our factor model.",
    },
  ],
  crowding_alerts: [
    { tickers: ["RDW", "ASTS", "RKLB"], mention_count: 4, week: "2026-W22",
      message: "3 space stocks mentioned by 4 channels in same week — crowding risk. Apply -20% score discount." },
  ],
  pre_video_flow_alerts: [
    { ticker: "RKLB", channel: "Penny Stock Hunter", call_volume_ratio: 3.8, days_before: 1,
      message: "Unusual 3.8× call volume on RKLB 1 day before video publish — potential pump coordination signal." },
  ],
};

// ── Backtest Mock Results ─────────────────────────────────────────────────────

export const BACKTEST_RESULTS = {
  run_date: "2026-05-30",
  period: "2024-06-01 to 2026-05-30 (24 months)",
  total_simulated_trades: 847,
  win_rate: 64.2,
  avg_r_multiple: 1.34,
  total_return_pct: 287.4,
  max_drawdown_pct: 18.3,
  sharpe_ratio: 1.82,
  by_strategy: [
    { strategy: "bull_call_spread",  trades: 312, win_rate: 68.3, avg_r: 1.41, notes: "Best in bull_trend regime" },
    { strategy: "long_call",         trades: 198, win_rate: 57.1, avg_r: 1.89, notes: "High variance; alpha plays" },
    { strategy: "bear_put_spread",   trades: 142, win_rate: 61.3, avg_r: 1.28, notes: "Strong in bear/high_vol" },
    { strategy: "iron_condor",       trades: 121, win_rate: 73.6, avg_r: 0.87, notes: "Income stream — consistent" },
    { strategy: "bull_put_spread",   trades:  74, win_rate: 70.3, avg_r: 0.92, notes: "Income stream — premium sell" },
  ],
  by_regime: [
    { regime: "bull_trend",  trades: 421, win_rate: 71.0, avg_r: 1.52, best_strategy: "bull_call_spread" },
    { regime: "bear_trend",  trades: 187, win_rate: 62.0, avg_r: 1.18, best_strategy: "bear_put_spread" },
    { regime: "chop",        trades: 143, win_rate: 58.0, avg_r: 0.94, best_strategy: "iron_condor" },
    { regime: "high_vol",    trades:  96, win_rate: 55.0, avg_r: 1.71, best_strategy: "long_call" },
  ],
  top_factors_by_ic: [
    { factor: "unusual_flow",    ic: 0.094, sample: 312 },
    { factor: "trend",           ic: 0.091, sample: 847 },
    { factor: "trade_structure", ic: 0.088, sample: 847 },
    { factor: "iv_analysis",     ic: 0.082, sample: 847 },
    { factor: "political_alpha", ic: 0.081, sample: 89  },
    { factor: "options_chain",   ic: 0.074, sample: 847 },
    { factor: "fundamental",     ic: 0.068, sample: 847 },
    { factor: "calendar",        ic: 0.029, sample: 847 },
    { factor: "dow_bias",        ic: 0.022, sample: 847 },
  ],
  monthly_returns: [
    { month: "2024-06", pct: 8.2 }, { month: "2024-07", pct: 12.1 }, { month: "2024-08", pct: -4.3 },
    { month: "2024-09", pct: 6.7 }, { month: "2024-10", pct: 9.4 },  { month: "2024-11", pct: 18.2 },
    { month: "2024-12", pct: 11.3 },{ month: "2025-01", pct: -7.1 }, { month: "2025-02", pct: 5.8 },
    { month: "2025-03", pct: 14.2 },{ month: "2025-04", pct: 7.9 },  { month: "2025-05", pct: 11.1 },
    { month: "2025-06", pct: 9.3 }, { month: "2025-07", pct: 13.7 }, { month: "2025-08", pct: -3.2 },
    { month: "2025-09", pct: 6.1 }, { month: "2025-10", pct: 8.8 },  { month: "2025-11", pct: 21.4 },
    { month: "2025-12", pct: 15.2 },{ month: "2026-01", pct: 9.7 },  { month: "2026-02", pct: 12.3 },
    { month: "2026-03", pct: 17.1 },{ month: "2026-04", pct: 11.8 }, { month: "2026-05", pct: 8.4 },
  ],
  notes: "Backtest uses Black-Scholes approximation for historical option prices. No slippage modeled. Live results will differ. IC priors from published factor research until 100+ real trades override.",
};

// ── Strategy Mock Data ────────────────────────────────────────────────────────

export const STRATEGY_DATA = {
  current: {
    version: "v1.4",
    effective_date: "2026-05-28",
    status: "active",
    authored_by: "System (IC auto-adjustment)",
    summary: "Dual-stream options strategy: Alpha stream for high-conviction directional plays (target 10×–100×), Income stream for consistent premium collection (target 30–50%/week). Human-in-the-loop required for all executions.",
    streams: {
      alpha: {
        label: "Alpha Stream",
        goal: "10×–100× returns on high-conviction directional catalysts",
        entry_conditions: [
          "Conviction score ≥ 80/100",
          "Minimum 3 independent category signals agreeing",
          "Catalyst required (earnings, govt contract, IPO halo, OGE disclosure)",
          "IV percentile < 50 preferred (cheap to buy premium)",
          "No major earnings within 5 days (unless playing the event intentionally)",
        ],
        structure_rules: [
          "IV < 45%ile → Long call/put (0.35–0.45Δ)",
          "IV 45–65%ile → Debit spread (bull/bear call/put)",
          "IV > 65%ile → Avoid naked buys; use spread to cap cost",
        ],
        dte: "14–21 days (swing) / 21–35 days (position)",
        position_size: "1–2% of portfolio per trade (higher conviction = larger)",
        profit_target: "No fixed % — hold until move plays out or stop hit",
        stop_loss: "50% of premium paid (exit if option loses half its value)",
        exit_rules: [
          "Hit target move shown in return projection",
          "50% premium loss → exit immediately",
          "DTE ≤ 5 → close regardless of P&L (gamma risk)",
        ],
      },
      income: {
        label: "Income Stream",
        goal: "30–50%/week consistent premium collection",
        entry_conditions: [
          "IV percentile ≥ 50 (elevated premium to sell)",
          "Regime: chop, high_vol, or directional with high IV",
          "Options bid-ask spread < 1.5% of underlying",
          "Open interest > 500 at target strikes",
        ],
        structure_rules: [
          "Neutral regime → Iron condor (0.16Δ short strikes, 30–45 DTE)",
          "Directional + high IV bullish → Bull put spread (0.30Δ short)",
          "Directional + high IV bearish → Bear call spread (0.30Δ short)",
          "Close at 50% max profit (tastytrade-proven threshold)",
        ],
        dte: "30–45 days entry, close at 21 DTE or 50% profit",
        position_size: "2–4% of portfolio per trade",
        profit_target: "50% of max credit received",
        stop_loss: "2× max credit received (if trade doubles against you, exit)",
        exit_rules: [
          "50% profit target hit → close immediately",
          "21 DTE roll alert → evaluate roll vs close",
          "Loss = 2× credit → exit, do not average down",
        ],
      },
    },
    risk_guardrails: {
      max_portfolio_heat: { value: 30, unit: "%", note: "Max capital at risk across all open positions" },
      max_sector_concentration: { value: 35, unit: "%", note: "No single sector > 35% of total risk" },
      daily_loss_cap: { value: 5, unit: "%", note: "If daily P&L ≤ -5% portfolio → halt all new trades" },
      max_drawdown: { value: 15, unit: "%", note: "If drawdown from peak ≥ 15% → kill switch + review" },
      max_concurrent_positions: { value: 10, unit: "positions", note: "Max 10 open positions at once" },
      min_signals_required: { value: 3, unit: "categories", note: "Need ≥3 independent categories agreeing" },
      min_options_liquidity: { bid_ask_pct: 1.5, open_interest: 500, note: "Hard gate before any entry" },
      net_delta_cap: { value: 60, unit: "%", note: "Portfolio can't be >60% net long or short directional" },
    },
    position_sizing: {
      method: "Conviction-scaled fractional Kelly",
      base_size_pct: 2.0,
      max_size_pct: 4.0,
      formula: "size = base × (conviction / 100) × kelly_fraction",
      kelly_fraction: 0.25,
      note: "Quarter-Kelly to account for model uncertainty. Conviction 80+ → ~2.5%, Conviction 90+ → ~3%",
    },
    confirmation_requirements: {
      min_independent_signals: 3,
      independent_categories: [
        "trend", "momentum", "iv_analysis", "fundamental", "options_chain",
        "sentiment", "options_flow", "political_alpha"
      ],
      anti_crowding: "Apply -20% score discount if 5+ influencers mentioned this week",
      false_breakout_filter: "Breakout valid only if 2+ consecutive closes above resistance AND volume >1.5× avg",
    },
  },

  versions: [
    {
      version: "v1.0",
      date: "2026-05-01",
      author: "V (initial setup)",
      change_type: "initial",
      summary: "Initial strategy: single-stream directional options based on IV rank and trend score.",
      changes: [
        "IV < 40%ile → buy calls/puts at 0.40Δ",
        "IV > 60%ile → sell iron condor",
        "Fixed position size: 2% per trade",
        "DTE: 30–45 days (all trades)",
        "Profit target: 50% max profit (all strategies)",
      ],
      performance: { win_rate: 58.1, avg_r: 1.12, trades: 43, period: "2026-05-01 to 2026-05-07" },
      rationale: "Starting point: tastytrade-proven parameters. 45 DTE + 50% profit target is well-researched baseline.",
    },
    {
      version: "v1.1",
      date: "2026-05-08",
      author: "V",
      change_type: "feature",
      summary: "Added dual-stream: Alpha (10×–100×) vs Income (30–50%/week). Different rules per stream.",
      changes: [
        "Alpha stream: DTE shortened to 14–21 days for directional plays",
        "Alpha stream: No fixed profit target — hold for full move",
        "Alpha stream: Stop at 50% premium loss",
        "Income stream: Keep 45 DTE, 50% profit target",
        "Conviction score ≥ 80 required for Alpha stream entries",
      ],
      performance: { win_rate: 62.3, avg_r: 1.28, trades: 31, period: "2026-05-08 to 2026-05-14" },
      rationale: "Realized two distinct trade types were being mixed. Alpha plays need different exit rules than premium selling. Separation improves clarity and reduces confusion on exit timing.",
    },
    {
      version: "v1.2",
      date: "2026-05-15",
      author: "V",
      change_type: "tightening",
      summary: "Tightened execution quality: bid-ask threshold 10% → 1.5%, added GEX/DEX and Expected Move.",
      changes: [
        "Options liquidity gate: bid-ask must be <1.5% of underlying (was 10%)",
        "ETF alternative suggested when spread too wide",
        "Added GEX/DEX/Vanna/Charm overlay signals",
        "Added Expected Move (ATM straddle price ÷ underlying) to context",
        "Added 25Δ IV skew signal",
      ],
      performance: { win_rate: 65.8, avg_r: 1.38, trades: 24, period: "2026-05-15 to 2026-05-21" },
      rationale: "RACE put trade (v1.0) lost due to 9.3% bid-ask spread eating premium. Tightening liquidity gate prevents this category of loss. GEX overlay adds dealer-flow context.",
    },
    {
      version: "v1.3",
      date: "2026-05-22",
      author: "V",
      change_type: "enhancement",
      summary: "Added Gamma Acceleration signal, conviction-scaled position sizing, and circuit breaker system.",
      changes: [
        "Gamma Acceleration (dΓ/dS) added as warning signal when >0.001",
        "Position sizing now conviction-scaled (quarter-Kelly based)",
        "Circuit breakers: daily loss cap 5%, max drawdown 15%, position limit 10",
        "Manual kill switch added with 24h TTL",
        "Discord webhook alerts for all position events",
      ],
      performance: { win_rate: 67.2, avg_r: 1.42, trades: 18, period: "2026-05-22 to 2026-05-27" },
      rationale: "System needs automated risk guardrails. Manual oversight is essential but not sufficient — need hard stops. Gamma acceleration warns of pin risk before expiry.",
    },
    {
      version: "v1.4",
      date: "2026-05-28",
      author: "System (IC auto-adjustment)",
      change_type: "ic_adjustment",
      summary: "Automatic weight adjustment: calendar/dow_bias halved due to low IC after 100+ trades.",
      changes: [
        "calendar IC: 0.029 after 134 trades → weight multiplier 0.50× (was 1.00×)",
        "dow_bias IC: 0.022 after 134 trades → weight multiplier 0.50× (was 1.00×)",
        "political_alpha IC: 0.081 → weight multiplier bumped to 1.20× (IC improving)",
        "unusual_flow IC: 0.094 → highest-performing single factor; weight multiplier 1.30×",
      ],
      performance: { win_rate: null, avg_r: null, trades: 0, period: "2026-05-28 to present" },
      rationale: "IC-driven automatic adjustment. Calendar effects and day-of-week bias showed near-zero predictive power after 100+ trades. Political alpha + unusual flow showed 2× expected IC. System adapts weights accordingly.",
    },
  ],

  pending_review: [
    {
      id: "rev_001",
      proposed_by: "System",
      proposed_date: "2026-05-30",
      description: "Congressional trading signals (STOCK Act 45-day disclosures) — propose adding as new alpha source alongside OGE.",
      evidence: "3,600+ Trump OGE transactions in Q1 2026. STOCK Act covers Senate/House with similar predictive value.",
      status: "pending_review",
    },
    {
      id: "rev_002",
      proposed_by: "System",
      proposed_date: "2026-05-30",
      description: "VIX regime thresholds: consider tightening to VIX <16 = calm, 16-26 = normal, >26 = elevated, >35 = crisis (vs current 35% RV threshold).",
      evidence: "Current threshold misclassifies many elevated periods. VIX-based thresholds align better with market practitioner experience.",
      status: "pending_review",
    },
  ],
};
