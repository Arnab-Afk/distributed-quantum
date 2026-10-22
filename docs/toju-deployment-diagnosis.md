# Toju deployment diagnosis

> Historical research/diagnosis. Deployment subsequently succeeded on October 11, 2026 IST: the full official Toju fork is live on Render and a Groq agent export/payment/retrieval was verified. Current status and reproduction steps are in [the deployment guide](toju-render-testnet-guide.md) and [demo guide](toju-devcon-demo.md). Earlier “not yet tested/deployed” statements below describe the investigation at that time.


Checked October 10, 2026. Source inspected: `tojunetwork/afara` commit `a0053d5fdd81904e00d1f6ac5889af31a8153d9d`. These are read-only observations, not a completed storage/payment test.

## Mentor-ready finding

The Toju testnet API at `https://staging-api.toju.network` returns HTTP 503, HTML “Service Suspended,” and the header `x-render-routing: suspend`. The latest check was October 10, 2026 at 16:40:44 UTC (22:10:44 IST). This identifies the suspended hosting layer; it does not establish a blockchain outage or disclose the Render account's suspension reason. Restoring or replacing this API deployment is necessary. Installing the SDK locally or changing only the blockchain RPC does not remove this dependency.

Reproduce without a wallet or payment:

```sh
curl --max-time 20 -i 'https://staging-api.toju.network/pricing/quote?size=1000000&duration=30&chain=base'
```

Earlier diagnostic-only checks also found the same response on `api.toju.network` at 16:26:48 UTC. Application integration remains testnet-only; no mainnet transaction was sent.

Render documents suspension for several conditions, including exhausted free instance hours, certain bandwidth limits without a payment method, and unusually high service-initiated traffic. None is confirmed for this deployment. Ordinary idle spin-down is separately documented as waking on an incoming request. The operator should inspect the Render service Events, workspace usage/billing, and suspension notification to identify the actual reason. [Render free service documentation](https://render.com/docs/free)

## The program supplied by the mentor

Address: `CSXnfQsFWxdPB5pnS73TQDA6ivK6kcFnRwtt6TgFquxH`.

It matches `declare_id!` in the public Rust source, the server's checked-in IDL, and the mainnet/testnet entries in `Anchor.toml`. The mentor's URL opens the mainnet explorer view. Read-only `getAccountInfo` requests to Solana's public RPCs returned:

| Network | Result | Observed slot |
| --- | --- | --- |
| Solana testnet | Executable program, upgradeable loader owner | 450879297 |
| Solana devnet | Account absent (`value: null`) | 509603713 |
| Solana mainnet-beta | Executable program, upgradeable loader owner | 455324499 |

On testnet, `getMultipleAccounts` at slot 450879505 also returned existing program-owned configuration and escrow accounts:

- Config: `DKxsbcKibCTLFDJ1RYUuxnVnEwkY5CgXX8JUpD6AeaNB`. The Anchor Config discriminator matches; the decoded minimum is seven days.
- Escrow: `2x6DuwSNcBEfCgU75zVfZ4a6jXiJgvLn56qSNfD7cFo1`.

This establishes deployment/account existence. It does not verify the deployed bytecode against source, prove storage works, or grant administrative access. No contract redeployment is indicated merely to repair the API suspension. Never use the repository's default Anchor provider settings blindly: its checked-in provider cluster is mainnet.

[Program on Solscan](https://solscan.io/account/CSXnfQsFWxdPB5pnS73TQDA6ivK6kcFnRwtt6TgFquxH) · [Testnet program](https://solscan.io/account/CSXnfQsFWxdPB5pnS73TQDA6ivK6kcFnRwtt6TgFquxH?cluster=testnet) · [Source configuration](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/solana-programs/Anchor.toml)

## Two different payment routes

- **SOL storage:** the Solana SDK, Toju API, and deployed Solana program. Solana testnet is available at the supplied program address; devnet is not interchangeable.
- **Agent x402 storage:** Toju's `@toju.network/x402` SDK, the Toju API's `/upload/agent` endpoint, and USDC on Base Sepolia (`eip155:84532`). The SDK calls its environment `sepolia`. This route does not use the supplied Solana program.

Both routes still need the API and storage backend. The x402 route matches the requested agent-payment demo and the existing Coinbase EVM wallets. Sharing the Solana contract does not by itself require switching that route.

[SDK environment mapping](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/packages/x402/src/constants.ts) · [HTTP calls in the SDK](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/packages/x402/src/client.ts)

## Can we host it ourselves?

Yes. The public repository contains the Express/TypeScript API. No Dockerfile or Compose file was found in this revision. The official local-development guide describes running from source; it is not a complete offline deployment recipe and some storage references lag behind the implementation.

The current server needs:

- Node/TypeScript runtime and the repository's locked dependencies.
- A database, migrations, and seeded pricing configuration. The application, migration script, and seed script use Neon HTTP. A plain PostgreSQL container requires adapting those callers or a compatible proxy; changing `DATABASE_URL` alone is insufficient.
- Pinata credentials and a gateway for public IPFS files. Storage remains an external service unless this adapter is replaced.
- For x402: a configured USDC recipient, explicit testnet network configuration, funded testnet payer, and a working facilitator. The source selects `https://x402.org/facilitator` for Base Sepolia.
- The full server also requires admin API, QStash signing, and Resend configuration at startup. A reduced agent-only deployment would need deliberate code changes to omit unrelated routes and jobs.
- For the SOL route: the correct testnet RPC and IDL, and any administrative operations performed by an authorized operator. Do not paste private keys into chat.

The SDK supports an endpoint override, so a new API can replace the suspended hostname without replacing the SDK. Hosting the API locally avoids this particular Render outage, but a real public-testnet demo still needs internet access, the chain, storage, and model services. Fully offline would require replacements and would be a simulation.

[Local-development guide](https://docs.toju.network/local-development) · [Server](https://github.com/tojunetwork/afara/tree/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/server) · [Pinata adapter](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/server/src/services/storage/pinata.service.ts)

## Deployment recommendation

For the quickest recovery, the mentor should restore the existing Render testnet service if its database/storage configuration is intact. Render supports this Node/Express application directly, so Docker is optional. If that service cannot be restored, run a separate testnet API locally for the recording, then deploy that tested configuration to a host the team controls. A new cloud deployment still needs its own authorized configuration; the public program address is not deployment access.

Do not pay to upgrade or create a new paid service without a stated budget. Free hosting has suspension and cold-start limits, so verify the complete upload and retrieval shortly before recording and keep the local API ready.

Before treating a self-hosted x402 deployment as demo-ready:

1. Fail closed if the payment recipient or middleware initialization is missing. Upstream currently allows `/upload/agent` without the middleware in these cases.
2. Resolve the quote-unit mismatch in this source revision: the SDK requests `chain=base` and treats `totalCost` as USD, while `getQuoteForFileUpload` treats only `fil` as USD and sends other chains through SOL/lamport conversion. Validate approved cost against the actual x402 challenge before signing.
3. Validate actual file size, network, asset, recipient, and approved amount; retain explicit user approval and duplicate-payment protection.
4. Retrieve and compare the uploaded content. Upstream logs a CID mismatch but returns its locally computed CID; its database transaction marker is synthetic, not an on-chain receipt.

[Render Node deployment](https://render.com/docs/deploy-node-express-app) · [Payment middleware](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/server/src/middlewares/x402.middleware.ts) · [Pricing calculation](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/server/src/utils/pricing.ts)

## Coinbase integration and current validation

Keep Coinbase wallet creation, balance, and transfer code. The existing platform MCP factory does not register Coinbase's x402 action provider. Removed unused AgentKit/AgentKitConfig imports; wallet providers remain. This does not remove the transitive Python x402 dependency: AgentKit 0.7.4 requires x402 below version 2 and its package initializer eagerly imports action-provider modules. Keep Toju's version-2 client isolated rather than upgrading the shared Python environment incompatibly.

Groq unit/integration-boundary checks: 4 passed, including building the real platform tool definitions and confirming no x402 action is exposed. Broader wallet checks: 12 passed, 2 failed in unchanged wallet behavior/tests (balance mock targets the provider while the service constructs Web3 separately; seed test expects UUID content while the service encrypts the configured wallet secret). These failures remain unresolved. No live storage payment, full browser application test, or deployment has succeeded yet. Docker CLI is installed, but its daemon was unavailable during inspection.
