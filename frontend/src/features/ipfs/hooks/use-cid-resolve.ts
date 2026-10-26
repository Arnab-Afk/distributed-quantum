"use client";

import { useCallback, useState } from "react";
import { useHeliaContext } from "../provider";
import {
  isResolveError,
  resolveVaultCid,
  type ResolveVaultCidResult,
} from "../lib/cid-resolve";
import { getTrustlessGateways } from "../lib/gateways";

export type CidResolveErrorCode =
  | "INVALID_CID"
  | "GATEWAY_UNREACHABLE"
  | "CID_MISMATCH"
  | "SCHEMA_INVALID"
  | "HELIA_NOT_READY"
  | "UNKNOWN";

export type CidResolveError = {
  code: CidResolveErrorCode;
  message: string;
};

function toResolveError(err: unknown): CidResolveError {
  if (isResolveError(err)) {
    return { code: err.code, message: err.message };
  }
  return {
    code: "UNKNOWN",
    message: err instanceof Error ? err.message : String(err),
  };
}

export function useCidResolve() {
  const { helia, ready } = useHeliaContext();
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<CidResolveError | null>(null);
  const [result, setResult] = useState<ResolveVaultCidResult | null>(null);

  const resolve = useCallback(
    async (cidStr: string): Promise<ResolveVaultCidResult | null> => {
      if (!helia || !ready) {
        const e: CidResolveError = {
          code: "HELIA_NOT_READY",
          message: "Vault (Helia) is still starting. Try again in a moment.",
        };
        setError(e);
        setResult(null);
        return null;
      }

      setResolving(true);
      setError(null);
      setResult(null);

      try {
        const resolved = await resolveVaultCid(cidStr, {
          helia,
          gateways: getTrustlessGateways(),
        });
        setResult(resolved);
        return resolved;
      } catch (err) {
        const e = toResolveError(err);
        setError(e);
        return null;
      } finally {
        setResolving(false);
      }
    },
    [helia, ready],
  );

  return { resolve, resolving, error, result, ready };
}
