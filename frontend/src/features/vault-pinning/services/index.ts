import type { PinningProvider, PinningService } from "../types";
import { lighthouseProvider } from "./lighthouse";
import { nftStorageProvider } from "./nft-storage";
import { pinataProvider } from "./pinata";

const providers = new Map<PinningService, PinningProvider>([
  ["lighthouse", lighthouseProvider],
  ["pinata", pinataProvider],
  // backward-compat: existing pin records that stored service="nft.storage"
  ["nft.storage", nftStorageProvider],
]);

export const DEFAULT_SERVICE: PinningService = "pinata";

export const SERVICE_LABELS: Record<PinningService, string> = {
  lighthouse: "Lighthouse",
  pinata: "Pinata",
  "nft.storage": "NFT.Storage",
};

export function getProvider(service: PinningService): PinningProvider {
  const provider = providers.get(service);
  if (!provider) throw new Error(`Unknown pinning service: ${service}`);
  return provider;
}

export function getAllProviders(): PinningProvider[] {
  return Array.from(providers.values());
}
