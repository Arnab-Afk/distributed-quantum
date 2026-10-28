# Starknet Session Setup Guide

**Quick-start guide for collaborators to test agent spending policies on Starknet Sepolia.**

This guide walks you through creating a Starknet session for an agent, registering it on-chain via Ready wallet, and testing a spend—all without hitting common errors.

---

## What This Does

Agent budget caps (`max_per_proposal`, `daily_budget`) are enforced **on-chain** via a Cairo smart contract. Even if the backend is compromised, the session key cannot spend beyond these limits. The policy contract checks:

- **Per-call limit** — single spend cannot exceed `max_per_call`
- **Daily limit** — 24-hour rolling total cannot exceed `daily_limit`
- **Expiry** — session expires at `expires_at` timestamp
- **Revocation** — owner can invalidate session anytime

---

## Prerequisites

### Tools
- **Ready wallet** (Argent) — install on mobile, funded with Sepolia STRK
- **curl** + **python3** — for backend API calls
- **Backend running** — `uv run quantum-backend --host 127.0.0.1 --port 8081`

### Deployed Contracts (Starknet Sepolia)

| Component | Address | Link |
|-----------|---------|------|
| **Policy Contract** | `0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4` | [Voyager](https://sepolia.voyager.online/contract/0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4) |
| **Ready Owner** | `0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc` | Klein on Sepolia |
| **STRK Token** | `0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d` | [Docs](https://docs.starknet.io/resources/chain-info/) |

### Backend Environment

Required in `backend/.env`:

```bash
# Agent auth (must match frontend)
AGENT_AUTH_BRIDGE_SECRET=your-secret-here

# Session key encryption
WALLET_ENCRYPTION_KEY=your-32-byte-hex-key

# Starknet RPC (publicnode or Cartridge /rpc/v0_10, NOT default Blast)
QB2_STARKNET_SEPOLIA_RPC_URL=https://starknet-sepolia-rpc.publicnode.com

# Optional: AVNU paymaster for gasless registration - https://portal.avnu.fi
AVNU_PAYMASTER_API_KEY=your-avnu-key
```

**RPC is critical:** Default Blast endpoint is dead. Use publicnode or `https://api.cartridge.gg/x/starknet/sepolia/rpc/v0_10`.

### STRK Funding

1. **Ready owner wallet** needs STRK for gas (register + revoke transactions)
2. **Policy contract** needs STRK for spend transfers (contract sends to recipient)

Get testnet STRK: [starknet-faucet](https://www.diadata.org/map/web3-builder-hub/starknet-faucets/)

---

## Step-by-Step Setup

### Step 1: Start Backend

```bash
cd /path/to/distributed-quantum/backend
uv run quantum-backend --host 127.0.0.1 --port 8081
```

Look for `Application startup complete` with no 500 errors. If you see `AttributeError: ... from_random`, your `starknet.py` is outdated—must be **≥0.30** (`KeyPair.generate()`).

---

### Step 2: Mint Bridge Token

The backend requires a `qn1.` signed token (not Better Auth cookies). **Mint fresh every ~60s:**

```bash
cd /path/to/distributed-quantum/backend

TOKEN=$(uv run python - <<'PY'
import base64, hashlib, hmac, json, os, time
from pathlib import Path

for line in Path(".env").read_text().splitlines():
    if line.startswith("AGENT_AUTH_BRIDGE_SECRET="):
        secret = line.split("=", 1)[1].strip().strip('"')
        break
else:
    raise SystemExit("AGENT_AUTH_BRIDGE_SECRET missing in backend/.env")

now = int(time.time())
payload = {
    "sub": "6ae21555e24ff257f6b952b9",  # Must match agent owner_id
    "email": "you@example.com",
    "iat": now,
    "exp": now + 60,
    "aud": "quantumnodes-agentkit",
}
body = base64.urlsafe_b64encode(
    json.dumps(payload, separators=(",", ":")).encode()
).rstrip(b"=").decode()
sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
print(f"qn1.{body}.{sig}")
PY
)

echo "Token expires in 60s. Use: ${TOKEN}"
```

**What this does:** Creates a short-lived JWT that identifies you as the agent owner. The `sub` field (`6ae21555e24ff257f6b952b9`) must match the agent's `owner_id` in MongoDB.

---

### Step 3: Get Your Agent ID

List your agents:

```bash
curl -s http://127.0.0.1:8081/api/v1/agents \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool
```

Example agent: **Research Assistant**  
Agent ID: `6b350343-a41f-41a0-a6b7-9e87f2b0503e`

Copy the `agent_id` you want to use. Check its `config.max_per_proposal` and `config.daily_budget`—these become your on-chain caps.

---

### Step 4: Open Starknet Session

**POST to create session:**

```bash
AGENT_ID="6b350343-a41f-41a0-a6b7-9e87f2b0503e"

curl -s -X POST "http://127.0.0.1:8081/api/v1/agents/${AGENT_ID}/starknet-session" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc",
    "token": "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
    "recipient": "0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc",
    "expires_at": 1795794084,
    "decimals": 18
  }' | python3 -m json.tool
```

**Field meanings:**

| Field | Value | Meaning |
|-------|-------|---------|
| `owner` | Your Ready address | Only this wallet can call `register_session` and `revoke_session` |
| `token` | STRK contract | Token the policy will transfer (18 decimals) |
| `recipient` | Recipient address | Where `spend` sends tokens (can be same as owner) |
| `expires_at` | Unix timestamp | Session expires after this (e.g. `date -j -f "%Y-%m-%d %H:%M:%S" "2026-10-30 00:00:00" +%s`) |
| `decimals` | `18` | STRK has 18 decimals; caps are scaled accordingly |

**Expected response (HTTP 201):**

```json
{
  "starknet_session": {
    "status": "active",
    "owner": "0x026a...",
    "token": "0x0471...",
    "recipient": "0x026a...",
    "max_per_call": "50000000000000000000",
    "daily_limit": "200000000000000000000",
    "expires_at": 1795794084,
    "session_public_key": "0x3f78b65a557dcc7bbfb21dc31b16e6ee3c340e2347517335a57f07215542894"
  },
  "register_session": {
    "contract": "0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4",
    "entrypoint": "register_session",
    "calldata": [
      "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
      "0x026a705ae4db69a318e5b6ce945a7c47776da45f5f281ab0e0a43a13d91ff0fc",
      "50000000000000000000",
      "200000000000000000000",
      "1795794084",
      "0x3f78b65a557dcc7bbfb21dc31b16e6ee3c340e2347517335a57f07215542894"
    ]
  },
  "paymaster": { ... }
}
```

**Save this entire response!** You'll need the `calldata` array for Step 5.

**Example caps for agent with max_per_proposal=50 STRK, daily_budget=200 STRK:**
- `max_per_call`: `50000000000000000000` (50 × 10¹⁸)
- `daily_limit`: `200000000000000000000` (200 × 10¹⁸)

**Common errors:**

| Error | Cause | Fix |
|-------|-------|-----|
| **403 Forbidden** | Wrong auth or `sub` ≠ agent owner | Re-mint token with correct `sub` |
| **500 Internal** | `WALLET_ENCRYPTION_KEY` missing or old starknet.py | Check env, `uv add starknet.py@latest` |
| **503 Service Unavailable** | Backend can't reach Starknet RPC | Set `QB2_STARKNET_SEPOLIA_RPC_URL` |

---

### Step 5: Register Session On-Chain (Voyager + Ready)

**Important:** `register_session` must be signed by your **Ready owner** (`0x026a705…`). The backend session key is only written on-chain in this call—it does **not** sign `register_session`. Use the **exact calldata** from your 201 response; opening a new session mints a new `session_public_key` and invalidates old calldata.

#### Method A: Voyager Web Interface (Recommended)

1. **Open contract on Voyager:**  
   [Policy Contract](https://sepolia.voyager.online/contract/0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4)

2. **Navigate to Write Contract → `register_session`**

3. **Fill in the six fields** from your API response `calldata` array:

   | Field | Example Value | From API |
   |-------|---------------|----------|
   | **token** | `0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d` | `calldata[0]` |
   | **recipient** | `0x026a705ae4db69a318e5b6ce945a7c47776da45f5f281ab0e0a43a13d91ff0fc` | `calldata[1]` |
   | **max_per_call** | `50000000000000000000` | `calldata[2]` |
   | **daily_limit** | `200000000000000000000` | `calldata[3]` |
   | **expires_at** | `1795794084` | `calldata[4]` |
   | **session_public_key** | `0x3f78b65a557dcc7bbfb21dc31b16e6ee3c340e2347517335a57f07215542894` | `calldata[5]` |

4. **Connect Wallet:**  
   - Desktop browser: use **WalletConnect** to connect Ready on your phone
   - Mobile browser: Ready should connect directly
   - **Must be the same address as `owner`** (`0x026a…F0fc` / Klein on Sepolia)

5. **Execute:**  
   - Click **Execute** button
   - Approve transaction in Ready app
   - Wait for confirmation (usually <1 minute)

6. **Verify Success:**  
   - Voyager shows tx as **Succeeded** in recent transactions
   - Contract state: `revoked = false`

**Troubleshooting:**

- **"ABI not verified"** — Normal; the form still works
- **Calldata format issues** — Switch to **Raw Calldata** mode and paste the six values line-by-line
- **Transaction reverts with "owner"** — Wrong wallet connected; must be the exact owner from constructor
- **Transaction reverts with "expired"** — `expires_at` is in the past; create new session with future timestamp
- **Transaction reverts with "per_call"** — `max_per_call` > `daily_limit` or ≤0; check your agent config

#### Method B: starkli CLI (Alternative)

```bash
export STARKNET_KEYSTORE=~/.starkli/sepolia/keystore.json
export STARKNET_ACCOUNT=~/.starkli/sepolia/account.json
export STARKNET_RPC=https://starknet-sepolia-rpc.publicnode.com

starkli invoke \
  0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4 \
  register_session \
  0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d \
  0x026a705ae4db69a318e5b6ce945a7c47776da45f5f281ab0e0a43a13d91ff0fc \
  u256:50000000000000000000 \
  u256:200000000000000000000 \
  1795794084 \
  0x3f78b65a557dcc7bbfb21dc31b16e6ee3c340e2347517335a57f07215542894
```

**Paymaster (Optional):**  
AVNU can sponsor `register_session` to make it gasless. If your 201 response included a `paymaster` object, submit that JSON to [AVNU Sepolia Paymaster](https://sepolia.paymaster.avnu.fi/). Otherwise, Ready pays the gas (~fraction of STRK).

---

### Step 6: Fund Policy Contract

`spend` pulls STRK **from the policy contract's balance**, not from your wallet.

#### Via Ready App:

1. Open Ready wallet (Klein account)
2. Tap **Send**
3. **To:** `0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4`  
   (Policy contract address, **not** OZ deployer)
4. **Asset:** STRK (Sepolia)
5. **Amount:** e.g. **5–10 STRK** (enough for multiple test spends)
6. **Send** → confirm transaction

7. **Verify on Voyager:**  
   [Check contract balance](https://sepolia.voyager.online/contract/0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4)  
   Should show STRK balance and incoming transfer tx

**You can register before or after funding—both orders work. You need both before `spend` succeeds.**

---

### Step 7: Test Spend

#### Backend Preflight (Off-Chain Validation)

Test the policy logic without broadcasting:

```bash
curl -s -X POST "http://127.0.0.1:8081/api/v1/agents/${AGENT_ID}/starknet-session/spend" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"amount": "1"}' | python3 -m json.tool
```

**Response (HTTP 200):**

```json
{
  "spend": {
    "contract": "0x04f1882a...",
    "entrypoint": "spend",
    "calldata": ["1000000000000000000"]
  },
  "policy_snapshot": {
    "spent_today": 0,
    "remaining_today": "200000000000000000000"
  }
}
```

The `calldata` shows amount in wei (1 STRK = `1000000000000000000`).

**Test rejection:**

```bash
# Try to spend 100 STRK (exceeds max_per_call of 50)
curl -s -X POST "http://127.0.0.1:8081/api/v1/agents/${AGENT_ID}/starknet-session/spend" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"amount": "100"}' | python3 -m json.tool
```

Should return **400 Bad Request** with `"per_call"` error.

#### On-Chain Spend (Voyager)

**Current limitation:** The Cairo contract checks `caller == owner` for `spend`, so you sign with Ready (not the session key yet).

1. **Open contract on Voyager** → **Write Contract** → **spend**
2. **Connect Ready wallet** (owner)
3. **amount:** `1000000000000000000` (1 STRK in wei)
4. **Execute** → approve in Ready
5. **Verify:**
   - Transaction succeeds
   - Recipient balance increases by 1 STRK
   - Contract balance decreases by 1 STRK

**Test on-chain rejection:**

Try spending `51000000000000000000` (51 STRK, exceeds `max_per_call`). Transaction should **revert** with `per_call` error.

---

### Step 8: Revoke Session (Optional)

To invalidate the session immediately:

```bash
curl -s -X POST "http://127.0.0.1:8081/api/v1/agents/${AGENT_ID}/starknet-session/revoke" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool
```

**Response:**

```json
{
  "revoke_session": {
    "contract": "0x04f1882a...",
    "entrypoint": "revoke_session",
    "calldata": []
  }
}
```

**On-chain:**

1. Voyager → Write Contract → **revoke_session**
2. Connect Ready (owner)
3. Execute (no parameters)
4. After confirmation, all future `spend` calls revert with `"revoked"`

---

## Quick Checklist

| Step | Status | Verification |
|------|--------|--------------|
| Backend running | ✅ | `curl http://127.0.0.1:8081/api/v1/health` returns 200 |
| Bridge token minted | ✅ | `echo ${TOKEN}` shows `qn1.…` |
| Session created (201) | ✅ | Response has `starknet_session` + `register_session.calldata` |
| Registered on-chain | ✅ | Voyager tx **Succeeded** |
| Policy funded | ✅ | Contract shows STRK balance on Voyager |
| Spend preflight passes | ✅ | Backend returns `spend.calldata` |
| On-chain spend works | ✅ | Voyager tx succeeds, recipient balance ↑ |

---

## Common Errors & Fixes

### Backend Issues

| Error | Cause | Fix |
|-------|-------|-----|
| **ModuleNotFoundError: starknet** | starknet.py not installed | `cd backend && uv add starknet.py` |
| **AttributeError: from_random** | Old starknet.py (<0.30) | `uv add starknet.py@latest`, restart backend |
| **WALLET_ENCRYPTION_KEY required** | Missing env var | Add 32-byte hex key to `.env` |
| **503 when creating session** | RPC unreachable | Set `QB2_STARKNET_SEPOLIA_RPC_URL=https://starknet-sepolia-rpc.publicnode.com` |
| **403 Forbidden on session** | Wrong auth token | Re-mint `qn1` token with matching `sub` |

### Contract Issues

| Revert Reason | Cause | Fix |
|---------------|-------|-----|
| **owner** | Wrong wallet signed | Connect Ready owner (`0x026a…F0fc`) |
| **expired** | `expires_at` in past | Create new session with future timestamp |
| **per_call** | Amount > `max_per_call` or caps inverted | Check `max_per_call` ≤ `daily_limit` |
| **daily** | Day total exceeds `daily_limit` | Wait for UTC rollover or increase limit |
| **revoked** | Session was revoked | Create new session |
| **transfer** | Contract has no STRK | Send STRK to policy contract (Step 6) |

### RPC Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `JsonRpcResponse` enum error | Dead Blast RPC | Use publicnode or Cartridge v0_10 |
| `unknown block tag 'pending'` | starkli on non-v0.8 RPC | For starkli account deploy only: `STARKNET_RPC=https://api.cartridge.gg/x/starknet/sepolia/rpc/v0_8` |
| `addDeclareTransaction` not found | Wrong RPC version | sncast needs `/rpc/v0_10`, not bare URL |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Ready Wallet (Owner)                                       │
│  Signs: register_session, revoke_session                    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ On-chain calls
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Policy Contract (Cairo)                      Starknet      │
│  0x04f1882a972a276e27b423cfadd29d24a75e798b…               │
│                                                              │
│  State:                                                      │
│  • max_per_call, daily_limit, expires_at                   │
│  • session_public_key (from backend)                        │
│  • spent_today, day_index, revoked                         │
│                                                              │
│  Functions:                                                  │
│  • register_session(...)  ← owner only                      │
│  • spend(amount)          ← enforces caps                   │
│  • revoke_session()       ← owner only                      │
└─────────────────────────────────────────────────────────────┘
                  │
                  │ Holds STRK, transfers on spend
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Recipient Address                                          │
│  Receives STRK from contract when spend succeeds            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Backend (Python)                                           │
│  • Generates session keypair (stored encrypted)             │
│  • Returns register_session calldata                        │
│  • Validates spend amounts off-chain (preflight)            │
│  • Does NOT sign on-chain transactions                      │
└─────────────────────────────────────────────────────────────┘
```

**Key security properties:**

1. **Session key is write-only** — backend stores private key encrypted; never returns it
2. **Owner controls registration** — backend cannot modify caps or register sessions; only owner wallet can
3. **On-chain enforcement** — spending limits hold even if backend is compromised
4. **Revocation** — owner can invalidate session immediately on-chain

---

## References

### Documentation
- [Starknet Session Keys (Ready)](https://docs.ready.co/aa-use-cases/session-keys/implement-session-keys)
- [Starknet Chain Info](https://docs.starknet.io/resources/chain-info/)
- [Starknet Compatibility Matrix](https://docs.starknet.io/learn/cheatsheets/compatibility)
- [AVNU Paymaster](https://docs.avnu.fi/docs/paymaster/gasfree)
- [Voyager Sepolia Explorer](https://sepolia.voyager.online/)

### Tools
- [Starknet Faucet](https://starknet-faucet.vercel.app/) — Get Sepolia STRK
- [Ready Wallet](https://ready.co/) — Argent account abstraction wallet
- [Scarb](https://docs.swmansion.com/scarb/) — Cairo package manager (contributors only)
- [starkli](https://book.starkli.rs/) — Starknet CLI (contributors only)

### Deployed Components

| Component | Network | Address/Link |
|-----------|---------|--------------|
| Policy Contract | Starknet Sepolia | [0x04f1882a...](https://sepolia.voyager.online/contract/0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4) |
| Contract Class | Starknet Sepolia | [0x00a4e8f1b...](https://sepolia.voyager.online/class/0x00a4e8f1b7461cc30324074ebf7320a07d20456a0f27ad33017f36dcd9565ff1) |
| STRK Token | Starknet Sepolia | `0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d` |
| Ready Owner | Starknet Sepolia | `0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc` |

### Internal Docs
- `REVVING_UP_STARKNET.md` — Full toolchain setup (Scarb, starkli, sncast)
- `FEAT_STARKNET_SPENDING_POLICIES.md` — Feature requirements and acceptance criteria
- `backend/CHAIN_REGISTRY.md` — Chain registry architecture and Starknet integration
- `backend/contracts/starknet/src/spending_policy.cairo` — Smart contract source

---

## For Maintainers: Deploying a New Policy Contract

If you need to deploy a fresh contract (e.g. new testnet, updated Cairo):

### Prerequisites
- **Scarb 2.19.0** (Sierra 1.9.0 for Sepolia compatibility)
- **starknet-foundry** (`sncast` 0.64.1+)
- **starkli 0.4.2** (for OZ account deploy)
- Funded OZ deployer on Sepolia

### Steps

1. **Compile contract:**
   ```bash
   cd backend/contracts/starknet
   asdf set scarb 2.19.0
   scarb clean && scarb build
   
   # Verify Sierra version (must be 0x1 0x9 0x0)
   python3 -c "import json; print(json.load(open('target/dev/spending_policy_SpendingPolicy.contract_class.json'))['sierra_program'][:3])"
   ```

2. **Declare class:**
   ```bash
   sncast --keystore ~/.starkli/sepolia/keystore.json \
     --account ~/.starkli/sepolia/account.json \
     declare --contract-name SpendingPolicy \
     --url https://starknet-sepolia-rpc.publicnode.com
   
   # Save the class hash from output
   CLASS_HASH="0x..."
   ```

3. **Deploy contract:**
   ```bash
   # Replace with your owner address
   OWNER="0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc"
   
   sncast --keystore ~/.starkli/sepolia/keystore.json \
     --account ~/.starkli/sepolia/account.json \
     deploy --class-hash ${CLASS_HASH} \
     --constructor-calldata ${OWNER} \
     --url https://starknet-sepolia-rpc.publicnode.com
   
   # Save the contract address from output
   CONTRACT_ADDRESS="0x..."
   ```

4. **Update docs:**
   - This file (STARKNET_SESSION_GUIDE.md) — all contract address references
   - Backend `.env.example` — add `STARKNET_POLICY_CONTRACT` if needed
   - Frontend constants — if UI references the contract

5. **Test:**
   ```bash
   # Full test suite
   cd backend
   uv run pytest tests/unit/test_starknet_policy.py -v
   ```

---

## Troubleshooting Deep Dive

### Session Creation Returns 500

**Symptoms:**
- POST `/starknet-session` returns HTTP 500
- Backend logs: `AttributeError: type object 'KeyPair' has no attribute 'from_random'`

**Cause:** starknet.py < 0.30 uses deprecated API.

**Fix:**
```bash
cd backend
uv add starknet.py@latest  # Installs ≥0.30
uv run quantum-backend --host 127.0.0.1 --port 8081  # Restart
```

### Register Transaction Reverts with "owner"

**Symptoms:**
- Voyager shows transaction **Reverted**
- Revert reason: `owner`

**Cause:** Wrong wallet signed the transaction. The contract checks `get_caller_address() == self.owner.read()`.

**Fix:**
1. Check contract owner on Voyager:
   ```
   Read Contract → owner → Query
   ```
2. Connect **that exact address** in Ready
3. If owner is wrong, deploy new contract with correct owner

### Spend Fails with "transfer"

**Symptoms:**
- Backend preflight passes (200 OK)
- On-chain `spend` reverts with `transfer`

**Cause:** Contract has insufficient STRK balance.

**Fix:**
1. Check contract balance: [Voyager](https://sepolia.voyager.online/contract/0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4)
2. Send STRK to contract (Step 6)
3. Wait for confirmation (check Recent Transactions)
4. Retry spend

### Daily Limit Exceeded

**Symptoms:**
- Backend returns **400** with `"daily"` error
- Previous spends succeeded today

**Cause:** UTC day total exceeds `daily_limit`.

**Fix (test):**
- Wait until next UTC day (midnight)
- Or: revoke session → create new one with higher `daily_budget`

**Fix (production):**
- Increase agent's `daily_budget` in config
- Create new session (caps map from config)

---

## Next Steps

### Missing Pieces (For Full Production)

1. **Session key signing** — Cairo contract currently checks `caller == owner`; needs session key verification
2. **Frontend UI** — session creation form + status badges + revoke button
3. **Automatic session refresh** — backend auto-renew before expiry
4. **Multi-agent sessions** — one session per agent, stored in agent document
5. **Mainnet deployment** — after thorough audit and testnet burn-in

### Contributing

See `backend/contracts/starknet/README.md` for Cairo development setup.

For questions or issues, check:
- Backend logs: `backend/quantum-backend/logs/`
- Voyager explorer for transaction details
- `REVVING_UP_STARKNET.md` for toolchain troubleshooting

---

**Last Updated:** October 28, 2026  
**Contract Version:** Sierra 1.9.0 (Scarb 2.19.0)  
**Network:** Starknet Sepolia  
**Status:** ✅ Deployed and tested
