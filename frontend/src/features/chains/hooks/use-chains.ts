"use client";
import { useQuery } from "@tanstack/react-query";
import { API, QUERY_KEYS } from "@/constants";
import type { ChainsResponse } from "../types";

export function useChains() {
  return useQuery<ChainsResponse>({
    queryKey: QUERY_KEYS.chains.all(),
    queryFn: async () => {
      const res = await fetch(API.CHAINS);
      if (!res.ok) throw new Error("Failed to fetch chains");
      return res.json();
    },
    // The registry is fixed for the backend's lifetime.
    staleTime: 5 * 60_000,
  });
}
