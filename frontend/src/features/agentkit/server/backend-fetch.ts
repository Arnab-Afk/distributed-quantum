import "server-only";
import { backendAssertion } from "@/features/auth/server/backend-assertion";
import { getSession } from "@/features/auth/server/session";

export async function agentBackendFetch(url: string, init: RequestInit = {}) {
  const session = await getSession();
  if (!session?.user) return Response.json({ error: "Sign in to use your agent." }, { status: 401 });
  const assertion = backendAssertion(session.user);
  if (!assertion) return Response.json({ error: "Agent authentication is not configured." }, { status: 503 });
  const headers = new Headers(init.headers);
  headers.set("Authorization", assertion);
  return fetch(url, { ...init, headers, cache: "no-store", redirect: "error" });
}
