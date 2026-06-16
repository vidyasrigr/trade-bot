import { proxyJson } from "@/lib/backendProxy";

export async function GET() {
  return proxyJson("/strategy");
}

export async function PATCH(req: Request) {
  const body = await req.text();
  return proxyJson("/strategy", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
