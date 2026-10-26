"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { QUERY_KEYS, API, UI } from "@/constants";
import type { CircuitSubmitRequest, CircuitSubmitResponse } from "../types";

export function useCreateRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      request: CircuitSubmitRequest,
    ): Promise<CircuitSubmitResponse> => {
      const res = await fetch(API.RUNS.CREATE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (!res.ok) {
        // Surface the backend's reason, e.g. a 402 when credits run out.
        const data: unknown = await res.json().catch(() => null);
        const message =
          typeof data === "object" && data !== null && "message" in data ? data.message : null;
        throw new Error(typeof message === "string" ? message : UI.ERRORS.RUN_CREATE_FAILED);
      }
      return res.json() as Promise<CircuitSubmitResponse>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.runs.all() });
    },
  });
}
