export { HeliaProvider, useHeliaContext } from "./provider";
export { useHelia } from "./hooks/use-helia";
export { useIpfsUpload } from "./hooks/use-ipfs-upload";
export { useIpfsFetch } from "./hooks/use-ipfs-fetch";
export { useCidResolve } from "./hooks/use-cid-resolve";
export { useLocalVaultIndex } from "./hooks/use-local-vault-index";
export { getTrustlessGateways, DEFAULT_TRUSTLESS_GATEWAYS } from "./lib/gateways";
export { resolveVaultCid, parseCidString } from "./lib/cid-resolve";

export type {
  CircuitIPFSRecord,
  RunIPFSRecord,
  VaultItem,
  LocalVaultIndex,
} from "./types";
