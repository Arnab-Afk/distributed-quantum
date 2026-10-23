"use client";

import dynamic from "next/dynamic";

const VaultCidClient = dynamic(
  () =>
    import("@/features/ipfs/components/vault-cid-client").then(
      (m) => m.VaultCidClient,
    ),
  { ssr: false },
);

export default function VaultCidPastePage() {
  return <VaultCidClient cid="" />;
}
