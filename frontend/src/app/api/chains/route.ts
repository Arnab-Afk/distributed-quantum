import { NextResponse } from "next/server";
import { fetchChains } from "@/features/chains/server/chains-service";

export async function GET() {
  const res = await fetchChains();
  if (!res) return NextResponse.json({ error: "Failed to fetch chains" }, { status: 502 });
  const data = await res.json().catch(() => ({ error: "Failed to fetch chains" }));
  return NextResponse.json(data, { status: res.ok ? res.status : 502 });
}
