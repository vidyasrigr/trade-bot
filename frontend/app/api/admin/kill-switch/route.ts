import { proxyJson } from "@/lib/backendProxy";

export async function POST(req: Request) {
  const body = await req.text();
  return proxyJson("/admin/kill-switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
