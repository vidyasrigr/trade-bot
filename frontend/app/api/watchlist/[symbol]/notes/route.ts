import { proxyJson } from "@/lib/backendProxy";

export async function PATCH(req: Request, { params }: { params: { symbol: string } }) {
  const body = await req.text();
  return proxyJson(`/watchlist/${params.symbol.toUpperCase()}/notes`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
