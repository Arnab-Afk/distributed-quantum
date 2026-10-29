# Starknet Session Setup Guide

**Quick-start guide for collaborators to test agent spending policies on Starknet Sepolia.**

Create a session for one agent, have the Ready owner register it, and test a spend. The stored session key is not a signer.

---

## What This Does

Agent budget caps (`max_per_proposal`, `daily_budget`) are enforced **on-chain** when the Ready owner calls `spend`. The backend stores a session key encrypted with `WALLET_ENCRYPTION_KEY` and puts the public key in `register_session`. This contract does not check that key.

The Ready owner signs `register_session`, `spend`, and `revoke_session`. The policy contract checks:

- **Owner** — `spend` reverts unless the caller is the owner
- **Per-call limit** — one spend cannot exceed `max_per_call`
- **Daily limit** — the contract’s `spent_today` cannot exceed `daily_limit`
- **Expiry** — session expires at `expires_at`
- **Revocation** — `revoke_session` sets `revoked` on-chain after the owner transaction is accepted

Spend preflight calls the same checks and does **not** write `spent_today`. Repeating preflight does not reduce the budget. The on-chain counter is the one that counts. A confirmed spend receipt does not write `spent_today` in the database either.

Revoke sets `revocation_pending`. It does not set `revoked`. The card says **Revoking** until a receipt check sees execution `SUCCEEDED` and finality `ACCEPTED_ON_L2` or `ACCEPTED_ON_L1`. L2 acceptance is what the UI treats as confirmed. L1 settlement is slower and is not required.

---

## Prerequisites

### Tools
- **Ready wallet** — funded with Sepolia STRK. The app connects it with starknetkit.
- **Backend** — `uv run quantum-backend --host 127.0.0.1 --port 8081` from `distributed-quantum/backend`
- **Frontend** — `pnpm dev` from `distributed-quantum/frontend` (pnpm 11)
- **curl** + **python3** — only if you call the API directly

### Deployed Contracts (Starknet Sepolia)

| Component | Address | Link |
|-----------|---------|------|
| **Policy Contract** | `0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4` | [Voyager](https://sepolia.voyager.online/contract/0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4) |
| **Ready Owner** | `0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc` | Klein on Sepolia |
| **STRK Token** | `0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d` | [Docs](https://docs.starknet.io/resources/chain-info/) |

Returned calls use `STARKNET_POLICY_CONTRACT`. If that variable is unset, open, spend, and revoke return **503**.

### Backend Environment

Required in `backend/.env`:

```bash
AGENT_AUTH_BRIDGE_SECRET=
WALLET_ENCRYPTION_KEY=
QB2_STARKNET_SEPOLIA_RPC_URL=https://starknet-sepolia-rpc.publicnode.com
STARKNET_POLICY_CONTRACT=
AVNU_PAYMASTER_API_KEY=
```

`QB2_STARKNET_SEPOLIA_RPC_URL` must be a live RPC (publicnode or `https://api.cartridge.gg/x/starknet/sepolia/rpc/v0_10`). The registry’s Blast default is dead.

AVNU (`https://sepolia.paymaster.avnu.fi`) may sponsor `register_session` only. The open response includes a `paymaster` JSON body for that call. The app does not submit it. Spend and revoke are paid by Ready. `revoke` returns `paymaster_sponsored: false`.

### STRK Funding

1. **Ready** pays gas for the invokes the app sends (register, spend, revoke).
2. **Policy contract** must hold STRK. `spend` transfers from the contract balance to the recipient.

Get testnet STRK: [starknet-faucet](https://www.diadata.org/map/web3-builder-hub/starknet-faucets/)

---

## In the app

### 1. Open a session

On **Agents**, a card without a session shows **Open Starknet Session**.

| Field | Default |
|-------|---------|
| Max per proposal (STRK) | 50 |
| Daily budget (STRK) | 200 |
| Expires in (days) | 90 |

**Connect Ready Wallet** uses starknetkit. The address is `connectorData.account`. **Open Session** posts that address as `owner`, STRK as `token`, and the same address as `recipient`, with `decimals: 18`. Caps are the dialog strings, not the raw agent config, when you submit the form.

The API returns **201** and stores the session before Ready approves. Canceling the prompt leaves that stored session. Opening again replaces it and mints a new `session_public_key`.

Ready then signs `register_session` with `wallet_addInvokeTransaction`. The app appends the hash as `kind: "register"`.

The card then shows **Starknet Session**:

- **Max / proposal** and **Daily limit** in STRK (`formatStrk` with the session decimals, 18). These are not raw fri.
- Status **Active**, **Revoking**, **Expired**, or **Revoked**.
- **Txn History**, **Test Spend**, and **Revoke** while the status is Active.

A successful open redirects to `/agents/chat?agentId=…`.

### 2. Test spend

**Test Spend** asks for an amount in STRK. The backend preflights caps and returns `spend` calldata (amount as a Cairo `u256`: low felt, then high felt). Ready signs `spend`. The hash is stored as `kind: "spend"` with that amount.

The dialog copy is: preflight checks caps, and the owner signs `spend`.

### 3. Revoke

**Revoke** asks Ready to sign `revoke_session` (empty calldata). The API sets `revocation_pending` before the wallet returns. The card switches to **Revoking** and shows “Revocation is waiting on the Ready transaction.” Test Spend and Revoke hide until the status is Active again.

`revoked` becomes true only after `POST …/starknet-session/txs` sees the revoke receipt `SUCCEEDED` and `ACCEPTED_ON_L2` or `ACCEPTED_ON_L1`. The UI label is then **Revoked**.

### 4. Transaction history

**Txn History** is on the agent card. The chat header shows the same caps, Test Spend, and Revoke, and does not show the history button.

The dialog title is Transaction history. Empty copy is **No records yet.** Otherwise each row is register, spend, or revoke:

| Receipt value | Label |
|---------------|--------|
| `pending` | Pending |
| `not_found` | Submitted |
| `confirmed` | Confirmed |
| `failed` | Failed |

A spend row with an amount reads `Spend {amount} STRK`. The hash is a truncated Voyager link. The other column is the formatted `submitted_at`, or an em dash when that field is missing.

Each submitted hash is appended to `starknet_session.calls`. `POST /api/v1/agents/{id}/starknet-session/txs` refreshes calls that are not confirmed or failed, via `StarknetRpcAdapter.verify_transaction` (`starknet_getTransactionReceipt`). Confirmed and failed stop. A confirmed spend does not write `spent_today`. A confirmed revoke sets `revoked` and clears `revocation_pending`.

A mounted session panel schedules two receipt checks from each open call’s `submitted_at`: about 15 seconds later, then about 60 seconds later. After those two, it does not keep polling. Opening Txn History refreshes once. Confirmed means L2 acceptance (`ACCEPTED_ON_L2` or `ACCEPTED_ON_L1`), not the later Ethereum proof. This is not a 30–45 minute poll.

### 5. Chat stays on the agent

Chat sessions are per agent. `/agents/chat` lists and restores transcripts whose `agentId` matches the agent in the URL. Switching agents drops another agent’s open transcript. A new agent does not show another agent’s messages.

---

## API

The app calls these through Next.js (`/api/agentkit/agents/{id}/starknet-session…`). Direct curl needs a `qn1.` bridge token. Better Auth cookies are not `Authorization: Bearer`. With `QB2_AUTH_REQUIRED=false`, a non-`qn1.` bearer is ignored and you are `dev-local`, which returns **403** unless `sub` is the agent `owner_id`.

Mint a 60s token from `distributed-quantum/backend`. Replace `sub` with the agent owner id from the UI.

```bash
cd /path/to/distributed-quantum/backend

TOKEN=$(uv run python - <<'PY'
import base64, hashlib, hmac, json, time
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
body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
print(f"qn1.{body}.{sig}")
PY
)
```

List agents: `GET /api/v1/agents` with `Authorization: Bearer ${TOKEN}`. Example agent **Research Assistant**: `6b350343-a41f-41a0-a6b7-9e87f2b0503e`.

### Open — `POST /api/v1/agents/{id}/starknet-session` (201)

```bash
curl -s -X POST "http://127.0.0.1:8081/api/v1/agents/${AGENT_ID}/starknet-session" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc",
    "token": "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
    "recipient": "0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc",
    "expires_at": 1795794084,
    "decimals": 18
  }'
```

Omit `max_per_proposal` and `daily_budget` to use the agent config. The app sends both as strings.

`register_session.calldata` is eight felts. The two `0` values below are the high halves of the `u256` caps (50 and 200 STRK at 18 decimals):

```json
[
  "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
  "0x026a705ae4db69a318e5b6ce945a7c47776da45f5f281ab0e0a43a13d91ff0fc",
  "50000000000000000000",
  "0",
  "200000000000000000000",
  "0",
  "1795794084",
  "0x…"
]
```

`register_session.contract` is `STARKNET_POLICY_CONTRACT`. `paymaster` is the AVNU body for this registration only.

| Error | Cause |
|-------|--------|
| **403** | Bearer is not `qn1.` or `sub` is not the agent owner |
| **400** | Expiry is not in the future, caps are inverted, or an address is invalid |
| **500** | starknet.py is missing `KeyPair.generate()` |
| **503** | `WALLET_ENCRYPTION_KEY` or `STARKNET_POLICY_CONTRACT` is unset, or starknet.py is not installed |

### Spend preflight — `POST …/starknet-session/spend` (200)

```bash
curl -s -X POST "http://127.0.0.1:8081/api/v1/agents/${AGENT_ID}/starknet-session/spend" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"amount": "1"}'
```

`amount` is whole token units (`"1"` is 1 STRK when `decimals` is 18). Calldata is `["1000000000000000000", "0"]`. This does not change `spent_today`. An amount over `max_per_call` returns **400** `per_call`. Over the remaining day total returns **400** `daily`.

### Note a hash — `POST …/starknet-session/tx` (200)

```json
{ "kind": "register", "tx_hash": "0x…" }
```

`kind` is `register`, `spend`, or `revoke`. Spend also requires a positive `amount`. The hash is appended to `calls` with `status: "pending"`. Caps and `revoked` stay as they were.

### Refresh receipts — `POST …/starknet-session/txs` (200)

No body. Non-terminal calls are checked. Confirmed and failed are left alone. RPC failure returns **503** `Starknet receipt lookup is unavailable`. That 503 is not the missing-contract 503.

### Revoke — `POST …/starknet-session/revoke` (200)

Returns `revoke_session` with empty calldata and the policy contract. The stored session has `revocation_pending: true` and `status: "revocation_pending"`. `revoked` is still false.

---

## On-chain (Voyager)

Use the calldata from the 201 you just created. A newer open invalidates it.

Do not send `register_session` from the starkli deployer account. That account pays declare and deploy. The policy owner is the Ready address, and any other caller reverts `owner`.

1. [Policy contract](https://sepolia.voyager.online/contract/0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4) → Write → `register_session`.
2. Connect Ready at the `owner` address.
3. Voyager’s form takes the full `u256` (`max_per_call`, `daily_limit` from `starknet_session`). Raw calldata is the eight felts, low then high.
4. For `spend`, the form amount is the full base-unit integer (1 STRK = `1000000000000000000`). Raw calldata is that integer’s low felt, then high felt.
5. `revoke_session` has no arguments.

Fund the **policy contract** with Sepolia STRK before `spend`. Registration and funding can happen in either order. Both have to be done before a transfer succeeds. Confirm the contract balance on Voyager.

Optional: submit the open response’s `paymaster` object to [AVNU Sepolia](https://sepolia.paymaster.avnu.fi/) if you want that **register** sponsored. The app path does not do this.

---

## Quick Checklist

| Step | Verification |
|------|----------------|
| Backend up | `GET /api/v1/health` returns 200 |
| Policy env set | Open does not return 503 |
| Session stored | 201 includes `starknet_session` and eight-felt `register_session.calldata` |
| Ready signed register | Txn History shows the register hash |
| Policy funded | Contract STRK balance on Voyager |
| Preflight | Spend returns calldata; repeating it leaves `spent_today` unchanged |
| Owner spend | Voyager receipt succeeds; recipient balance increases |
| Revoke | Card says Revoking, then Revoked only after a confirmed revoke receipt |

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| **403** | Wrong `qn1` `sub` | Mint again with the agent `owner_id` |
| **500** `from_random` | starknet.py &lt; 0.30 | `uv add starknet.py` in `backend`, restart |
| **503** on open | `WALLET_ENCRYPTION_KEY` or `STARKNET_POLICY_CONTRACT` unset, or starknet.py is not installed | Set both env vars, restart |
| **503** on spend or revoke | `STARKNET_POLICY_CONTRACT` unset | Set the deployed policy address, restart |
| **503** on `…/txs` | Receipt RPC failed | Set `QB2_STARKNET_SEPOLIA_RPC_URL` to publicnode or Cartridge `/rpc/v0_10` |
| Revert **owner** | Signer is not the constructor owner | Sign with Ready `0x026a…F0fc` |
| Revert **expired** | `expires_at` is in the past | Open again with a future expiry |
| Revert **per_call** | Amount or cap is above the per-call max, or caps are inverted | Amount ≤ max/proposal ≤ daily budget |
| Revert **daily** | On-chain day total would pass `daily_limit` | Wait for the next unix day (`timestamp // 86400`) or open a new session |
| Revert **revoked** | Owner revoke is already accepted | Open a new session |
| Revert **transfer** | Contract STRK balance is too low | Send STRK to the policy contract |
| `unknown block tag 'pending'` | starkli on a non-v0.8 RPC | Account deploy only: Cartridge `/rpc/v0_8`. See `REVVING_UP_STARKNET.md` |

---

## Who signs what

```
Ready owner
  register_session, spend, revoke_session
  (starknetkit → wallet_addInvokeTransaction)
        │
        ▼
Policy contract  0x04f1882a…aaa4
  caps, expiry, session_public_key, revoked, spent_today
  spend transfers STRK from the contract to recipient
        │
        ▼
Backend
  encrypts the session private key (never returned)
  returns calldata; preflight does not persist spent_today
  appends hashes; receipt refresh confirms or fails them
  sets revoked only after a confirmed revoke receipt
```

AVNU may sponsor `register_session` when you submit the `paymaster` body yourself. It does not sponsor `spend` or `revoke_session`.

---

## References

- [Starknet Chain Info](https://docs.starknet.io/resources/chain-info/)
- [Starknet Compatibility](https://docs.starknet.io/learn/cheatsheets/compatibility)
- [AVNU Paymaster](https://docs.avnu.fi/docs/paymaster/gasfree)
- [Voyager Sepolia](https://sepolia.voyager.online/)
- [Starknet Faucet](https://starknet-faucet.vercel.app/)
- `REVVING_UP_STARKNET.md` — Scarb, starkli, sncast, declare, deploy
- `backend/CHAIN_REGISTRY.md` — registry and RPC
- `backend/contracts/starknet/src/spending_policy.cairo` — contract source (comments only; this deploy was not replaced)

| Component | Address |
|-----------|---------|
| Policy contract | `0x04f1882a972a276e27b423cfadd29d24a75e798b60cc7d8d4b536ebe0741aaa4` |
| Class | `0x00a4e8f1b7461cc30324074ebf7320a07d20456a0f27ad33017f36dcd9565ff1` |
| STRK | `0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d` |
| Ready owner | `0x026a705Ae4dB69a318E5b6ce945a7c47776da45f5F281aB0E0A43A13D91FF0fc` |

---

## For Maintainers: Deploying a New Policy Contract

The Sepolia contract above is the one the app uses. Deploy a new one only for a new network or a new class. This tree’s Cairo comments were not redeployed.

- **Scarb 2.19.0** (Sierra 1.9.0)
- **sncast** 0.64.1+
- **starkli 0.4.2** for the OpenZeppelin deployer account
- Funded deployer. Constructor argument is the Ready owner.

```bash
cd backend/contracts/starknet
asdf set scarb 2.19.0
scarb clean && scarb build
python3 -c "import json; print(json.load(open('target/dev/spending_policy_SpendingPolicy.contract_class.json'))['sierra_program'][:3])"
```

The header must be `0x1 0x9 0x0`. Declare and deploy with publicnode (or Cartridge `/rpc/v0_10`), the same keystore and account as `REVVING_UP_STARKNET.md`, and the Ready address as the only constructor calldata. Point `STARKNET_POLICY_CONTRACT` at the new address. Do not put the address only in a second frontend constant; calls use the env var.

```bash
cd backend
uv run pytest tests/unit/test_starknet_policy.py -v
```

---

## Not in this version

- The session private key does not sign `spend`, and it is not registered as a Ready session key.
- Sessions do not auto-renew. Receipt checks run about 15 seconds and 60 seconds after submit, then only when Txn History is opened.
- Mainnet is not deployed.

---

**Last Updated:** October 29, 2026
**Contract:** Sierra 1.9.0 class already on Starknet Sepolia (not redeployed with the latest comments)
**Network:** Starknet Sepolia
