import { proxyJson } from "@/lib/backendProxy";

export async function POST(req: Request) {
  const body = await req.text();
  return proxyJson("/trades/paper/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
