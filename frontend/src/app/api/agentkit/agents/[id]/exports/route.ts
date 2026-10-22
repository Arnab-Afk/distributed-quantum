import { agentBackendFetch } from "@/features/agentkit/server/backend-fetch";
import { BACKEND_AGENTKIT } from "@/constants/backend";
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const session = new URL(request.url).searchParams.get("session_id") ?? "";
  try {
    const response = await agentBackendFetch(`${BACKEND_AGENTKIT.AGENTS}/${encodeURIComponent(id)}/exports?session_id=${encodeURIComponent(session)}`);
    return Response.json(await response.json(), { status: response.status });
  } catch { return Response.json({ error: "Storage service unavailable." }, { status: 502 }); }
}
