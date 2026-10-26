import { NextResponse } from "next/server";
import { BACKEND_AGENTKIT } from "@/constants/backend";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const address = searchParams.get("address");
    if (!address?.trim()) {
      return NextResponse.json(
        { error: "validation_error", message: "address query parameter is required" },
        { status: 422 },
      );
    }
    const params = new URLSearchParams();
    params.set("address", address.trim());
    const coinType = searchParams.get("coin_type");
    if (coinType) params.set("coin_type", coinType);
    const fresh = searchParams.get("fresh");
    if (fresh) params.set("fresh", fresh);

    const res = await fetch(`${BACKEND_AGENTKIT.ENS_REVERSE}?${params.toString()}`, {
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unreachable" }, { status: 502 });
  }
}
