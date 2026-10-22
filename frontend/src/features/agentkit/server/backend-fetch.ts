import "server-only";
import { createHmac } from "node:crypto";
import { getSession } from "@/features/auth/server/session";

export async function agentBackendFetch(url: string, init: RequestInit = {}) {
  const session = await getSession();
  if (!session?.user) return Response.json({ error: "Sign in to use your agent." }, { status: 401 });
  const secret = process.env.AGENT_AUTH_BRIDGE_SECRET;
  if (!secret || secret.length < 32) return Response.json({ error: "Agent authentication is not configured." }, { status: 503 });
  const now = Math.floor(Date.now() / 1000);
  const body = Buffer.from(JSON.stringify({ sub: session.user.id, email: session.user.email, iat: now, exp: now + 60, aud: "quantumnodes-agentkit" })).toString("base64url");
  const signature = createHmac("sha256", secret).update(body).digest("hex");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer qn1.${body}.${signature}`);
  return fetch(url, { ...init, headers, cache: "no-store", redirect: "error" });
}
