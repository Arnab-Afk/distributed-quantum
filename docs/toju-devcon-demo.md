# DevCon: research agent → Toju storage

Verified October 11, 2026 IST. The full official Toju server runs on Render Free, from [our fork](https://github.com/Winter-Soren/afara/tree/devcon/testnet). QuantumNodes runs locally. Neon and QStash use Free plans. No paid upgrade was selected.

## Record this flow

The recording script below uses a free NVIDIA model through OpenRouter. The key is configured in the ignored backend environment, and one live call successfully prepared the 183-byte “DevCon Final Check” approval card. Groq remains selectable with `AGENT_LLM_PROVIDER=groq`; there is no automatic provider switch. `AGENT_LLM_PROVIDER=openrouter` selects `nvidia/nemotron-3.5-lightning:free`. The backend rejects paid model names and sends zero prompt/completion price ceilings. No paid inference fallback exists.

The final check is [saved in this chat](http://localhost:3000/agents/chat?sessionId=79865ae9-5a43-45d1-a227-d77c5a1e5ffd); its upload remains pending user approval. New chats now keep their session ID in the URL. Browser testing verified that the same session and content survive reload without an additional model request.

1. Open [agent chat](http://localhost:3000/agents/chat). Sign in if needed. Keep both local servers running.
2. Ask: `Draft a short Bell-pair experiment report. Clearly label it a proposal, not an executed result. Prepare a Toju storage proposal for it and ask me to approve.`
3. Show the approval card: exact content, public-IPFS notice, 30-day retention, Base Sepolia, recipient, hash and price. Preparing the card does not upload or pay.
4. Click **Cancel** to demonstrate refusal, or **Approve & store** to authorize that specific export. A direct `yes` approves only the current pending card. The agent cannot approve its own proposal.
5. After approval, show **Stored and retrieved. SHA-256 verified.** Open the artifact and testnet payment links. The client checks an actual USDC Transfer and downloads/hash-checks the stored bytes.
6. Reload the page to demonstrate persisted receipt history. If an outcome is uncertain, use **Check receipt (no new payment)**. Do not make another payment to recover the same upload.

For a completed run, ask to export its run ID. The backend reads that user's saved run, including status and whitelisted input/output metadata; it does not trust invented model results. The live recording test below used a draft, not a completed quantum experiment.

## Already verified sample

- [Open verified chat](http://localhost:3000/agents/chat?sessionId=2bddbf60-5dab-4023-b513-f614ced3185b)
- [Public report](https://gateway.pinata.cloud/ipfs/bafybeiaw3wgnhn5yort3hvvzohvyd6ms43xmjat4qhj4jaazr3e2rnuvie/report.md)
- [Base Sepolia payment](https://sepolia.basescan.org/tx/0x4b9e24bb741676455f1b5aa611d7459bd2b6fbf8666bf8353a2eca84602fa1fe)
- [Toju receipt](https://toju-devcon-testnet.onrender.com/upload/agent/receipt/7d008bec-1ab8-4ec7-b22c-77c0203f9824)
- 193 bytes; 30 days; 0.000001 faucet USDC; SHA-256 `e15da0fabb5b6eb408688ad22010e1a3c8d9be1ba36cf5959071000315f75f47`.

The sample explicitly says the Bell-pair experiment has not run. Its first signing attempt failed before payment; the later upload settled once. A retired HTTP gateway then blocked retrieval, which was recovered through Pinata and receipt reconciliation without paying again. That history remains visible in the chat.

A later draft named “Cancellation check” was **approved by the user**, not cancelled. Toju pinned it, then the x402 settlement returned 402 without a transaction hash. A subsequent chain check found only the first payment and a balance of 0.999999 test USDC. The failed export is preserved as uncertain and cannot be automatically paid again. Diagnostics now expose a bounded settlement reason and explain an unsettled receipt accurately; the historical failure's exact facilitator reason was not captured.

## Spoken script and exact screen actions (about three minutes)

Do a single rehearsal after the live verification is green. Keep provider dashboards, keys, email and environment files out of the recording. Use a fresh chat for the recording; retain the test chat as evidence. Do not claim a new live upload succeeded until the verified label appears.

| Time | Screen action | Say |
| --- | --- | --- |
| 0:00–0:20 | Show QuantumNodes agent chat. | “This is QuantumNodes. I’m demonstrating how a research agent can propose saving its work through Toju, with the user controlling publication and payment.” |
| 0:20–0:40 | Type the exact prompt below and submit once. | “I’m asking for a small experiment plan. This is a draft, so we explicitly distinguish it from an executed quantum result.” |
| 0:40–1:15 | Wait for the reply and its storage card. Expand **Review exact content and payment recipient**. | “The agent proposes storage. Before anything is published, I can inspect the exact content, content hash, recipient, retention and testnet price. It also warns me that IPFS content is public.” |
| 1:15–1:35 | Click **Approve & store** once. | “I approve this specific artifact. The backend checks ownership and the immutable proposal, then signs one capped USDC authorization on Base Sepolia.” |
| 1:35–2:00 | Wait for **Stored and retrieved. SHA-256 verified.** | “Toju stores the file using its actual server and Pinata integration. The app verifies the on-chain transfer and downloads the artifact to compare its SHA-256 with the approved content.” |
| 2:00–2:25 | Click **Open stored artifact**; return, then click **View testnet payment**. | “Here is the public file, and here is its testnet transaction. This uses faucet funds, not real money.” |
| 2:25–2:45 | Return to chat. Type `Thanks. In one sentence, summarize what we saved.` once, only if quota remains. | “The storage receipt stays with the original response. The next messages continue below it, so the conversation remains readable.” |
| 2:45–3:00 | Show the existing verified receipt or reload its saved chat. | “The receipt persists across reloads. If a payment result is uncertain, the app checks the existing receipt rather than automatically paying again.” |

Exact recording prompt:

> Prepare a Toju storage proposal titled DevCon Research Draft for this exact text: “Draft only. Bell-pair plan: prepare two qubits, apply a Hadamard gate to qubit zero, then a controlled-NOT. Measure both qubits. This is a proposed experiment, not an executed result.” Ask me to approve before publishing it.

If asked about hosting, say: “The full Toju server is deployed separately on Render, backed by Neon and signed QStash jobs. QuantumNodes is running locally for this recording. The Solana configuration uses testnet; this agent payment path uses Base Sepolia.”

If an API or model limit interrupts recording, stop that take. Preserve the receipt, wait for the stated reset, and use **Check receipt** for an uncertain upload. The already verified sample can be shown as a completed test, clearly labelled as such. Never narrate a failed attempt as successful.

## Start locally if the running terminals close

From the repository root, in separate terminals:

```sh
cd backend
.venv/bin/quantum-backend --host 127.0.0.1 --port 8081
```

```sh
cd frontend
bun run dev
```

This machine's Bun fallback is `/tmp/quantumnodes-bun/package/bin/bun`. The backend loads its ignored `.env`. The frontend uses its ignored `.env.local`. Keep MongoDB running. Node 22 and `npm ci` in `backend/toju-client` are required when recreating the environment. `TOJU_NODE_BINARY` points to the installed Node 22 binary here.

Required configuration names are documented in both `.env.example` files. Groq and CDP credentials stay in the backend; Pinata, Neon, Resend and job-signing credentials stay in the Toju service. The frontend/backend share a server-only `AGENT_AUTH_BRIDGE_SECRET`; never give it a public environment-variable prefix.

Before recording, open [Toju health](https://toju-devcon-testnet.onrender.com/health) and wait for `healthy`, then open the chat. Free Render can take 50 seconds or more to wake. Groq Free may rate-limit requests; wait for its reset instead of enabling a paid fallback. There is no automatic mainnet fallback.

## Deployment and limits

Follow [the Render testnet guide](toju-render-testnet-guide.md) for build/start commands and environment setup. The Solana route is configured for **Solana testnet** with the mentor's existing program. Agent x402 payments use **Base Sepolia**, because that is Toju's EVM testnet payment route.

QStash schedules (UTC): warnings 00:00 daily; expiration cleanup 00:10 daily; debt cleanup 00:20 daily; usage snapshot 00:30 daily; usage comparison Sunday 00:40. One signed usage-snapshot request was delivered successfully. Destructive `/jobs/destroy` is not scheduled.

Checks passed: 16 focused backend tests, 4 Node client tests, frontend TypeScript, full Toju build and 2 server payment-policy tests, browser login/proposal/approval, real testnet settlement, public retrieval, and receipt recovery. No real-money payment was made.

Not verified end to end: full quantum experiment execution, Solana/Filecoin payments, renewal UI, Toju notification emails, and time-based deletion. The separate Toju Vite frontend is not deployed. Free-tier quotas/cold starts remain a demo risk; public IPFS copies may outlive the requested pinning period.
