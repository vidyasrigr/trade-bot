import { proxyJson } from "@/lib/backendProxy";

export async function GET() {
  return proxyJson("/politics/disclosures");
}
