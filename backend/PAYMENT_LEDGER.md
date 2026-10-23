# Payment events and credit ledger — Part of #3

Every payment rail (x402, cards, Zcash, swaps, on-chain transfers) records the
same kind of payment event, and value that enters the platform's internal credit
system is written to one append-only, USDC-denominated ledger. The aim is
"accept anywhere and settle once": idempotency, reconciliation and
double-payment protection exist once instead of once per rail.

Code: `src/quantum_backend_v2/payments/` (`models.py`, `ledger.py`, `errors.py`).

## Collections

| Collection | Contents | Unique on |
| --- | --- | --- |
| `payment_events` | One document per payment, with its status history | `idempotency_key` |
| `credit_ledger` | Append-only entries: `credit`, `hold`, `capture`, `release` | `idempotency_key` |
| `credit_holds` | Guard: amount still capturable or releasable per hold | `hold_id` |
| `credit_balances` | Guard: cached `available` and `held` per account | `account_id` |

`payment_events` also indexes `job_id`, `proposal_id`, `status` and
`(status, created_at)`. Money is stored as `Decimal128`, never as floats.
Indexes are created at app startup and before a `LedgerService` first writes.

## Payment events

`record_event` stores an event once per idempotency key. Replaying a key returns
the stored event with `created=False`. Replaying it with a different rail,
purpose, asset, amount or ledger account raises `IdempotencyConflictError`.

```
pending ──> confirmed ──> refunded
   │  └──> failed
   └──> uncertain ──> confirmed | failed   (admin reconciliation only)
```

- `confirm` (pending → confirmed) credits the event's `ledger_account_id`, if it
  has one. Calling it again is harmless and finishes a credit a crash interrupted.
- `mark_uncertain` is for payments whose outcome is unknown, such as a timeout after a
  transaction may have been broadcast. Replaying an uncertain key raises
  `PaymentUncertainError`, and `confirm` refuses it: **uncertain payments are
  never retried automatically.**
- `reconcile` lets an admin resolve a pending or uncertain event as confirmed or
  failed after checking the rail. The admin's id and reason go into the status history.
- `refunded` is reserved. Refund policy is out of scope for #3.

### Choosing idempotency keys

Use a key that names the payment itself, so a retry produces the same key:

| Payment | Key |
| --- | --- |
| Stripe credit pack (#10) | `stripe:checkout:<checkout session id>` |
| Fragment payout | `fragment_payout:<proposal id>:<fragment id>:<attempt>` |
| Full escrow release | `escrow_release:<proposal id>:<attempt>` |
| Proposal funding | `proposal_funding:<proposal id>:<deposit tx hash>` |
| USDC transfer | `metadata["idempotency_key"]`, else `transfer:<uuid>` |

Use the Stripe session id rather than the event id: an asynchronously paid
session produces two events with different ids for the same payment.

## Credit ledger

Ledger entries are never updated or deleted. An account's balance is defined by
`derive_balance`: credits add to `available`; a hold moves value from
`available` to `held`; a capture spends held value; a release returns it.
`LedgerService.balance` always sums the entries; it never reads the guards.

```python
await ledger.hold(account, Decimal("12"), hold_id=job_id, job_id=job_id)  # on submit
await ledger.capture(job_id, actual_cost, idempotency_key=f"capture:{job_id}")
await ledger.release(job_id, idempotency_key=f"release:{job_id}")  # the rest
```

### Concurrency without transactions

Our MongoDB runs as a standalone server, which has no multi-document
transactions. Instead, each hold, capture or release changes its guard
document with one atomic conditional update:

- a hold succeeds only if `credit_balances.available >= amount`;
- a capture or release succeeds only if `credit_holds.remaining >= amount`;
- a full release compares and sets the remainder it read.

The ledger entry's unique key decides between concurrent replays of the same
operation; the loser undoes its guard change and returns the winner's entry.

Writes are ordered so a crash between two steps always **fails closed**: value
can end up reserved and unusable until reconciled, but never spendable twice.
Credits write the ledger before the guard; holds, captures and releases change
the guard first. A hold guard lost between two inserts is rebuilt from the
ledger on the next capture or release.

## Reconciliation

`run_reconciliation` runs every `QB2_PAYMENT_RECONCILE_INTERVAL_SECONDS`
(default 300; `0` disables) and on demand. It:

1. marks pending events older than 30 minutes that have **no external
   reference** as uncertain. Their outcome was never recorded. Events
   with a tx hash or Stripe id are awaiting their rail and are left alone;
2. compares each account's `credit_balances` guard with its ledger sum and
   reports drift. It does not repair drift, so an operator can find the cause first.

## Admin API

All routes require the admin role. None of them can write ledger entries.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/admin/payments/events?status=uncertain` | List events (also `job_id`, `proposal_id`, `limit`) |
| GET | `/api/v1/admin/payments/events/{key}` | One event with its status history |
| POST | `/api/v1/admin/payments/events/{key}/reconcile` | `{"outcome": "confirmed" \| "failed", "reason": "...", "external_ref": "0x..."}` |
| POST | `/api/v1/admin/payments/reconciliation` | Run the sweep now |
| GET | `/api/v1/admin/payments/accounts/{account_id}/balance` | Balance derived from the ledger |

## First consumers

The existing Base Sepolia paths write events without changing their responses:

- `AgentKitService.transfer_usdc` records a pending event before sending and
  confirms it with the tx hash.
- `ProposalService.fund_proposal` records a confirmed event for the escrow deposit.
- `_pay_fragment_researcher` and `_release_all_escrow` record a pending event per
  attempt before withdrawing. A new attempt is allowed only after every earlier
  one failed, so resubmitting results no longer pays a researcher twice.

A send that fails with `ValueError` (validation, before anything is sent) marks the
event failed. Any other error marks it uncertain. If updating an event fails
after funds moved, the error is logged and the sweep flags the event later.

On-chain events are confirmed when the transaction is broadcast, as the legacy
`payments` records are. Receipt-based confirmation is a follow-up.

## Integrating a new rail

1. `record_event(...)` with a key that names the payment, before value moves.
   Set `ledger_account_id` if the payment should become credit.
2. Move the value only if `created` is true.
3. `confirm(key, external_ref=...)` when it settles, `fail` when it definitely
   did not, and `mark_uncertain` when you cannot tell.

## Prepaid credits (#10)

Users can buy credit packs by card and spend the credits on circuit runs. One
credit is one USDC, so card-bought credits sit in the same ledger as everything else.

```
Settings → POST /api/billing/credits/checkout → Stripe Checkout (mode: payment)
Stripe → /api/auth/stripe/webhook  (signature check, event-id de-dupe)
       → line items → credits      (from STRIPE_CREDIT_PACKS, never the client)
       → POST /api/v1/internal/billing/credit-purchases  (X-Billing-Internal-Secret)
       → payment event stripe:checkout:<session id> → ledger credit
```

**Buying.** Packs are Stripe one-time Prices mapped to credit amounts in
`STRIPE_CREDIT_PACKS` (frontend). The webhook handles credit-pack sessions itself
and does not forward them to the subscription plugin. It works out the credits from
the session's line items as Stripe recorded them. A session paid by a delayed
method completes unpaid and is credited on
`checkout.session.async_payment_succeeded`.

**Exactly once.** The frontend de-duplicates Stripe events by id. The backend
keys the purchase on the Checkout Session (`stripe:checkout:<session id>`), so a
redelivered event, or the two events of one async session, credit once. A
redelivery also finishes a credit that a crash interrupted.

**Spending.** With `QB2_CIRCUIT_JOB_CREDIT_COST` above 0, submitting a circuit holds
its cost under `job:<job id>`, or returns `402 insufficient_credits`. A completed job
captures the hold and a failed one releases it. If the server stops mid-job, the
hold stays reserved and is never spent twice. Releasing holds for jobs that never
finish is a follow-up; there is no admin route for it yet. The default of 0
keeps runs free. x402 runs are paid per request and never use credits.

**Identity.** Runs and balances use the signed `qn1` assertion, so both sides need
the same `AGENT_AUTH_BRIDGE_SECRET`. Without it, runs are submitted anonymously as
before and are not charged to a user.

### Configuration

| Side | Variable | Purpose |
| --- | --- | --- |
| Frontend | `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` | Stripe billing (#42); required for packs too |
| Frontend | `STRIPE_CREDIT_PACKS` | `price_abc:10,price_def:50` |
| Both | `BILLING_INTERNAL_SECRET` / `QB2_BILLING_INTERNAL_SECRET` | Same 32+ character secret; guards the purchase route |
| Both | `AGENT_AUTH_BRIDGE_SECRET` | Signs the user's identity for runs and balances |
| Backend | `QB2_CIRCUIT_JOB_CREDIT_COST` | Credits per circuit run; `0` disables charging |

### Manual test (Stripe CLI, test mode)

1. In the Stripe Dashboard (test mode), create a product with a **one-time** price,
   e.g. $10, and set `STRIPE_CREDIT_PACKS=price_...:10`.
2. Set the secrets above, `QB2_CIRCUIT_JOB_CREDIT_COST=2`, and restart both apps.
3. `stripe listen --forward-to localhost:3000/api/auth/stripe/webhook`
4. Settings → Credits → **Buy 10 credits · $10.00**, pay with `4242 4242 4242 4242`.
   The balance shows 10.
5. `stripe events resend <evt_id>`: the webhook returns `duplicate: true` and the
   balance stays 10. `GET /api/v1/admin/payments/events/stripe:checkout:<cs_...>`
   shows one confirmed card event.
6. Submit a circuit run: the balance drops to 8, with 2 reserved while it runs and
   spent once it completes. With fewer than 2 credits, submitting shows the 402 message.

## Tests

```bash
uv run pytest tests/unit/test_payment_ledger_models.py tests/unit/test_payments_admin_api.py tests/unit/test_credits_api.py
# Frontend webhook and credit-pack tests:
(cd ../frontend && bun run test:billing)
# Idempotency and concurrency need a real server (disposable local MongoDB only):
QB2_MONGODB_TEST_URI=mongodb://127.0.0.1:27017 uv run pytest tests/live -q
```

The live tests cover replayed keys, concurrent confirms, concurrent holds that
would overspend, concurrent double captures and releases, rebuilding a lost hold
guard, drift detection, randomized concurrent traffic that must keep guards equal
to ledger sums, and the payout paths (paid once, never retried when uncertain).
`tests/live/test_credits_mongo.py` covers credit purchases delivered twice or
concurrently, the two events of one async session, crash recovery, and job
metering that charges only completed jobs.
