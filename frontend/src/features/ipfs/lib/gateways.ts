/**
 * Trustless HTTP gateway list for Helia block fetching.
 *
 * Privacy: each gateway you query sees the CID (and your IP). Prefer
 * self-hosted or trusted gateways for sensitive shared results. Content is
 * still verified against the CID before display, so a malicious gateway
 * cannot forge a different payload for that CID.
 */

export const DEFAULT_TRUSTLESS_GATEWAYS = [
  // Pinata serves vault pins reliably; supports ?format=raw for true IPLD blocks.
  "https://gateway.pinata.cloud",
  "https://trustless-gateway.link",
  "https://4everland.io",
] as const;

const ENV_KEY = "NEXT_PUBLIC_IPFS_TRUSTLESS_GATEWAYS";

/** Parse a comma/whitespace-separated gateway list; empty entries are dropped. */
export function parseGatewayList(raw: string | undefined | null): string[] {
  if (!raw?.trim()) return [];
  return raw
    .split(/[,\s]+/)
    .map((s) => s.trim().replace(/\/+$/, ""))
    .filter(Boolean);
}

/**
 * Gateways used by the trustless-gateway block broker.
 * Override with NEXT_PUBLIC_IPFS_TRUSTLESS_GATEWAYS (comma-separated URLs).
 */
export function getTrustlessGateways(
  envValue: string | undefined = typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_IPFS_TRUSTLESS_GATEWAYS
    : undefined,
): string[] {
  const fromEnv = parseGatewayList(envValue);
  return fromEnv.length > 0 ? fromEnv : [...DEFAULT_TRUSTLESS_GATEWAYS];
}

export { ENV_KEY as TRUSTLESS_GATEWAYS_ENV_KEY };
