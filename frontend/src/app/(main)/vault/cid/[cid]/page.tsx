"use client";

import dynamic from "next/dynamic";

const VaultCidClient = dynamic(
  () =>
    import("@/features/ipfs/components/vault-cid-client").then(
      (m) => m.VaultCidClient,
    ),
  { ssr: false },
);

export default async function VaultCidPage({
  params,
}: {
  params: Promise<{ cid: string }>;
}) {
  const { cid } = await params;
  return <VaultCidClient cid={decodeURIComponent(cid)} />;
}
