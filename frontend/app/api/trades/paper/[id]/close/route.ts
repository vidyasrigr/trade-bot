import { proxyJson } from "@/lib/backendProxy";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const body = await req.text();
  return proxyJson(`/trades/paper/${params.id}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
