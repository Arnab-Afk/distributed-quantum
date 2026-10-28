import { financeResultResponse } from "@/shared/server/finance-result-response";
import { financeBackendFetch } from "@/shared/server/finance-backend-fetch";
import { type NextRequest, NextResponse } from "next/server";
import { BACKEND } from "@/constants";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;
  try {
    const res = await financeBackendFetch(BACKEND.OPTIONS.DETAIL(jobId));
    return await financeResultResponse(
      res,
      request.nextUrl.searchParams.get("download") == "provenance",
    );
  } catch {
    return NextResponse.json(
      { detail: "Backend unreachable" },
      { status: 502 },
    );
  }
}
