import type { Chain, ChainCapability, ChainsResponse, ExplorerKind } from "../types";

/** Finds a chain by CAIP-2 id or legacy alias; unknown or disabled names return undefined. */
export function findChain(
  registry: ChainsResponse | null | undefined,
  network: string | null | undefined,
): Chain | undefined {
  if (!registry || !network) return undefined;
  return registry.chains.find(
    (chain) => chain.chain_id === network || chain.aliases.includes(network),
  );
}

export function supports(chain: Chain, capability: ChainCapability): boolean {
  return chain.capabilities.includes(capability);
}

/** Fills the template's single terminal placeholder, e.g. `.../tx/{tx_hash}`. */
export function explorerUrl(chain: Chain, kind: ExplorerKind, value: string): string {
  return chain.explorers[kind].replace(/\{[a-z_]+\}$/, encodeURIComponent(value));
}
