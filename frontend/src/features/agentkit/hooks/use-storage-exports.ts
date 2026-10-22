"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
export type StorageExport = {
  id: string; title: string; content: string; filename: string; sha256: string; bytes: number;
  usdc: string; payTo: string; status: string; expires_at: string; error?: string; message_index?: number | null;
  receipt?: { cid: string; transaction: string; url: string; verified: boolean };
};
export function useStorageExports(agentId?: string, sessionId?: string | null) {
  const cache = useQueryClient();
  const key = ["storage-exports", agentId, sessionId];
  const url = `/api/agentkit/agents/${encodeURIComponent(agentId ?? "")}/exports`;
  const query = useQuery<StorageExport[]>({ queryKey: key, enabled: Boolean(agentId && sessionId), queryFn: async () => {
    const r = await fetch(`${url}?session_id=${encodeURIComponent(sessionId!)}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.message ?? data.error ?? "Could not load exports.");
    return data;
  } });
  const decision = useMutation({ mutationFn: async ({ proposal, action }: { proposal: StorageExport; action: "approve" | "cancel" | "reconcile" }) => {
    const r = await fetch(`${url}/${encodeURIComponent(proposal.id)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sessionId, decision: action, sha256: proposal.sha256 }) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.message ?? data.error ?? "Storage approval failed.");
    return data as StorageExport;
  }, onSettled: () => cache.invalidateQueries({ queryKey: key }) });
  return { ...query, decision, refresh: (savedSessionId?: string | null) => cache.invalidateQueries({ queryKey: ["storage-exports", agentId, savedSessionId ?? sessionId] }) };
}
