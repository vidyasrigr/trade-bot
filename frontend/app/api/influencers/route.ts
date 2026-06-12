import { NextResponse } from "next/server";
import { INFLUENCERS_DATA } from "@/lib/mockData";

export async function GET() {
  return NextResponse.json(INFLUENCERS_DATA);
}
