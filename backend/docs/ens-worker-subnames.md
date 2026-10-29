# Worker ENS subnames (issue #22, phase 2 / PR3)

Design note and proof-of-concept schema for `*.qmesh.eth`-style worker records.
**No production parent name is registered here** — that needs a maintainer decision and budget.

## Goal

Give each worker (and later each agent) a stable ENS subname that carries libp2p discovery
data in text records, so Web3 identity and the peer network stay linked.

Example (illustrative):

```text
worker-alpha.qmesh.eth
```

## Parent name

| Item | Proposal |
|------|----------|
| Parent | `qmesh.eth` (or a Sepolia test parent while prototyping) |
| Issuer | Off-chain / CCIP-Read resolver backed by MongoDB (gasless subname issuance) |
| Fallback | On-chain subdomain mint only if off-chain path is blocked |

## Text-record schema

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `peer-id` | string | yes | libp2p peer id (base58btc / CIDv1 as used by enrollment) |
| `multiaddrs` | string | yes | Comma-separated multiaddrs, or JSON array string |
| `services` | string | yes | Comma-separated service ids the peer advertises |
| `pricing-url` | URL | no | HTTP(S) endpoint for fragment pricing |
| `network` | string | no | Payment / AgentKit network id (e.g. `base-sepolia`) |
| `wallet` | address | no | Preferred payout address (coin type 60 / ENSIP-11) |
| `avatar` | URL | no | Optional branding |

Forward `addr` (coin type 60 or L2 ENSIP-11) SHOULD resolve to the payout wallet when set.

## MongoDB projection (CCIP-Read backend)

Suggested collection `ens_worker_records`:

```json
{
  "subname": "worker-alpha",
  "parent": "qmesh.eth",
  "peer_id": "12D3KooW…",
  "multiaddrs": ["/ip4/…/tcp/4021", "/dns4/…/tcp/443/wss"],
  "services": ["circuit.execute", "finance.qaoa"],
  "pricing_url": "https://…/pricing",
  "network": "base-sepolia",
  "wallet": "0x…",
  "updated_at": "2026-10-21T00:00:00Z"
}
```

The CCIP-Read gateway returns ENSIP-10 wildcard answers for `{subname}.qmesh.eth` from this doc.

## Proof of concept (one worker)

1. Pick a Sepolia test parent (or a free publicname for local demo).
2. Insert one `ens_worker_records` document for a known enrollment peer.
3. Serve text records via a stub resolver endpoint (even if not yet on-chain):
   - `GET /api/v1/ens/workers/{subname}` → schema above
4. Operator console shows `subname` next to peer id when present.

Until the parent name and CCIP-Read gateway exist, the stub API alone is enough to validate the schema against real peer data from `discovery/` / enrollment.

## Out of scope

- Registering production `qmesh.eth`
- Running our own registry contracts
- Contenthash / IPFS result CIDs (phase 3, depends on #4)
