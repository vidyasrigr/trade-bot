import { NVDA_ANALYSIS } from "@/lib/mockData";

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function sseEvent(type: string, data: unknown): string {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
}

export async function GET(_req: Request, { params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();

  const stream = new ReadableStream({
    async start(controller) {
      const enc = new TextEncoder();
      const send = (type: string, data: unknown) =>
        controller.enqueue(enc.encode(sseEvent(type, data)));

      send("status", { stage: "macro", message: "Fetching macro & market regime..." });
      await sleep(600);

      send("status", { stage: "technical", message: "Running 20-category scoring engine..." });
      await sleep(900);

      send("status", { stage: "scoring", message: "Calculating weighted scores..." });
      await sleep(500);

      const analysis = symbol === "NVDA" ? NVDA_ANALYSIS : buildGenericAnalysis(symbol);

      send("analysis_scores", {
        category_scores: analysis.category_scores,
        total_score: analysis.total_score,
        direction: analysis.direction,
      });
      await sleep(400);

      send("status", { stage: "agents", message: "Running 4 parallel analyst agents..." });
      await sleep(1200);

      send("analyst_reports", {
        fundamental: buildFundamentalReport(symbol),
        technical: buildTechnicalReport(symbol),
        volatility: buildVolatilityReport(symbol),
        sentiment: buildSentimentReport(symbol),
      });
      await sleep(600);

      send("status", { stage: "trader", message: "Trader agent synthesizing thesis..." });
      await sleep(1000);

      send("trader_thesis", { thesis: analysis.trader_thesis });
      await sleep(400);

      send("status", { stage: "risk", message: "Risk manager validating position sizing..." });
      await sleep(600);

      send("risk_assessment", { assessment: analysis.risk_assessment });
      await sleep(300);

      send("status", { stage: "options", message: "Querying options chain for best structure..." });
      await sleep(500);

      send("order_ticket", analysis.order_ticket);

      send("complete", {
        conviction_score: analysis.conviction_score,
        total_score: analysis.total_score,
        direction: analysis.direction,
      });

      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}

function buildGenericAnalysis(symbol: string) {
  const score = 55 + Math.floor(symbol.length * 3.7) % 30;
  return {
    ...NVDA_ANALYSIS,
    total_score: score,
    direction: score >= 65 ? "bullish" : score <= 45 ? "bearish" : "neutral",
    conviction_score: score - 8,
    trader_thesis: `## Trade Thesis: ${symbol}\n\nAnalysis complete. Score ${score}/100. Connect to live backend for full Claude reasoning.`,
    risk_assessment: `Portfolio check complete. Standard position sizing applies.`,
    order_ticket: {
      ...NVDA_ANALYSIS.order_ticket,
      symbol,
      thesis_summary: `${symbol} analysis complete — score ${score}/100. Connect to live backend for full detail.`,
    },
  };
}

function buildFundamentalReport(symbol: string) {
  return `**${symbol} Fundamental Analysis**\n\nEarnings momentum remains strong with sequential revenue growth. Analyst consensus skews bullish with median price target implying 12–18% upside from current levels. No material negative catalysts identified in the next 60 days. Short interest at 2.1% — no squeeze pressure but also no headwind.`;
}

function buildTechnicalReport(symbol: string) {
  return `**${symbol} Technical Analysis**\n\nAll EMAs aligned bullish (8 > 21 > 50 > 200). ADX above 30 confirms trend strength. RSI 14d at 64 — room to run before overbought territory. MACD bullish crossover confirmed on daily timeframe with histogram expanding. Volume profile shows strong accumulation at current levels.`;
}

function buildVolatilityReport(symbol: string) {
  return `**${symbol} Volatility Analysis**\n\nIV rank elevated but not extreme. Term structure in mild backwardation reflecting near-term demand. Realized vol running below implied — suggests options slightly expensive. Recommended structure: bull call spread to neutralize excess vega. Expected move (30 DTE): ±7.2%.`;
}

function buildSentimentReport(symbol: string) {
  return `**${symbol} Sentiment Analysis** (Ollama)\n\nNews sentiment: 73% positive in past 7 days. Social media mentions trending up but not at crowding levels. Unusual options flow: 2 large block call purchases at ask in past 48h. Dark pool activity positive. YouTuber mentions: 1 (below 5-mention crowding threshold — no discount applied).`;
}
