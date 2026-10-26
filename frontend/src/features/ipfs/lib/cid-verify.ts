import type { CID } from "multiformats/cid";
import { sha256 } from "multiformats/hashes/sha2";

function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/**
 * Re-hash block bytes and compare to the CID multihash.
 * Only sha2-256 CIDs are supported (Helia JSON default).
 */
export async function blockMatchesCid(
  bytes: Uint8Array,
  cid: CID,
): Promise<boolean> {
  if (cid.multihash.code !== sha256.code) {
    return false;
  }
  const digest = await sha256.digest(bytes);
  return bytesEqual(digest.bytes, cid.multihash.bytes);
}
