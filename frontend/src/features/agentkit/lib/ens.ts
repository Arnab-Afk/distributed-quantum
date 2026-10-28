const ADDRESS_PATTERN = /^0x[a-fA-F0-9]{40}$/;

/** True when the value looks like a dotted ENS name rather than a hex address. */
export function looksLikeEnsName(value: string): boolean {
  const candidate = value.trim();
  if (!candidate || ADDRESS_PATTERN.test(candidate)) return false;
  return candidate.includes(".");
}

export function isHexAddress(value: string): boolean {
  return ADDRESS_PATTERN.test(value.trim());
}

export function truncateAddress(address: string): string {
  if (!address) return "";
  if (address.length < 12) return address;
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

export type EnsResolveResponse = {
  name: string;
  address: string;
  coin_type: number;
  ens_network: string;
  cached: boolean;
};

export type EnsReverseResponse = {
  address: string;
  name: string | null;
  coin_type: number;
  ens_network: string;
  cached: boolean;
};

/** Pull a human-readable message from FastAPI / BFF error payloads. */
export function ensErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const body = payload as Record<string, unknown>;
  if (typeof body.message === "string" && body.message.trim()) return body.message;
  if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  if (typeof body.error === "string" && body.error.trim()) return body.error;
  return fallback;
}
