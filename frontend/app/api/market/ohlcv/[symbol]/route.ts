import { proxyJson } from "@/lib/backendProxy";

export async function GET(req: Request, { params }: { params: { symbol: string } }) {
  const period = new URL(req.url).searchParams.get("period") || "6mo";
  return proxyJson(`/market/ohlcv/${params.symbol.toUpperCase()}?period=${encodeURIComponent(period)}`);
}
