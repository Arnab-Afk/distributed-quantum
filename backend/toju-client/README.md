# Toju payment client

This is a backend child process that signs approved Base Sepolia payments using
QuantumNodes' existing CDP wallet. It does not host a storage API. The complete
Toju server runs separately from https://github.com/Winter-Soren/afara/tree/codex/devcon-testnet.

Node 22: `npm ci`, then `npm test`. Python starts `worker.mjs` over stdin/stdout.
No wallet or API secrets belong in this directory. Receipts verify the actual
USDC Transfer on Base Sepolia and the downloaded artifact SHA-256. Reconciliation
never signs or pays again. Export limit: 256 KiB, retention: 30 days.
