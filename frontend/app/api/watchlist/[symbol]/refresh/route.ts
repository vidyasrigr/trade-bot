import { proxyJson } from "@/lib/backendProxy";

export async function POST(_req: Request, { params }: { params: { symbol: string } }) {
  return proxyJson(`/watchlist/${params.symbol.toUpperCase()}/refresh`, { method: "POST" });
}
