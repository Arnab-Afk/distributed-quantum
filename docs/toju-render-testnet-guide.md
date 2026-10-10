# Deploy Toju staging/testnet on Render

Updated October 11, 2026 (IST). The full Toju server is deployed and the agent payment/upload/retrieval flow has passed a live browser test. It adapts the mentor's [mainnet launch playbook](https://app.notion.com/p/mainnet-launch-playbook-3f5c9a95088b804b80dbd0684514bd01), read in the signed-in browser through its final launch-log section.

## Deployed installation

- API: https://toju-devcon-testnet.onrender.com (`/health` returns database/server up).
- Source: https://github.com/Winter-Soren/afara/tree/devcon/testnet, commit `e0a18f3a7c62ccac65e55a6168689b1b17085504` (adds settlement diagnostics to the verified deployment), a fork of the official Toju repository.
- Render: Free Node service in Singapore; full upstream route families and lifecycle jobs retained. QuantumNodes runs locally and is not deployed on Render.
- Neon: Free project `toju-devcon-testnet`; ten migrations applied and pricing configured.
- QStash: Free EU region, five schedules active; signed `/jobs/usage/snapshot` delivery verified as DELIVERED.
- Gateway: `https://gateway.pinata.cloud`; the retired `ipfs.io` HTTP gateway returned 429 and must not be used for the demo.
- Proven flow: Groq draft → explicit approval → one Base Sepolia faucet-USDC payment → Toju/Pinata upload → chain Transfer and downloaded SHA-256 verification. Receipt reconciliation also passed without a second signature or payment.

See [recording steps and proof](toju-devcon-demo.md). Sections below reproduce this installation; warnings about upstream bugs refer to the original revision and are fixed in the deployed fork.

## What we are deploying

Deploy the **Toju Node/Express API** from `tojunetwork/afara`, separately from the QuantumNodes Python backend. No Docker image or new Solana contract deployment is needed merely to bring this API online.

The mentor's branch convention is `dev` for staging and `main` for production. At inspection, `dev` was `04d8732d3afa207442e3ff3f5cb0fe49c3104bba` and `main` was `a0053d5fdd81904e00d1f6ac5889af31a8153d9d`; their server, x402 package, and root lockfile had no differences. Recheck these files if deploying a later revision.

Two test networks are relevant:

| Storage payment route | Network | Required on-chain component |
| --- | --- | --- |
| SOL wallet / Solana SDK | **Solana testnet** | Existing Toju program `CSXnfQsFWxdPB5pnS73TQDA6ivK6kcFnRwtt6TgFquxH` |
| Agent x402 / USDC | **Base Sepolia**, chain ID `84532` | Test USDC and an x402 recipient; this route does not call the Solana program |

The agent demo uses the second route. The same API can also serve the first. October 10 read-only RPC checks found the supplied program plus config/escrow on Solana testnet; devnet had no program at that address. Do not substitute devnet or run the mainnet deployment commands from the playbook.

## 1. Decide whether to restore the existing staging service

If the mentor controls the old Render service, first open its **Events**, **Logs**, and workspace usage/billing. The observed `503` / `x-render-routing: suspend` comes from hosting, and a new build alone may not remove a workspace suspension. Resolve the reason shown by Render, then redeploy the staging service with its existing staging resources.

Otherwise create a separate service using the steps below. Start with its supplied `onrender.com` URL; a custom domain is optional. You need repository access plus access to staging Neon, Pinata, Resend, and QStash configuration. Use dashboard invitations or your team's secret manager; don't copy production secrets or paste wallet private keys into chat.

## 2. Prepare an isolated staging database and service credentials

Use a **separate empty Neon database** for this installation, or the existing verified staging database. The current server uses Neon HTTP in its application, migration runner, and seed script. A generic Render Postgres URL is not a drop-in replacement without changing those drivers.

Use staging storage credentials/resources for Pinata and staging QStash schedules. The expiration jobs can remove pins, so sharing production storage and copying production schedules is inappropriate for this deployment.

For the full upstream server, prepare the variables listed in step 4 even if your first demo only uses x402. Its startup validation requires the email and QStash signing settings too. Do not use dummy credentials to make the health check pass.

## 3. Create the Render Web Service

In Render, choose **New → Web Service**, connect the Toju repository or your reviewed fork, and enter:

| Setting | Value |
| --- | --- |
| Name | `toju-devcon-testnet` |
| Runtime / Language | Node |
| Branch | `devcon/testnet` in `Winter-Soren/afara` |
| Root Directory | **Leave blank** (repository root) |
| Build Command | See below |
| Start Command | See below |
| Health Check Path | `/health/live` (liveness); use `/health` for database readiness |
| Auto-deploy | Disable while preparing the recording; deploy a reviewed commit manually |
| Instance | Free if available and sufficient for development; review its limits before relying on it for the recording |

Keep the repository root because the lockfile and `pnpm-workspace.yaml` live there. Setting Render's root to `server` hides the parent workspace files. [Render monorepo rules](https://render.com/docs/monorepo-support)

Build command:

```sh
corepack pnpm --filter server... install --frozen-lockfile --prod=false && corepack pnpm --dir server run build
```

Start command:

```sh
corepack pnpm --dir server exec tsx scripts/migrate.ts staging && node server/dist/index.js
```

The root `packageManager` pins pnpm 10.11.0; Corepack uses that pin. Development dependencies are included because the build needs TypeScript. The migration command runs from `server`, where its `drizzle` directory lives. The `staging` argument selects the migration script's environment-file convention; **the actual target database is still `DATABASE_URL`**. No `.env` file is needed on Render when variables are configured in its dashboard.

The upstream `start` script runs the migration runner with the argument `production` and recompiles on every start. The explicit command above avoids that ambiguity. Run only one instance/migration process during initial setup. The deployed runner executes each migration and its completion marker in one Neon transaction. Inspect migration errors before retrying or editing an already applied migration.

These commands built and started the deployed service successfully. [Render Node deployment](https://render.com/docs/deploy-node-express-app)

## 4. Set the Render environment variables

Enter secret values in Render's **Environment** section, not in Git. Substitute your actual staging values for placeholders.

| Variable | Staging value / purpose |
| --- | --- |
| `NODE_VERSION` | `22.22.3` as an explicit reproduction baseline; test and pin a newer supported patch before upgrading |
| `NODE_ENV` | `staging` for this inspected revision; see the network caveat below |
| `HUSKY` | `0` (skip local Git-hook setup during deployment) |
| `SKIP_INSTALL_DEPS` | `true` (the explicit build command installs with pnpm) |
| `DATABASE_URL` | Neon connection string for the isolated staging database, with its required TLS options |
| `ADMIN_API_KEY` | A separate high-entropy staging API secret, stored securely |
| `PINATA_JWT` | Authorized staging Pinata credential |
| `PINATA_GATEWAY` | Full gateway origin, e.g. `https://YOUR-GATEWAY.mypinata.cloud`; no trailing `/ipfs` |
| `RESEND_API_KEY` | Valid key for the staging email sender |
| `EMAIL_FROM` | Sender verified in your Resend account |
| `EMAIL_REPLY_TO` | Your approved support address, if used |
| `BASE_URL` | Staging **frontend** URL used in email links |
| `QSTASH_CURRENT_SIGNING_KEY` | Current signing key for staging job delivery |
| `QSTASH_NEXT_SIGNING_KEY` | Next signing key from the same QStash configuration |
| `SOLANA_RPC_URL` | `https://api.testnet.solana.com`, or a provider endpoint explicitly serving Solana **testnet** |
| `SOLANA_PROGRAM_IDL` | Entire JSON content of `server/src/utils/solana/idl.json`; verify its `address` is the supplied program ID |
| `X402_NETWORK` | `sepolia` |
| `BASE_USDC_WALLET` | Your chosen staging EVM payment-recipient public address (`0x…`), not a private key |
| `FILECOIN_NETWORK` | `calibration` to keep the separately mounted Filecoin routes on testnet |

Leave `PORT` at Render's supplied value. The server reads it. Optional monitoring: `SENTRY_DSN` and the `BTRSTACK_*` variables documented in `server/src/utils/logger.ts`. Groq and Coinbase wallet-signing secrets belong to **QuantumNodes**, not this storage API.

**Why `NODE_ENV=staging` here?** Render normally sets `NODE_ENV=production` at runtime. This source revision's Filecoin deposit response selects a mainnet token when that value is `production`, while its verification code uses `FILECOIN_NETWORK`. Explicit `staging` avoids the mismatch. This is a compatibility workaround; the proper code fix is to derive both from `FILECOIN_NETWORK`, then use normal production runtime settings independently of the blockchain. `NODE_ENV` alone does not control Solana or x402. [Render environment defaults](https://render.com/docs/environment-variables)

`ADMIN_KEYPAIR` is **not needed merely to read an already initialized Solana config or use the x402 route**. The server loads it when initialization is required; the seed script also requires it. For authorized Solana administration, use the correct staging authority through a secret manager. A newly generated wallet does not become administrator of the existing contract. Do not put a mainnet upgrade-authority key into this service to get past an error.

The Notion guide lists `QSTASH_URL` and `QSTASH_TOKEN`: keep these with the process/dashboard that creates schedules. The inspected API receives signed jobs and requires the two signing keys; it does not read those publishing variables. Likewise, its current email code reads `EMAIL_FROM`, `EMAIL_REPLY_TO`, and optionally `PROMULGATOR`; don't assume every historical variable is still consumed.

## 5. Migrate and initialize pricing

Deploy once with the environment configured. The start command runs migrations against the staging database. In Neon SQL Editor, verify you have selected that database, then inspect:

```sql
SELECT id, admin_key, rate_per_byte_per_day, min_duration_days,
       withdrawal_wallet, filecoin_wallet
FROM config;
```

If restoring a working staging database, preserve its reviewed configuration. If this is a fresh database, replace the two public-key placeholders below with the values from the **testnet** program config, confirmed by its operator. They are public addresses, not private keys. For an x402-only installation, these Solana fields are still required by the schema but do not select the Base recipient; that is `BASE_USDC_WALLET`.

```sql
INSERT INTO config (
  id, admin_key, rate_per_byte_per_day, min_duration_days,
  withdrawal_wallet, filecoin_wallet
)
VALUES (
  1,
  'REPLACE_WITH_TESTNET_CONFIG_ADMIN_PUBLIC_KEY',
  0.000000000003,
  7,
  'REPLACE_WITH_TESTNET_CONFIG_WITHDRAWAL_PUBLIC_KEY',
  NULL
)
ON CONFLICT (id) DO NOTHING;

SELECT COUNT(*) AS config_rows FROM config;
SELECT id, rate_per_byte_per_day, min_duration_days FROM config;
```

Expect exactly one config row and confirm the rate is approximately `3e-12` USD/byte/day. `NULL` leaves Filecoin payments unconfigured; do not exercise that route unless you separately configure a calibration recipient. The Base recipient is independent.

**The original upstream seed had an incorrect rate of `3000000000.0`; the deployed fork fixes it to `0.000000000003`.** The quote and payment code multiply the database rate directly. Also, a default primary-key value of 1 does **not** enforce a singleton table: explicitly verify that there is only one row. Both points differ from assumptions in the Notion guide.

## 6. Verify the API and deployed payment fixes

With the actual Render URL:

```sh
TOJU_STAGING_URL='https://YOUR-ACTUAL-SERVICE.onrender.com'
curl --fail-with-body --max-time 90 "$TOJU_STAGING_URL/health"
curl --fail-with-body --max-time 90 "$TOJU_STAGING_URL/pricing/quote?size=1000000&duration=30&chain=sol"
```

`/health` should return JSON with `status: healthy` and database/server `up`. This health check only proves database connectivity and a running server. A quote request also checks pricing configuration; the SOL quote uses an external price feed. [Render health checks](https://render.com/docs/health-checks)

The deployed branch includes these fixes to the original source:

1. **Correct Base quote units.** `server/src/utils/pricing.ts` currently treats only `chain=fil` as USD and sends `base` through SOL/lamport conversion. Base must use USD too, with consistent duration and rounding relative to the payment challenge. For 1,000,000 bytes × 30 days × `3e-12`, the USD amount is `0.00009`; the x402 atomic amount is `90` micro-USDC. Enforce the minimum duration consistently.
2. **Require the x402 gate.** Missing `BASE_USDC_WALLET` or middleware initialization failure currently leaves `/upload/agent` available without payment. Make the route unavailable/startup fail in either case. Verify declared size matches the received bytes and bound upload sizes.
3. **Verify the receipt and content.** The handler currently logs a CID mismatch but returns its precomputed CID; require retrieval of the exact exported bytes before reporting success. Its synthetic database transaction marker is not an on-chain transaction hash.

After fixing the gate, this unpaid request should return **402** and the correct testnet challenge; it sends neither a file nor a signature:

```sh
curl --max-time 90 -i -X POST "$TOJU_STAGING_URL/upload/agent?size=1000000&duration=30"
```

Check the decoded challenge: network `eip155:84532`, USDC asset `0x036CbD53842c5426634e7929541eC2318f3dCF7e`, your configured recipient, and the approved amount. A 400 “No file uploaded” instead of 402 suggests the handler was reached without a payment gate. Do not proceed to upload until that is resolved.

The fork also fixes migration execution/SQL, bounds uploads, persists real settlement hashes, binds export IDs to exact content, and provides receipt recovery. Live payment and retrieval are verified; health alone would not establish that.

## 7. Connect the application to the new API

Use the actual Render URL as the SDK's explicit endpoint. Otherwise the SDK still calls the suspended default hostname.

Server-side agent SDK configuration:

```ts
createAgentClient({
  privateKey: testnetPrivateKeyFromSecretStore,
  environment: 'sepolia',
  endpoint: 'https://YOUR-ACTUAL-SERVICE.onrender.com',
})
```

This illustrates the SDK endpoint setting, not a replacement for QuantumNodes' planned CDP signer and approval controls. Never expose the key in browser code. The app must approve an immutable artifact and payment limit before the SDK is allowed to upload.

For the SOL route, configure `Environment.testnet`, an explicit testnet `rpcUrl`, and the same custom `endpoint` on the Solana client. Avoid automatic RPC-name inference with opaque provider URLs: the SDK defaults unknown URLs to its production endpoint.

If deploying Toju's own Vite UI as well, use `VITE_SOLANA_NETWORK=testnet`, `VITE_FILECOIN_NETWORK=calibration`, and `VITE_API_URL` set to this API, then rebuild. Some current hooks only pass the custom API URL in development builds; check upload, quote, history, and renewal requests in the production build and fix those hooks to honor the override. These `VITE_*` variables do not configure QuantumNodes' Next.js frontend.

Add `staging-api.toju.network` as a Render custom domain only if the mentor controls it. Follow the DNS target Render displays, verify TLS, then switch the client endpoint. The `onrender.com` URL is sufficient to begin testing.

## 8. Configure lifecycle jobs and accept the demo

In the staging QStash configuration, review the schedules targeting this API's `/jobs/send-warnings`, `/jobs/delete-expired`, and `/jobs/remove-debtors` routes. They must use the matching signing keys and staging resources. Do not copy a production destructive job; `/jobs/destroy` is not a routine schedule. Optional usage jobs are `/jobs/usage/snapshot` and `/jobs/usage/compare`. A successful upload without lifecycle jobs does not prove expiration cleanup is operating.

For the DevCon acceptance run:

1. Confirm the Groq agent drafts a report and offers storage without uploading it.
2. Review the exact artifact, public-IPFS visibility, duration, testnet recipient, and payment cap; decline once, then approve a fresh proposal.
3. Complete one payment with faucet-funded Base Sepolia test USDC. If demonstrating SOL separately, use testnet SOL and a testnet-configured wallet.
4. Retrieve the file through the gateway and compare its bytes/hash with the approved artifact.
5. Refresh and recover the receipt. Repeat approval and verify no second payment occurs.
6. Exercise an unavailable API and verify the app reports failure without claiming storage or switching to mainnet.

Free Render services can sleep after inactivity and can be suspended at usage limits. Test shortly before recording; using testnet does not make hosted database/storage/email resources inherently free. Review current dashboard pricing rather than treating the playbook's historical cost table as a current quote. [Render free-service limits](https://render.com/docs/free)

## Troubleshooting

| Symptom | Check |
| --- | --- |
| HTML 503 “Service Suspended” | Render service/workspace suspension notice; distinguish this from application JSON errors |
| JSON 503 from `/health` | Neon connection, TLS, database availability |
| Startup missing-environment error | Required variables in step 4; the old `.env.example`/Notion list is incomplete |
| Quote 400 / config not found | Completed migrations and one seeded config row |
| Astronomical quote | Accidental `3e9` seed rate; inspect the database before changing it |
| Base quote much larger than 0.00009 for the example | Base quote routed through SOL conversion; step 6 fix |
| Request still hits suspended hostname | SDK endpoint override or production UI hook ignored it |
| Successful upload but gateway 404/wrong file | Directory CID needs filename; investigate computed/pinned CID mismatch |
| Network unexpectedly mainnet | Inspect RPC, SDK environment, x402 challenge, Filecoin selector, and built UI settings separately |

## Sources and limits

Read the mentor's full Notion playbook and checked current public source, including `server/src/index.ts`, `server/package.json`, migration/seed scripts, schema, pricing, x402 middleware, Pinata adapter, SDK endpoint configuration, and UI callers. [Inspected staging source](https://github.com/tojunetwork/afara/tree/04d8732d3afa207442e3ff3f5cb0fe49c3104bba/server)

The playbook describes an older Storacha setup and historical deployment costs; current source uses Pinata. Its February launch log also says a contract update was postponed, so source code existing on GitHub does not establish that the deployed bytecode matches it. A bytecode/source verification or contract upgrade was not performed.

Deployment, migrations, pricing, one signed job, and one public agent export are verified. No DNS change or contract upgrade was made. Solana payments, Filecoin payments, expiration/deletion, renewal UI and Toju notification emails have not been exercised end to end. The separate Toju Vite frontend is not deployed; email renewal links still use the upstream default. Free services can sleep or reach quotas; this is a testnet demonstration, not a production availability guarantee.
