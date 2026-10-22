# Groq and Toju testnet implementation plan

Goal: implement the approved research draft in docs/toju-agent-storage-research.md.
Execution: in this existing working directory, preserving unrelated changes. User explicitly requested implementation, so no additional design approval gate.

## Constraints
- Groq or explicitly configured free OpenRouter/NVIDIA inference; no paid fallback.
- Toju staging and Base Sepolia only; never use mainnet in application code.
- User-approved immutable export proposals, server ownership checks, public-visibility notice, capped payment, no automatic replay of uncertain payments.
- No credentials in source control, browser-facing code, model prompts, or logs.

## Tasks
- [x] Add a tested async Groq tool loop using httpx; wire the existing agent service and demo-reachable inference calls.
- [x] Add tested Toju quote/upload transport using an isolated Node x402 v2 client and the existing CDP wallet signer; preserve AgentKit's Python x402 v1 dependency and enforce chain, token, recipient and amount policy before signing.
- [x] Add MongoDB-backed immutable export proposals and atomic approval transitions; bind approvals to session/user/agent, persist receipts, handle cancellation and uncertain outcomes.
- [x] Connect draft/run export tools to chat. Return structured proposals and receipts and support explicit approval UI; interpret a direct yes only against the active proposal with server checks.
- [x] Add authenticated frontend forwarding for the touched AgentKit routes, approval cards, persistence, and clear unavailable-service states.
- [x] Test backend and frontend, start both, exercise UI using computer use, and record exact external blockers.

## Test focus
- Unauthenticated/cross-owner requests and forged model approval.
- Duplicate/concurrent approvals and timeouts after signing.
- Changed artifact/quote, wrong network/token/payee, rate limits and malformed tool calls.
- Public visibility, content retrieval, expiry, and truthful settlement display.
- Groq missing credentials and Toju 503 must never become fake success or paid fallback.

## Completed and verified

- Full official Toju fork deployed on Render Free; Neon Free and QStash Free configured.
- Groq `openai/gpt-oss-20b` live tool call prepared an immutable proposal and stopped for approval.
- Better Auth session forwarded as a short-lived HMAC assertion; agent/session/run ownership enforced server-side.
- Existing Coinbase AgentKit wallets retained; automatic AgentKit x402 tools removed from the chat path. `backend/toju-client` uses the existing CDP signer for one explicitly approved Base Sepolia payment.
- Approved sample stored and retrieved with SHA-256 verification; actual on-chain USDC Transfer verified; uncertain outcome recovered without repaying.
- 16 focused Python tests, 4 Node client tests and frontend TypeScript check passed. The full Toju server build and 2 payment-policy tests passed before deployment.
- Exact deployment, known limits and recording script: `docs/toju-render-testnet-guide.md` and `docs/toju-devcon-demo.md`.
- Original vendor endpoints returned Render suspension responses. The client now targets our full Toju deployment explicitly.
