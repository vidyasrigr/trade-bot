import { proxyJson } from "@/lib/backendProxy";

export async function GET() {
  return proxyJson("/backtest/results");
}
