import { proxyJson } from "@/lib/backendProxy";

export async function GET(req: Request) {
  const status = new URL(req.url).searchParams.get("status") || "all";
  return proxyJson(`/trades/paper?status=${encodeURIComponent(status)}`);
}
