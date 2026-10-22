import { agentBackendFetch } from "@/features/agentkit/server/backend-fetch";
import { BACKEND_AGENTKIT } from "@/constants/backend";
export async function POST(request: Request, { params }: { params: Promise<{ id: string; proposalId: string }> }) {
  if (request.headers.get("origin") !== new URL(request.url).origin) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  const { id, proposalId } = await params;
  try {
    const response = await agentBackendFetch(`${BACKEND_AGENTKIT.AGENTS}/${encodeURIComponent(id)}/exports/${encodeURIComponent(proposalId)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(await request.json()) });
    return Response.json(await response.json(), { status: response.status });
  } catch { return Response.json({ error: "Storage outcome is unverified. Refresh the receipt before taking another action." }, { status: 502 }); }
}
