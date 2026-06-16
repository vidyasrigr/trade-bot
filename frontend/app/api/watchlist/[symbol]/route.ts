import { proxyJson } from "@/lib/backendProxy";

export async function DELETE(_req: Request, { params }: { params: { symbol: string } }) {
  return proxyJson(`/watchlist/${params.symbol.toUpperCase()}`, { method: "DELETE" });
}
