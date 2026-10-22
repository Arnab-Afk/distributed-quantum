# Toju agent storage: research and proposed demo scope

> Historical research/diagnosis. Deployment subsequently succeeded on October 11, 2026 IST: the full official Toju fork is live on Render and a Groq agent export/payment/retrieval was verified. Current status and reproduction steps are in [the deployment guide](toju-render-testnet-guide.md) and [demo guide](toju-devcon-demo.md). Earlier “not yet tested/deployed” statements below describe the investigation at that time.


Research date: October 10, 2026. This is a research brief and design proposal, not an implementation or a successful live-test report.

## Requested outcome

- Use the existing agent chat to create drafts/reports and work with quantum experiments.
- Let the user request storage of a report, a particular run, run metadata, run results, or metadata plus results.
- Let the agent suggest storing useful content, but require explicit user approval before upload or payment.
- Replace paid Claude inference in the demo flow with Groq. Do not fall back to a paid provider.
- Use test networks only. Demonstrate the running backend and frontend through the browser extension, including retrieving the exported content.

## Sources reviewed

Read all 13 documentation source pages listed in Toju's `docs/mint.json`: introduction, quickstart, pricing, local development, storage payments, CID computation, renewal concepts, SDK overview, deposits, SOL price, upload history, SDK renewal, and x402 agent payments.

Also inspected the live website and documentation in the connected browser, read the full auto-generated transcript and description of the requested video, and inspected the x402 SDK and corresponding server implementation.

- [Toju website](https://www.toju.network/)
- [Documentation](https://docs.toju.network/introduction)
- [Agent payments](https://docs.toju.network/sdk/x402)
- [Requested video: Your AI agent just paid for its own decentralized storage](https://www.youtube.com/watch?v=7M0RPbH89HE)
- [Source repository](https://github.com/tojunetwork/afara), inspected commit `a0053d5fdd81904e00d1f6ac5889af31a8153d9d`
- [Agent SDK implementation](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/packages/x402/src/client.ts)
- [Agent SDK environments](https://github.com/tojunetwork/afara/blob/a0053d5fdd81904e00d1f6ac5889af31a8153d9d/packages/x402/src/constants.ts)
- [Groq local tool calling](https://console.groq.com/docs/tool-use/local-tool-calling)
- [Groq OpenAI compatibility](https://console.groq.com/docs/openai)
- [Groq free-plan limits](https://console.groq.com/docs/rate-limits)

The supplied website and video consistently identify Toju. I have treated “Sjozu.network” as referring to the same product.

## What Toju supplies

Toju is a payment bridge for time-limited IPFS storage. It does not export a model, deploy an agent, or run quantum experiments. Our application must construct the artifact; Toju stores its bytes and charges for the requested duration.

| Payment path | SDK | Development network | Fit for this request |
| --- | --- | --- | --- |
| Autonomous USDC payment | `@toju.network/x402` | Base Sepolia, `eip155:84532` | Recommended; this is the video's flow |
| SOL wallet payment | `@toju.network/sol` | Solana testnet/devnet | Requires a different wallet and payment integration |
| USDFC wallet payment | `@toju.network/fil` | Filecoin Calibration | Supported alternative with additional wallet/token setup |

The agent SDK's `environment: "sepolia"` points to `https://staging-api.toju.network`. The Base Sepolia USDC address is `0x036CbD53842c5426634e7929541eC2318f3dCF7e`.

Agent upload contract:

1. Quote: `GET /pricing/quote?size=<bytes>&duration=<days>&chain=base`.
2. Upload: multipart `POST /upload/agent?size=<bytes>&duration=<days>`, field `file`.
3. Handle the HTTP 402 challenge through the x402 client, signing the requested USDC authorization and retrying with the protocol payment header.
4. Response: `cid`, `expiresAt`, `fileName`, and `fileSize`.

The video demonstrates a duplicate upload error followed by a successful different-file upload for 60 days on staging using test USDC. The duplicate is a Toju behavior; IPFS immutability itself does not generally forbid uploading the same bytes again.

## Documentation and implementation differences

- Some docs still describe Base as forthcoming, while the x402 package and server implement it. The x402 options table mentions only mainnet, but the source types and example explicitly support `sepolia`.
- The video describes Storacha. The inspected server now uses Pinata public IPFS uploads. Do not claim that the current path proves Filecoin persistence without further evidence.
- The landing page mentions encryption, but the inspected agent upload path sends the file directly to public pinning. Treat artifacts as public unless our application encrypts them explicitly. A testnet payment does not make the file private.
- The x402 SDK supplies upload and quote methods, not an agent renewal method. SOL renewal documentation should not be presented as an implemented USDC renewal flow.
- Human-wallet docs specify a seven-day minimum; the inspected agent handler accepts positive integer days. A conservative initial UI can use 30 days while exposing the actual chosen duration in approval.
- The SDK's estimate rounds to six decimals, while the server payment middleware imposes a one-micro-USDC minimum. Validate the actual payment challenge against the approved maximum; do not assume the estimate is the final charge.
- The agent controller records a synthetic `x402:base:...` reference rather than returning a real on-chain hash. Only render a block-explorer receipt when a real settlement transaction has been obtained and verified.
- The handler computes a CID before pinning, logs a mismatch with the pinning service's CID, and returns the computed value. Fetching the returned CID and checking the exported bytes is therefore an essential acceptance check.
- Expiry concerns the provider's pinning period. Unpinning is neither permanent storage nor a guarantee that all other copies disappear.

## Live availability finding

On October 10, 2026, a read-only request to the documented staging quote endpoint returned HTTP 503, `x-render-routing: suspend`, and “Service Suspended.” No payment or upload was attempted.

This blocks proving a hosted Toju testnet upload today. A restored staging service, a working alternative supplied by Toju, or a separately configured deployment of Toju on Base Sepolia would be needed. A self-hosted instance would still require storage credentials, database configuration, payment recipient configuration, and a working facilitator. Local mocks may test our error handling, but cannot count as the live demo passing.

## Existing project integration points

| Area | Existing code | Findings |
| --- | --- | --- |
| Chat UI | `frontend/src/app/(main)/agents/chat/page.tsx` | Existing agent selection, conversation, and session flow |
| Chat forwarding | `frontend/src/app/api/agentkit/agents/[id]/chat/route.ts` | Forwards requests to Python; currently does not forward authenticated identity |
| Chat endpoint | `backend/src/api/v1/agents.py` | Checks ownership through `CurrentUser` and invokes the agent service |
| Model/tool loop | `backend/src/services/ai_agent_service.py` | Claude through Bedrock; up to eight tool-call rounds |
| Agent tools | `backend/src/mcp_server/platform_mcp.py` | Existing drafts/proposals, circuit, pharma, finance, risk, and wallet tools |
| Wallets | `backend/src/services/agentkit_service.py` | CDP wallets; default network is Base Sepolia; installed provider supports typed-data signing |
| Conversation persistence | `frontend/src/features/agentkit/hooks/use-chat-sessions.ts` and backend chat-session endpoints | Reuse for artifact proposals and receipt rendering, with server-authoritative pending approval |
| Separate agent workspace | `backend/src/quantum_backend_v2/agent/` | Has hardcoded user identity and placeholder execution; not the recommended demo entry point |
| Existing x402 feature | `frontend/src/features/x402/server/` | Algorand payments for quantum execution, a separate purpose and network |

No Grok, Groq, or xAI references were found in the searched backend/frontend application source. Groq is the requested inference provider; it is distinct from xAI's Grok model family.

Authentication needs work along the touched chat/export flow: the Python auth resolver currently supports explicit development tokens or a development bypass, not validation of Better Auth sessions. Some existing MCP job tools also use unscoped localhost requests. Export authorization must be enforced on the server against the artifact's real owner; do not trust an LLM-supplied user ID or unrestricted run ID.

## Proposed behavior

Examples:

- “Draft a report of this experiment.” → draft in chat; agent may suggest storing it.
- “Store this run's results for 30 days.” → a concrete pending export with the selected run and results.
- “Store only its metadata.” → a separate metadata-only export proposal.
- Agent: “I think this report would be useful to keep. Store it on IPFS for 30 days?” → no upload or payment yet.
- User approves the displayed proposal → execute the one approved export and return a persistent receipt.

Keep the initial artifact formats small: Markdown for generated reports/drafts and versioned JSON for structured run exports. Use selected server-owned content, not arbitrary server filesystem paths. Preserve experiment outputs faithfully and distinguish generated narrative from measured/simulated results.

The server stores an immutable snapshot or content hash with each pending proposal, bound to user, agent, conversation, artifact, duration, public visibility, and maximum price. The UI displays that proposal. A “yes” can resolve only one unambiguous pending proposal in that conversation; if the conversation has moved on or multiple proposals exist, ask which one. A model's own assertion that approval exists is insufficient.

Both chat approval and an explicit approve control must reach the same server validation. Changes to contents, duration, or price above the approved maximum require a new approval. Cancellation makes no storage call. Retrying a click or repeating “yes” must not pay twice. Persist in-progress and uncertain outcomes and reconcile them instead of blindly replaying paid requests.

Receipt: artifact name/type, run reference where applicable, CID, gateway link, Base Sepolia label, expiry, quoted versus confirmed payment information, and verification status. Retain receipts across refresh. Never label an upload verified until retrieving the expected content succeeds.

## Groq migration

Use Groq's OpenAI-compatible chat completions endpoint and local function calling. Keep MCP tool execution in the Python backend; no public MCP deployment is needed. Reuse installed `httpx` for the request layer rather than introducing a framework solely to switch model APIs.

Convert existing tool definitions and tool-result messages to the supported format, retain bounded tool rounds, handle malformed arguments and unknown tools, and report rate limits clearly without replaying completed side effects. Choose a currently available free-plan tool-capable model after checking the account; `openai/gpt-oss-20b` is a documented candidate, not yet a live-tested choice.

Use backend-only `GROQ_API_KEY` and `GROQ_MODEL`; no keys in responses, prompts, logs, frontend bundles, or source control. Stay on the free plan and disable paid fallback. Audit every inference path reachable from the demo tools: changing only `chat()` would leave other proposal/analysis Bedrock calls in the repository.

The signed-in Groq console confirms that the current plan is Free ($0). The user created the `quantumnodes-devcon` key in the console; it is saved only in the Git-ignored `backend/.env`. The console displayed no expiry. The Groq tool loop now has four passing checks, including its real MCP tool definitions; a live browser chat has not yet been tested.

## Implementation approaches to compare

1. **Recommended: Python-owned exports.** Extend the existing Python MCP tool path, persist proposals and receipts with existing MongoDB, and use an official Python x402 client with a CDP typed-data signer adapter. This keeps agent identity, approvals, artifacts, and wallet decisions together. The adapter's compatibility still needs a focused test.
2. **Use Toju's TypeScript SDK.** Put `@toju.network/x402` behind a server-only integration in the existing Next.js runtime. This follows Toju's exact SDK but introduces an authenticated Python-to-TypeScript boundary and the SDK currently expects an EVM private key rather than the existing CDP wallet interface.

Solana wallet uploads remain possible, but would add another wallet stack and differ from the requested agent-payment video. Recommend Base Sepolia for the first complete demo.

## Verification required before recording

- Backend tests: Groq tool loop, tool errors, no Bedrock fallback, ownership, approval binding, changed-content rejection, cancellation, duplicate approval, stale quote, rate limiting, upload failure, uncertain payment outcomes, persistence, mainnet rejection, and real receipt validation.
- Start the existing backend through its normal startup wrapper and the frontend with the repository's prescribed Bun commands. Use controlled demo data and funded testnet wallets.
- Browser exercise: sign in, draft a report, see a storage suggestion, decline once, approve once, inspect receipt, open the stored file, reload and recover receipt, export run metadata separately from results, and repeat approval without another payment.
- Live acceptance: demonstrate a real testnet payment and successful content retrieval. Record model, service/network, artifact, receipt, and test result evidence without exposing secrets.
- The connected extension currently identifies itself as Chrome. Brave was not available in the browser inventory. The user subsequently authorized using this Chrome extension.

No product code, network payments, or storage uploads were performed during this research phase. Existing unrelated working-tree changes were observed and left intact.

## Subsequent deployment investigation

See [deployment diagnosis](toju-deployment-diagnosis.md) for the current Render suspension evidence, the mentor-supplied program verified on Solana testnet, self-hosting requirements, and the AgentKit/x402 dependency constraint. The Python-only transport proposal above has been superseded by an isolated TypeScript x402 v2 client to preserve the existing Coinbase wallet integration.
