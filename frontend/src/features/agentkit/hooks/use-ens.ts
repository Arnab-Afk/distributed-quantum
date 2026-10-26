import { useQuery } from "@tanstack/react-query";
import { API_AGENTKIT } from "@/constants/api";
import { QUERY_KEYS_AGENTKIT } from "@/constants/query-keys";
import {
  ensErrorMessage,
  isHexAddress,
  looksLikeEnsName,
  type EnsResolveResponse,
  type EnsReverseResponse,
} from "../lib/ens";

async function fetchEnsResolve(
  name: string,
  fresh: boolean,
): Promise<EnsResolveResponse> {
  const params = new URLSearchParams({ name, fresh: String(fresh) });
  const res = await fetch(`${API_AGENTKIT.ENS_RESOLVE}?${params.toString()}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(ensErrorMessage(data, "ENS resolution failed"));
  }
  return data as EnsResolveResponse;
}

async function fetchEnsReverse(address: string): Promise<EnsReverseResponse> {
  const params = new URLSearchParams({ address });
  const res = await fetch(`${API_AGENTKIT.ENS_REVERSE}?${params.toString()}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(ensErrorMessage(data, "ENS reverse lookup failed"));
  }
  return data as EnsReverseResponse;
}

/** Forward-resolve an ENS name. Disabled unless the input looks like a name. */
export function useEnsResolve(
  name: string,
  options?: { fresh?: boolean; enabled?: boolean },
) {
  const trimmed = name.trim();
  const fresh = options?.fresh ?? false;
  const enabled =
    (options?.enabled ?? true) && looksLikeEnsName(trimmed);

  return useQuery({
    queryKey: QUERY_KEYS_AGENTKIT.ensResolve(trimmed.toLowerCase(), fresh),
    queryFn: () => fetchEnsResolve(trimmed, fresh),
    enabled,
    staleTime: fresh ? 0 : 60_000,
    retry: false,
  });
}

/** Reverse-resolve a primary ENS name for a hex address. Fails open (null name). */
export function useEnsReverse(address: string | null | undefined) {
  const trimmed = (address ?? "").trim();
  const enabled = isHexAddress(trimmed);

  return useQuery({
    queryKey: QUERY_KEYS_AGENTKIT.ensReverse(trimmed),
    queryFn: () => fetchEnsReverse(trimmed),
    enabled,
    staleTime: 120_000,
    retry: false,
  });
}

/** Imperative fresh resolve used immediately before sending funds. */
export async function resolveEnsFresh(name: string): Promise<EnsResolveResponse> {
  return fetchEnsResolve(name.trim(), true);
}
