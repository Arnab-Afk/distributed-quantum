<div align="center">

# QMeshPy: Distributed Quantum Services with Algorand x402

**Quantum computation as discoverable, machine-payable peer-to-peer services powered by py-libp2p, Qiskit, and Algorand x402.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Qiskit](https://img.shields.io/badge/Qiskit-1.x-6929C4?logo=ibm&logoColor=white)](https://qiskit.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/QMeshPy/distributed-quantum?color=brightgreen)](https://github.com/QMeshPy/distributed-quantum/commits/main)

</div>

---

## What this is

A research platform that treats quantum operations as network services. A FastAPI coordinator discovers worker peers over py-libp2p (GossipSub), compiles OpenQASM circuits into distributed execution plans, routes fragments to workers over libp2p streams, and assembles results with Qiskit statevector simulation. A Next.js operator console shows the peer network, job lifecycle, and quantum analysis live.

The same infrastructure powers a QAOA portfolio optimizer that benchmarks quantum against classical baselines.

[Watch the demo video](https://www.loom.com/share/8c5a546cb99a4a98996e738bf23c3e7a)

> **Scope:** this is a proof-of-concept on simulators, not a quantum hardware stack. Auth is dev-mode only.

### Applications

| Application | What it does | Status |
|---|---|---|
| Circuit orchestration | Normalize OpenQASM, plan, and execute distributed fragments across worker peers | Available |
| Financial modelling | QAOA portfolio benchmarks against classical optimization | Available |
| Risk and options | Simulated VaR, CVaR, credit-risk, and option-pricing experiments | Available |
| Molecular workflows | Drug-discovery research pipeline with simulated quantum stages | Experimental |

### Architecture

```
  Next.js operator console  ──(BFF proxy, REST)──▶  FastAPI coordinator
                                                          │
                                           py-libp2p runtime (Trio)
                                      Ed25519 host · GossipSub · stream RPC
                                                          │
                                       ┌──────────────────┼──────────────────┐
                                  Worker peer        Worker peer        Worker peer

  Persistence: Postgres (event-sourced) · MongoDB (projections) · JSONL (peer log)
```

### Headline result

97% of QAOA runtime is classical COBYLA parameter search, not the quantum circuit, so adding quantum nodes yields at most 1.03x speedup (Amdahl's Law). The advantage shows up in scaling: classical wins at 10 to 20 assets, and QAOA wins from about 40 assets (3.2x faster at 40, 9.5x at 60). The full analysis is in the [research paper draft](https://github.com/QMeshPy/documentations/blob/main/research/RESEARCH_PAPER_DRAFT.md).

---

## ⚡ Algorand x402: Machine-Payable Quantum Computing

> **QMeshPy is a decentralized quantum-computing service network where developers and autonomous agents can discover quantum workloads, pay seamlessly with Algorand USDC through x402, and trigger real distributed quantum circuit and quantum-finance computations across a libp2p mesh.**

QMeshPy turns distributed quantum computing into **discoverable, programmable, and pay-per-use network services**. The platform combines **FastAPI, Qiskit, py-libp2p, and Algorand x402** so that quantum capabilities can be exposed as services rather than requiring every developer, researcher, or application to operate its own quantum-computing infrastructure.

The Algorand x402 integration adds the missing **machine-to-machine payment layer**: a software client can discover a quantum service, determine the payment requirement, make an on-chain USDC payment, and invoke the computation programmatically.

### Why Algorand x402?

The problem QMeshPy addresses is twofold:

1. **Access to specialized quantum computation is difficult.** Developers, researchers, financial applications, and other software increasingly need specialized quantum workloads without necessarily operating their own quantum infrastructure.
2. **Distributed compute needs native machine payments.** A decentralized compute network needs a way for software clients and autonomous agents to discover a service, understand its price, pay programmatically, and receive the resulting computation without manual payment or account-management workflows.

Algorand x402 provides a natural payment rail for this model. HTTP requests can communicate the payment requirement through the standard `402 Payment Required` flow, while **Algorand USDC provides on-chain settlement** before the corresponding QMeshPy computation proceeds.

### What QMeshPy exposes

For the Algorand x402 integration, QMeshPy currently exposes two paid services:

| Service | Description | Payment flow | Execution |
|---|---|---|---|
| **Quantum Circuit Execution** | Submit quantum circuits for distributed execution | Algorand USDC via x402 | Distributed across the QMeshPy libp2p mesh |
| **QAE Options Pricing** | Run quantum-amplitude-estimation-based options pricing | Algorand USDC via x402 | QMeshPy quantum-finance execution pipeline |

The underlying platform separates circuit, finance, discovery, and enrollment services and connects them to distributed worker peers through py-libp2p.

### How the x402 request flow works

```text
┌───────────────────────┐
│ Developer / Agent     │
│ / Application         │
└──────────┬────────────┘
           │
           │ 1. Request quantum service
           ▼
┌─────────────────────────────────────┐
│ QMeshPy x402 Endpoint               │
│ POST /api/x402/quantum/runs         │
└──────────┬──────────────────────────┘
           │
           │ 2. No payment supplied
           ▼
      HTTP 402 Payment
        Required
           │
           │ 3. Client supplies x402 payment
           ▼
┌─────────────────────────────────────┐
│ GoPlausible x402 Facilitator         │
│ Bazaar discovery + route metadata    │
└──────────┬──────────────────────────┘
           │
           │ 4. Algorand USDC settlement
           ▼
┌─────────────────────────────────────┐
│ Algorand TestNet / MainNet           │
│ On-chain payment settlement          │
└──────────┬──────────────────────────┘
           │
           │ 5. Payment verified
           ▼
┌─────────────────────────────────────┐
│ QMeshPy Quantum Service              │
│ Circuit execution / QAE pricing      │
└──────────┬──────────────────────────┘
           │
           │ 6. Distributed execution
           ▼
┌─────────────────────────────────────┐
│ py-libp2p Worker Mesh                │
│ GossipSub + libp2p streams           │
└──────────┬──────────────────────────┘
           │
           │ 7. Result returned
           ▼
┌───────────────────────┐
│ Developer / Agent     │
│ receives computation  │
└───────────────────────┘
```

This creates a complete **request → payment → settlement → computation → result** lifecycle where payment is handled programmatically rather than through a manual checkout workflow.

### x402 integration details

The QMeshPy Algorand integration has the following characteristics:

- **Two paid endpoints:** quantum circuit execution and QAE options pricing.
- **GoPlausible facilitator:** both routes use the GoPlausible x402 facilitator.
- **Bazaar discovery:** x402 Bazaar discovery is enabled for the routes.
- **Global challenge metadata:** the `x402-global-challenge` tag is set in the route metadata.
- **HTTP 402 flow:** unpaid requests return a proper `402 Payment Required` response with the payment requirement.
- **Real Algorand USDC:** paid TestNet requests use real Algorand USDC rather than a mocked payment implementation.
- **On-chain settlement:** successful payments settle on-chain and increase the service receiver's balance.
- **Computation after payment:** once payment is settled, QMeshPy creates the corresponding quantum job and executes it.
- **Distributed execution:** quantum circuit jobs are dispatched through the QMeshPy py-libp2p mesh.
- **Real result:** the QAE options-pricing endpoint has completed successfully and returned a real computation result.

### Algorand TestNet configuration

The current integration is configured for Algorand TestNet.

The x402 endpoint is:

```text
POST /api/x402/quantum/runs
```

The platform acts as the **seller/service provider**. The seller only needs a public Algorand receiver address; private keys and mnemonics are not required by the QMeshPy repository.

The current TestNet configuration uses:

```dotenv
X402_ENABLED=true
X402_NETWORK=testnet
X402_AVM_ADDRESS=<Algorand receiver address>
X402_FACILITATOR_URL=https://facilitator.goplausible.xyz
X402_QUANTUM_RUN_PRICE=$0.01
```

The QMeshPy TestNet flow uses the Algorand USDC ASA:

```text
10458941
```

A complete setup and verification procedure is available in:

**[docs/algorand-x402-runbook.md](docs/algorand-x402-runbook.md)**

The runbook covers receiver setup, TestNet funding, USDC opt-in, payer setup, environment variables, unpaid 402 verification, paid requests, and the MainNet transition.

---

## ✅ Algorand x402 TestNet Verification

The integration has been tested end-to-end against **Algorand TestNet** using real Algorand USDC.

The verification covered the complete payment and computation lifecycle:

1. Send an unpaid request.
2. Receive the expected HTTP `402 Payment Required`.
3. Provide the required x402 payment.
4. Settle the payment using Algorand USDC.
5. Verify the on-chain transaction.
6. Confirm that the service receiver balance increased.
7. Create the corresponding QMeshPy job.
8. Execute the workload through the QMeshPy execution infrastructure.
9. Return the computation result.

### Verified behavior

**Quantum circuit execution**

The paid circuit endpoint has been exercised against the QMeshPy distributed execution layer. Circuit jobs are routed through the py-libp2p mesh, where worker peers participate in the computation.

Two early test transactions exposed issues in the sample circuit itself rather than the payment flow. After correcting the circuit, the paid request completed successfully.

**QAE options pricing**

The paid options-pricing endpoint completed successfully after Algorand USDC settlement and returned a real computation result.

This is important because the TestNet verification is not only checking that an Algorand transaction exists: it verifies that **payment enables an actual downstream computation**.

### TestNet transaction evidence

#### 1. Quantum circuits — first paid call

The first paid circuit request successfully exercised the payment flow, but the resulting job failed because the submitted sample circuit was invalid.

**Transaction:**  
https://lora.algokit.io/testnet/transaction/XKHMXGIXMN3AWDZHXR2SNMTOLFXC2YUWNVCO5I4DLIWIHAT622RQ

**Result:** Payment flow exercised successfully; computation failed because of the sample circuit.

#### 2. QAE options pricing — successful

The options-pricing request completed successfully and returned a real result after payment settlement.

**Transaction:**  
https://lora.algokit.io/testnet/transaction/CRKLH5GMLK3WESENWBUO22VA7N6WFASUW2C6A5GYHCN7GYDMNVEQ

**Result:** Payment settled and QAE options-pricing job completed successfully.

#### 3. Quantum circuits — second paid call

A second circuit request was submitted after the initial test. The job reached execution but failed on the `measure q -> c` line in the submitted circuit.

**Transaction:**  
https://lora.algokit.io/testnet/transaction/NRWBXMIC6R5HZ6BKBL2C4ATYZC5ADM37SSAPZWIT3MEQ6KI2QIMQ

**Result:** Payment flow exercised successfully; computation failed on the circuit's measurement instruction.

#### 4. Quantum circuits — fixed circuit, successful

The circuit was corrected and submitted again. This time the paid request completed successfully and the job ran through the QMeshPy execution infrastructure.

**Transaction:**  
https://lora.algokit.io/testnet/transaction/M3EJCHKT6BZIDVBVQSVOK3S2AVMW367FKQDNK2LWHT6XBYSOC7IA

**Result:** Payment settled and the distributed quantum circuit job completed successfully.

### Test payer account

The Algorand TestNet payer account used for the paid integration tests is:

https://lora.algokit.io/testnet/account/YFBKZ4PSSKSOJNHUGXOK3GOBO5J7R2GXR57FPQLYKUJOTLIAWB7S7JY724

### What the TestNet results demonstrate

The successful tests demonstrate that QMeshPy can connect the following components into one machine-driven workflow:

```text
HTTP request
    ↓
x402 payment requirement
    ↓
Algorand USDC payment
    ↓
On-chain settlement
    ↓
Payment verification
    ↓
QMeshPy job creation
    ↓
libp2p distributed execution
    ↓
Quantum / quantum-finance result
```

The important distinction is that the Algorand transaction is not an isolated payment demonstration. The payment is directly connected to access to a computational service.

---

## 🔎 Discovery + Payment + Computation

QMeshPy is designed around a broader service-network model.

A future application or autonomous agent should not need to know which machine owns the quantum hardware or simulator. Instead, it should be able to:

1. **Discover** a quantum-capable service.
2. **Inspect** the service capability and payment requirement.
3. **Request** computation.
4. **Receive an HTTP 402** when payment is required.
5. **Pay programmatically** using Algorand USDC through x402.
6. **Wait for settlement and authorization.**
7. **Submit or trigger the quantum workload.**
8. **Receive the resulting computation.**

This makes quantum computation behave more like a programmable network resource.

The role of each layer is deliberately separated:

| Layer | Responsibility |
|---|---|
| **x402** | Standard payment-required interaction between client and service |
| **Algorand** | On-chain USDC payment and settlement |
| **GoPlausible** | x402 payment facilitation |
| **Bazaar** | Service discovery within the x402 ecosystem |
| **FastAPI** | QMeshPy service/API layer |
| **py-libp2p** | Peer discovery, communication, and distributed execution |
| **Qiskit** | Quantum circuit and quantum-finance computation |
| **Worker peers** | Distributed computation providers |

This separation allows QMeshPy to keep its decentralized execution model while adding a standardized economic interface for machine-to-machine computation.

---

## 🤖 Machine-to-Machine Quantum Services

One of the longer-term goals of QMeshPy is to make specialized computation accessible to **software rather than only human operators**.

For example, an autonomous financial agent could discover a QAE options-pricing service, determine that the service costs a specified amount of USDC, make the required Algorand payment through x402, and receive the resulting computation.

Likewise, a quantum application could discover a circuit-execution service, pay for execution, and submit a workload without manually managing a quantum-computing backend.

This creates a model where:

```text
Autonomous Agent
      │
      ├── Discover service
      │
      ├── Determine price
      │
      ├── Pay with Algorand USDC
      │
      ├── Invoke computation
      │
      └── Consume result
             │
             ▼
       QMeshPy Service
             │
             ▼
       libp2p Worker Mesh
```

Algorand x402 therefore provides an important economic primitive for QMeshPy: **machine-payable access to distributed computation**.

---

## 🌐 Vision: An Open Marketplace for Quantum Services

The long-term vision is an open network where independent compute providers can contribute quantum-capable worker nodes and applications can dynamically discover and pay for specialized quantum capabilities.

QMeshPy's architecture already moves in this direction through:

- distributed worker discovery;
- capability advertisements;
- peer-to-peer communication;
- distributed circuit execution;
- quantum-finance services;
- service-oriented APIs;
- and a roadmap toward an open node network and autonomous workloads.

The existing roadmap includes:

| Milestone | Theme |
|---|---|
| **M1** | Production SDK & Platform |
| **M2** | Bring Your Own Node Network |
| **M3** | Autonomous Research & Drug Discovery Platform |
| **M4** | Torrent-Native Service Network |
| **M5** | Hydra Self-Healing Network |

Within this architecture, **Algorand x402 provides the economic layer** that allows computational services to be consumed programmatically.

The goal is not simply to attach payments to a quantum API. The goal is to combine:

**discovery + capability + payment + distributed execution + results**

into a composable network primitive for quantum computing.

---

## 🏗️ Platform Architecture

QMeshPy combines a service/API layer with a decentralized execution layer:

```text
                         ┌───────────────────────────────┐
                         │ Developer / AI Agent / App    │
                         └───────────────┬───────────────┘
                                         │
                              x402 payment request
                                         │
                                         ▼
                         ┌───────────────────────────────┐
                         │       QMeshPy API Layer       │
                         │                               │
                         │  Circuit Execution            │
                         │  QAE Options Pricing          │
                         │  Discovery / Enrollment       │
                         └───────────────┬───────────────┘
                                         │
                              payment verified
                                         │
                         ┌───────────────▼───────────────┐
                         │      FastAPI Coordinator       │
                         │                               │
                         │  Circuit Jobs │ Finance       │
                         └───────────────┬───────────────┘
                                         │
                              py-libp2p / GossipSub
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
             ┌────────────┐      ┌────────────┐      ┌────────────┐
             │ Worker     │      │ Worker     │      │ Worker     │
             │ Peer       │      │ Peer       │      │ Peer       │
             └────────────┘      └────────────┘      └────────────┘
                    │                    │                    │
                    └────────────────────┼────────────────────┘
                                         │
                                         ▼
                              Quantum computation
                                         │
                                         ▼
                                  Result / Job
```

Algorand x402 is intentionally positioned at the service boundary. The payment layer does not replace the decentralized networking layer; it authorizes access to services that are then executed across the QMeshPy peer-to-peer infrastructure.

---

## 🔗 Algorand x402 Resources

- **QMeshPy Algorand x402 implementation:**  
  https://github.com/QMeshPy/distributed-quantum/tree/feat/algorand-x402

- **Algorand TestNet transaction — successful QAE options pricing:**  
  https://lora.algokit.io/testnet/transaction/CRKLH5GMLK3WESENWBUO22VA7N6WFASUW2C6A5GYHCN7GYDMNVEQ

- **Algorand TestNet transaction — successful fixed circuit:**  
  https://lora.algokit.io/testnet/transaction/M3EJCHKT6BZIDVBVQSVOK3S2AVMW367FKQDNK2LWHT6XBYSOC7IA

- **Algorand TestNet payer account:**  
  https://lora.algokit.io/testnet/account/YFBKZ4PSSKSOJNHUGXOK3GOBO5J7R2GXR57FPQLYKUJOTLIAWB7S7JY724

- **Complete x402 TestNet runbook:**  
  [docs/algorand-x402-runbook.md](docs/algorand-x402-runbook.md)

---

## Toju agent storage — testnet integration

Agents can draft a report in chat and propose storing it on public IPFS through
the **full Toju server**. Ask naturally: **“Let's store this proposal so we can
access it later.”** The agent prepares an immutable approval card; only the
signed-in owner can approve publication and its capped testnet payment.

The card stays beside its original response. Later messages continue below it,
and saved conversations survive reloads. Use **Agents → Agent Chat** in the
navigation bar to try the flow.

### Links and deployment boundaries

| Resource | Location |
| --- | --- |
| Integration branch | `feat/toju-agent-storage` in both [QMeshPy](https://github.com/QMeshPy/distributed-quantum/tree/feat/toju-agent-storage) and [Winter-Soren](https://github.com/Winter-Soren/distributed-quantum-services/tree/feat/toju-agent-storage) |
| Toju API readiness | [Render health](https://toju-devcon-testnet.onrender.com/health) |
| Toju API liveness | [Render liveness](https://toju-devcon-testnet.onrender.com/health/live) |
| Full Toju server source | [Winter-Soren/afara, devcon/testnet](https://github.com/Winter-Soren/afara/tree/devcon/testnet), forked from the official Toju server |
| Hosting instructions | [Full Render / Neon / QStash guide](docs/toju-render-testnet-guide.md) |
| Video demo | [Watch the Toju agent storage demo on Google Drive](https://drive.google.com/file/d/1PZ6MHxBd5_XOqMTGnrS6OEB_tGlL6uGX/view?usp=drive_link) |

**QuantumNodes runs locally for this demo. Render hosts the separate full Toju
Node/Express server**, including its storage, payment, database and lifecycle-job
routes. `backend/toju-client` is a payment/verification worker, not a replacement
storage server. The retired `services/toju-demo` prototype must not be deployed.

Agent storage payments use **Base Sepolia** (`eip155:84532`) and faucet USDC.
The server's separate Solana route uses **Solana testnet**, with program
`CSXnfQsFWxdPB5pnS73TQDA6ivK6kcFnRwtt6TgFquxH`. This agent demo does not execute
a Solana payment. Neither route automatically falls back to mainnet.

### Run the integration locally

Use Python 3.12 (the tested runtime), `uv`, **Node 22**, Bun, and a running local
MongoDB. Start with the backend/frontend setup below. The frontend uses Bun;
the isolated payment worker has its own npm lockfile.

```sh
# From the repository root
cd backend
uv sync --extra dev
cd toju-client
npm ci
cd ../../frontend
bun install
```

Create ignored `backend/.env` and `frontend/.env.local` files from their example
settings. Merge the values below into your local files; do not overwrite existing
credentials. Generate **one** bridge secret with `openssl rand -hex 32` and use
that same value on both sides. Generate a separate Better Auth secret.

Backend configuration (`backend/.env`):

```dotenv
QB2_MONGODB_TARGET=local
QB2_MONGODB_LOCAL_URI=mongodb://127.0.0.1:27017
QB2_MONGODB_DATABASE=qds
AGENT_AUTH_BRIDGE_SECRET=<same-generated-bridge-secret-as-frontend>

AGENT_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<your-own-openrouter-key>
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free

CDP_API_KEY_ID=<your-own-cdp-key-id>
CDP_API_KEY_SECRET=<your-own-cdp-key-secret>
CDP_WALLET_SECRET=<your-own-cdp-wallet-secret>
NETWORK=base-sepolia

TOJU_API_URL=https://toju-devcon-testnet.onrender.com
TOJU_PAYMENT_RECIPIENT=0xbB2Fc1cc295b53a75217319eA421256dABB3eacb
TOJU_NODE_BINARY=node
```

`TOJU_NODE_BINARY` must resolve to Node 22; use its absolute path if your shell's
default differs. The current agent services use `QB2_MONGODB_LOCAL_URI` directly;
set that URI explicitly even if connecting to a remote MongoDB installation.

For Groq instead, set `AGENT_LLM_PROVIDER=groq`, `GROQ_API_KEY`, and
`GROQ_MODEL=openai/gpt-oss-20b`. OpenRouter accepts only free model names and sends
zero-price provider limits. Provider switching is manual; there is no paid
fallback or automatic rate-limit retry. Free model availability can change.

Frontend configuration (`frontend/.env.local`):

```dotenv
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8081
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DB_NAME=quantum_platform
BETTER_AUTH_URL=http://localhost:3000
BETTER_AUTH_SECRET=<separate-generated-auth-secret>
AGENT_AUTH_BRIDGE_SECRET=<same-generated-bridge-secret-as-backend>
RESEND_API_KEY=<your-own-resend-key>
OTP_EMAIL_FROM=<sender-verified-in-your-resend-account>
NEXT_PUBLIC_TRIAL_DISABLED=true
```

The trial flag is for local development; it does **not** bypass sign-in or export
ownership checks. Email OTP authentication requires a working Resend sender.
MongoDB stores chat/agent state and authentication; **Neon belongs to the Toju
server**, not these MongoDB settings. Provider keys, the auth bridge and CDP
signing credentials are server-only; never prefix them with `NEXT_PUBLIC_`.

Start the two processes in separate terminals:

```sh
cd backend
uv run quantum-backend --host 127.0.0.1 --port 8081
```

```sh
cd frontend
bun run dev
```

Sign in at [localhost:3000](http://localhost:3000), open **Agents → Agent Chat**,
and use your own agent and its CDP Base Sepolia wallet. Fund that wallet with
test USDC using the [Circle faucet](https://faucet.circle.com/) before approving
an export. Do not use mainnet funds or another user's wallet.

### Try a draft, approval and receipt

1. Ask: `Draft a short Bell-pair experiment proposal. Clearly label it as a proposed experiment that has not been run. Show only the draft for now.`
2. Then ask: `Let's store this proposal so we can access it later.`
3. Review the exact content, public-IPFS notice, recipient, SHA-256, 30-day
   retention and price. Click **Cancel** to decline or **Approve & store** once
   to publish. A direct `yes` applies only to the current pending approval.
4. Wait for **Stored and retrieved. SHA-256 verified.** Open the artifact and
   testnet payment links. The worker checks the on-chain USDC Transfer and the
   downloaded bytes; an upload response alone is not treated as proof.
5. Reload the saved chat to see the persisted receipt. For an uncertain outcome,
   use **Check receipt (no new payment)**; never repay automatically.

The model can also propose exporting an owned workflow run ID. The backend reads
that user's stored run snapshots and exports selected metadata/results rather
than trusting model-invented results. Exports are limited to 256 KiB, approval
expires after 15 minutes, and the current payment policy caps each export at
24 micro-USDC (`0.000024` test USDC). Changing server pricing requires reviewing
the client's matching policy; mismatched quotes fail closed.

### Host your own full Toju server on Render

Follow the [complete hosting guide](docs/toju-render-testnet-guide.md), which
includes every environment variable, pricing initialization, migrations and
signed QStash schedule. The reproduced installation uses Render Free, Neon Free
and QStash Free; check your account's quotas before inviting additional users.

- Deploy the **afara server fork**, branch `devcon/testnet`, with Render's
  root directory blank. Do not deploy this entire QuantumNodes repository as Toju.
- Use Node 22, `NODE_ENV=staging`, `X402_NETWORK=sepolia`,
  `FILECOIN_NETWORK=calibration`, and a Solana testnet RPC/IDL.
- Provide your own Neon `DATABASE_URL`, Pinata JWT/gateway, Resend sender/key,
  QStash current/next signing keys, admin API secret and Base Sepolia recipient.
  Keep all secrets in Render's environment settings.
- Build: `corepack pnpm --filter server... install --frozen-lockfile --prod=false && corepack pnpm --dir server run build`
- Start: `corepack pnpm --dir server exec tsx scripts/migrate.ts staging && node server/dist/index.js`
- Set Render's health-check path to `/health/live`. Check `/health` separately
  for database readiness and initialize pricing as documented in the guide.
- Configure the five signed lifecycle/usage jobs described in the guide.
  Do not schedule `/jobs/destroy`.
- Point your QuantumNodes backend's `TOJU_API_URL` at your new service and set
  `TOJU_PAYMENT_RECIPIENT` to its exact `BASE_USDC_WALLET` public address.

The demo endpoint above is a shared test service, not a production availability
guarantee. Its hosted `/health` returning healthy does not by itself verify
payment settlement, IPFS retrieval or lifecycle cleanup.

### Verification and known limits

The earlier **DevCon Demo** draft completed a testnet payment and verified
retrieval: [public report](https://gateway.pinata.cloud/ipfs/bafybeiaw3wgnhn5yort3hvvzohvyd6ms43xmjat4qhj4jaazr3e2rnuvie/report.md)
and [Base Sepolia transaction](https://sepolia.basescan.org/tx/0x4b9e24bb741676455f1b5aa611d7459bd2b6fbf8666bf8353a2eca84602fa1fe).
A later approved draft was pinned but settlement failed; its uncertain receipt
is preserved. The exact historical settlement failure was not captured.

Run the focused checks without consuming model quota or making payments:

```sh
cd backend
uv run pytest tests/services/test_agent_bridge.py tests/services/test_groq_agent.py tests/services/test_toju_storage.py
cd toju-client
npm test
cd ../../frontend
bun run tsc --noEmit
```

The storage test uses a temporary local MongoDB database and removes only that
test database. The provider/payment calls in these checks are mocked. Live
coverage includes one completed export, receipt recovery and a signed QStash
usage snapshot. A full quantum experiment, Solana/Filecoin payments, renewal
email flow and time-based deletion have not been verified end to end. Public
IPFS copies may remain after pin retention ends. Free-tier cold starts, quotas
and external settlement failures remain demo limitations.

---

## Quick start

**Prerequisites:** Python 3.11+ with [uv](https://github.com/astral-sh/uv), Node.js 22 (Bun for the frontend, npm for the isolated Toju payment worker), and Docker (full stack only).

**Backend** (http://localhost:8081, Swagger at `/docs`):

```bash
cd backend
make install
make run          # or `make run-clean` to reset runtime state
```

**Frontend** (http://localhost:3000):

```bash
cd frontend
bun install
bun run dev      # Next.js on http://localhost:3000
```

Create `frontend/.env.local` first:

```dotenv
NEXT_PUBLIC_BACKEND_URL=http://localhost:8081
NEXT_PUBLIC_TRIAL_DISABLED=true
```

### Configure Algorand x402 (TestNet)

The x402 endpoint is `POST /api/x402/quantum/runs`. The platform is the
seller: it needs only a public Algorand receiver address. Never place a
mnemonic or private key in this repository.

1. Create a dedicated Algorand TestNet receiver in Pera, Defly, Lute, or an
   approved custody system.
2. Fund it with TestNet ALGO at
   [Lora](https://lora.algokit.io/testnet/fund), then opt it into TestNet USDC
   ASA `10458941`. The account needs at least 0.2 ALGO for its base and
   asset-opt-in minimum balances, plus transaction fees.
3. Optional for receiver testing: request TestNet USDC from the
   [Circle faucet](https://faucet.circle.com/). A paid test also needs a
   separate payer account with ALGO, the same USDC opt-in, and TestNet USDC.
4. Generate one gateway secret with `openssl rand -hex 32`. Set the same
   value as `QB2_X402_GATEWAY_SECRET` in `.env` and `backend/.env`, and as
   `X402_GATEWAY_SECRET` in `frontend/.env`.
5. Set `X402_AVM_ADDRESS` in `frontend/.env` to the receiver's public
   address, then change `X402_ENABLED=true`.

`frontend/.env` should contain:

```dotenv
NEXT_PUBLIC_BACKEND_URL=http://localhost:8081
X402_ENABLED=true
X402_NETWORK=testnet
X402_AVM_ADDRESS=<58-character Algorand receiver address>
X402_FACILITATOR_URL=https://facilitator.goplausible.xyz
X402_QUANTUM_RUN_PRICE=$0.01
X402_GATEWAY_SECRET=<same 64-character secret>
```

The hosted facilitator and default AlgoNode endpoints require no API key.
MetaMask is not compatible with Algorand AVM payments. AWS Bedrock and
Coinbase CDP keys configure the existing agent features, not this x402 route.
See [the complete TestNet runbook](docs/algorand-x402-runbook.md) for unpaid
and paid verification commands and the MainNet switch.

If `next dev` reports `EMFILE` on macOS, use the production server for the
local check:

```bash
cd frontend
bun run build
bun run start
```

### Full Stack with Docker
**Full stack with Docker:**

```bash
cp .env.example .env     # add your Neon Postgres and Atlas MongoDB credentials
docker compose up --build
```

---

## Platform content node (Kubo)

The Compose stack includes **Kubo v0.43.1**, pinned by release tag and multi-platform
image digest. With current Docker Engine/Compose, start only the content node:

```bash
docker compose up -d --wait kubo
docker compose exec kubo ipfs --api=/ip4/127.0.0.1/tcp/5001 diag healthy
docker compose stop kubo
```

No provider credentials or backend startup are required. Compose may warn about
unset variables for the existing backend, even when starting only Kubo. If port
8080 is in use, run `KUBO_GATEWAY_PORT=18080 docker compose up -d --wait kubo`
(or set that variable in `.env`). The gateway remains loopback-only.

| Interface | Exposure |
|---|---|
| Swarm `4001/tcp` and `4001/udp` | Published for IPFS peers, separate from quantum-worker libp2p |
| Gateway `8080/tcp` | `127.0.0.1:8080` only; read content at `/ipfs/<CID>` |
| Admin RPC `5001/tcp` | **Not published** or proxied by Caddy; trusted Compose containers use `http://kubo:5001` |

The named `kubo_data` volume persists `/data/ipfs` across container recreation.
Stopping/removing a container does not remove it. Volume deletion permanently
removes this node's data and identity; do not use `docker compose down --volumes`
on a deployment unless you intend to delete **all** that project's named volumes.
The backend has no Kubo health dependency: content failures must not block compute.

`IPFS_PROFILE=server` applies **only when a new repository is initialized**. It
turns off mDNS and NAT port mapping and filters private swarm addresses. The
image sets `Addresses.API=/ip4/0.0.0.0/tcp/5001` and
`Addresses.Gateway=/ip4/0.0.0.0/tcp/8080` **inside the container**. Host exposure is
controlled by the mappings above. Existing repositories are not reconfigured;
back up the volume and review migrations/configuration before changing versions.
See the pinned [release](https://github.com/ipfs/kubo/releases/tag/v0.43.1),
[profile/configuration reference](https://github.com/ipfs/kubo/blob/v0.43.1/docs/config.md#server-profile),
[image entrypoint](https://github.com/ipfs/kubo/blob/v0.43.1/bin/container_daemon),
and [healthcheck](https://github.com/ipfs/kubo/blob/v0.43.1/Dockerfile).

Checks require Python 3.10+ (via uv) and Docker Compose with `up --wait` support:

```bash
uv run --no-project python -m unittest discover -s scripts -p test_kubo_compose.py -v
uv run --no-project python scripts/smoke_kubo.py
```

The first command checks deployment configuration without starting containers.
The optional live smoke test extracts only Kubo into a uniquely named temporary
project, ignores project `.env` values, uses random host ports and runs **offline**.
It checks health/profile, RPC host-binding absence, loopback gateway, matching
add/cat bytes and CIDs, and retained content/pin after container recreation. It
attempts to remove only its own container/network/volume, including on failure.
If cleanup also fails, it reports the disposable project label without replacing
the original error. Command failures identify the operation without dumping
possibly sensitive output. It needs no backend dependencies or private data;
its fixture is harmless public text.

The normal service is **online**: IPFS is public content-addressed networking,
not confidential storage. Never add private data expecting the CID to be secret.
Unpublished RPC is not authentication: containers on `backend_network` and Docker
administrators remain trusted. RPC authorization/hardening (#60), the Python
client (#61), automatic uploads and production hosting are separate work.

## Documentation

Long-form documentation lives in the **[QMeshPy/documentations](https://github.com/QMeshPy/documentations)** repository. Start with its [START_HERE](https://github.com/QMeshPy/documentations/blob/main/START_HERE.md) page.

| I want to... | Read |
|---|---|
| Contribute code | [CONTEXT.md](CONTEXT.md) (in this repo), then [ARCHITECTURE](https://github.com/QMeshPy/documentations/blob/main/ARCHITECTURE.md) |
| Understand the system design | [ARCHITECTURE](https://github.com/QMeshPy/documentations/blob/main/ARCHITECTURE.md), [design](https://github.com/QMeshPy/documentations/blob/main/design.md), [requirements](https://github.com/QMeshPy/documentations/blob/main/requirements.md) |
| Work on the frontend | [frontend/DESIGN.md](frontend/DESIGN.md) (in this repo) |
| Deploy it | [DEPLOYMENT-MANUAL.md](DEPLOYMENT-MANUAL.md) (in this repo), [Lightsail guide](https://github.com/QMeshPy/documentations/blob/main/LIGHTSAIL-DEPLOYMENT.md) |
| Read the research | [Paper draft](https://github.com/QMeshPy/documentations/blob/main/research/RESEARCH_PAPER_DRAFT.md), [math appendix](https://github.com/QMeshPy/documentations/blob/main/research/MATHEMATICAL_APPENDIX.md), [scaling strategy](https://github.com/QMeshPy/documentations/blob/main/research/QUANTUM_SCALING_STRATEGY.md) |
| Reproduce the benchmarks | [Implementation notes](https://github.com/QMeshPy/documentations/blob/main/technical/IMPLEMENTATION_NOTES.md), [benchmark results](https://github.com/QMeshPy/documentations/blob/main/technical/BENCHMARK.md), and the scripts in `backend/scripts/` |
| Understand the finance use case | [Financial modeling foundations](https://github.com/QMeshPy/documentations/blob/main/FINANCIAL_MODELING_FOUNDATIONS.md) |
| See where the project is going | [Future roadmap](https://github.com/QMeshPy/documentations/blob/main/FUTURE_ROADMAP.md) |

---

## Contributing

1. Fork the repo and create a feature branch.
2. Read [CONTEXT.md](CONTEXT.md). The Trio/asyncio bridge and event-sourced persistence have constraints that aren't obvious.
3. Run `make lint && make test` in `backend/` and `npm run build` in `frontend/` before opening a PR.
4. Keep changes surgical: match the existing style and don't refactor adjacent code.
