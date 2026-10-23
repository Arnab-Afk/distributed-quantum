import { creditsOverviewResponse } from "@/features/billing/server/credits";

export const dynamic = "force-dynamic";

export async function GET() {
  return creditsOverviewResponse();
}
