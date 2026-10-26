import { creditCheckoutResponse } from "@/features/billing/server/credits";

export async function POST(req: Request) {
  return creditCheckoutResponse(req);
}
