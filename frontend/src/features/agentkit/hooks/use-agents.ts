import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";
import { QUERY_KEYS_AGENTKIT } from "@/constants/query-keys";
import { API_AGENTKIT } from "@/constants/api";

export function shortAddress(value: string | null | undefined) {
  const address = value?.trim() ?? "";
  if (!address) return "";
  if (address.length <= 13) return address;
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

export function parseApiTimestamp(value: string): Date | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const hasZone = /(?:Z|[+-]\d{2}:\d{2})$/.test(trimmed);
  const date = new Date(hasZone ? trimmed : `${trimmed}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function humanWhen(value: string | number | null | undefined) {
  if (value == null || value === "") return null;
  const date = typeof value === "number"
    ? (Number.isFinite(value) && value > 0 ? new Date(value) : null)
    : parseApiTimestamp(value);
  if (!date) return null;
  return {
    relative: formatDistanceToNow(date, { addSuffix: true }),
    exact: format(date, "MMM d, yyyy 'at' h:mm a"),
  };
}

export function humanSpan(created: string | number | null | undefined, updated: string | number | null | undefined) {
  const start = humanWhen(created);
  const last = humanWhen(updated);
  if (!start && !last) return null;
  const title = [start && `Started ${start.exact}`, last && `Updated ${last.exact}`].filter(Boolean).join(" · ");
  const text = start && last && start.relative === last.relative && start.exact !== last.exact
    ? `Started ${start.exact} · Updated ${last.exact}`
    : [start && `Started ${start.relative}`, last && `Updated ${last.relative}`].filter(Boolean).join(" · ");
  return { text, title };
}

export type StarknetSessionStatus = {
  status?: string;
  expires_at?: number;
};

export type AgentItem = {
  agent_id: string;
  agent_name: string;
  owner_id: string;
  wallet_address: string;
  config: Record<string, unknown>;
  total_spent: string;
  starknet_session?: StarknetSessionStatus | null;
  created_at: string;
  updated_at?: string;
};

export function collapseDuplicatePersonalAgents<T extends { agent_id: string; agent_name: string; created_at: string }>(
  agents: T[],
  sessions: { agentId?: string }[],
): T[] {
  const personal = agents.filter((agent) => agent.agent_name === DEFAULT_AGENT_BODY.agent_name);
  if (personal.length <= 1) return agents;
  const keeper = [...personal].sort((a, b) => {
    const aSessions = sessions.filter((session) => session.agentId === a.agent_id).length;
    const bSessions = sessions.filter((session) => session.agentId === b.agent_id).length;
    if (aSessions !== bSessions) return bSessions - aSessions;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  })[0];
  return agents.filter(
    (agent) => agent.agent_name !== DEFAULT_AGENT_BODY.agent_name || agent.agent_id === keeper?.agent_id,
  );
}

const DEFAULT_AGENT_BODY = {
  agent_name: "Research Assistant",
  config: {
    auto_fund: false,
    max_per_proposal: "50",
    daily_budget: "200",
    research_interests: ["quantum computing", "error correction", "variational algorithms"],
    min_reputation_threshold: 40,
  },
};

export function useAgents() {
  return useQuery<AgentItem[]>({
    queryKey: QUERY_KEYS_AGENTKIT.agents(),
    queryFn: async () => {
      const res = await fetch(API_AGENTKIT.AGENTS);
      if (!res.ok) throw new Error("Failed to fetch agents");
      const data = await res.json();
      return Array.isArray(data) ? data : (data.agents ?? []);
    },
    staleTime: 60_000,
  });
}

let personalAgentCreate: Promise<AgentItem> | null = null;

async function postAgent(payload: typeof DEFAULT_AGENT_BODY): Promise<AgentItem> {
  const res = await fetch(API_AGENTKIT.AGENTS, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message ?? err.error ?? "Failed to create agent");
  }
  return res.json();
}

export function useRevokeStarknetSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) => {
      const res = await fetch(
        `/api/agentkit/agents/${encodeURIComponent(agentId)}/starknet-session/revoke`,
        { method: "POST" },
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.message ?? data.error ?? "Could not revoke the session");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS_AGENTKIT.agents() });
    },
  });
}

export function useCreateAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body?: typeof DEFAULT_AGENT_BODY) => {
      if (body) return postAgent(body);
      if (!personalAgentCreate) {
        personalAgentCreate = postAgent(DEFAULT_AGENT_BODY).finally(() => {
          personalAgentCreate = null;
        });
      }
      return personalAgentCreate;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS_AGENTKIT.agents() });
    },
  });
}
