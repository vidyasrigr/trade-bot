import { proxyJson } from "@/lib/backendProxy";

export async function GET(_req: Request, { params }: { params: { symbol: string } }) {
  return proxyJson(`/trades/freshness/${params.symbol.toUpperCase()}`);
}
