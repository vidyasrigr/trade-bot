import { NextResponse } from "next/server";

// Server-side proxy target. BACKEND_API_URL (server-only) wins; falls back to the
// public var the pages use, then localhost FastAPI.
const BACKEND =
  process.env.BACKEND_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000/api";

function unreachable(url: string) {
  return NextResponse.json(
    {
      error: "backend_unreachable",
      detail: `FastAPI backend not reachable at ${url}. Start it with: cd backend && uvicorn main:app --reload`,
    },
    { status: 502 },
  );
}

export async function proxyJson(path: string, init?: RequestInit): Promise<Response> {
  const url = `${BACKEND}${path}`;
  let resp: Response;
  try {
    resp = await fetch(url, { cache: "no-store", ...init });
  } catch {
    return unreachable(url);
  }
  const data = await resp.json().catch(() => null);
  if (data === null) {
    return NextResponse.json(
      { error: "invalid_backend_response", detail: `Non-JSON response from ${url}` },
      { status: 502 },
    );
  }
  return NextResponse.json(data, { status: resp.status });
}

export async function proxyStream(path: string): Promise<Response> {
  const url = `${BACKEND}${path}`;
  try {
    const resp = await fetch(url, { cache: "no-store" });
    return new Response(resp.body, {
      status: resp.status,
      headers: {
        "Content-Type": resp.headers.get("content-type") ?? "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch {
    const body = new TextEncoder().encode(
      `event: error\ndata: ${JSON.stringify({
        message: `FastAPI backend not reachable at ${url}. Start it with: cd backend && uvicorn main:app --reload`,
      })}\n\n`,
    );
    return new Response(body, {
      status: 502,
      headers: { "Content-Type": "text/event-stream" },
    });
  }
}
