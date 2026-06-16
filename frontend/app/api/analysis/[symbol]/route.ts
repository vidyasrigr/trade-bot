import { proxyStream } from "@/lib/backendProxy";

export async function GET(_req: Request, { params }: { params: { symbol: string } }) {
  return proxyStream(`/analysis/${params.symbol.toUpperCase()}`);
}
