"""Opt-in real MongoDB checks for the payment ledger (#3).

Idempotency and concurrency guarantees come from MongoDB unique indexes and
atomic conditional updates, so they are tested against a real server. Each test
owns and drops a unique database. Run against disposable local MongoDB only:
QB2_MONGODB_TEST_URI=mongodb://127.0.0.1:27017 uv run pytest tests/live -q
"""

from __future__ import annotations

import asyncio
import os
import random
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from bson import Decimal128
from pymongo import AsyncMongoClient

from quantum_backend_v2.payments.errors import (
    HoldExceededError,
    IdempotencyConflictError,
    InsufficientCreditError,
    InvalidStatusTransitionError,
    PaymentUncertainError,
)
from quantum_backend_v2.payments.ledger import CREDIT_HOLDS, CREDIT_LEDGER, LedgerService
from quantum_backend_v2.payments.models import (
    LedgerEntryType,
    PaymentEventStatus,
    PaymentPurpose,
    PaymentRail,
    utc_now,
)

pytestmark = pytest.mark.anyio

D = Decimal


@pytest.fixture
async def ledger() -> AsyncIterator[LedgerService]:
    uri = os.getenv("QB2_MONGODB_TEST_URI")
    if not uri:
        pytest.skip("Set QB2_MONGODB_TEST_URI to opt into disposable local MongoDB tests")
    parsed = urlsplit(uri)
    if parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Live ledger tests accept only local MongoDB")
    client: AsyncMongoClient = AsyncMongoClient(uri, serverSelectionTimeoutMS=2000)
    database_name = f"qmesh_ledger_test_{uuid4().hex}"
    try:
        await client.admin.command("ping")
        service = LedgerService(client[database_name])
        await service.ensure_indexes()
        yield service
    finally:
        await client.drop_database(database_name)
        await client.close()


async def _card_purchase(ledger: LedgerService, key: str, amount: str, account: str = "user-1"):
    return await ledger.record_event(
        idempotency_key=key,
        rail=PaymentRail.CARD,
        purpose=PaymentPurpose.CREDIT_PURCHASE,
        amount=D(amount),
        ledger_account_id=account,
    )


async def _funded(ledger: LedgerService, amount: str, account: str = "user-1") -> None:
    key = f"seed-{uuid4().hex}"
    await _card_purchase(ledger, key, amount, account)
    await ledger.confirm(key)


async def _assert_no_drift(ledger: LedgerService) -> None:
    report = await ledger.run_reconciliation()
    assert report.drifted_accounts == ()


# ----------------------------------------------------------------------
# Payment events
# ----------------------------------------------------------------------


async def test_replaying_a_key_returns_the_stored_event(ledger: LedgerService) -> None:
    first = await _card_purchase(ledger, "stripe:checkout:cs_1", "10")
    second = await _card_purchase(ledger, "stripe:checkout:cs_1", "10")

    assert first.created and not second.created
    assert second.event.idempotency_key == first.event.idempotency_key
    assert len(await ledger.list_events()) == 1


async def test_replaying_a_key_with_different_amount_conflicts(ledger: LedgerService) -> None:
    await _card_purchase(ledger, "stripe:checkout:cs_1", "10")
    with pytest.raises(IdempotencyConflictError):
        await _card_purchase(ledger, "stripe:checkout:cs_1", "11")


async def test_concurrent_confirms_credit_exactly_once(ledger: LedgerService) -> None:
    await _card_purchase(ledger, "stripe:checkout:cs_1", "25")

    await asyncio.gather(*(ledger.confirm("stripe:checkout:cs_1") for _ in range(10)))

    entries = await ledger.entries("user-1")
    assert [e.entry_type for e in entries] == [LedgerEntryType.CREDIT]
    assert (await ledger.balance("user-1")).available == D("25")
    await _assert_no_drift(ledger)


async def test_concurrent_records_of_one_key_create_one_event(ledger: LedgerService) -> None:
    results = await asyncio.gather(
        *(_card_purchase(ledger, "stripe:checkout:cs_1", "5") for _ in range(10))
    )
    assert sum(r.created for r in results) == 1
    assert len(await ledger.list_events()) == 1


async def test_uncertain_event_blocks_retry_until_reconciled(ledger: LedgerService) -> None:
    await _card_purchase(ledger, "payout:p1:f1", "8")
    await ledger.mark_uncertain("payout:p1:f1", reason="rpc timed out")

    with pytest.raises(PaymentUncertainError):
        await _card_purchase(ledger, "payout:p1:f1", "8")
    with pytest.raises(InvalidStatusTransitionError):
        await ledger.confirm("payout:p1:f1")
    assert (await ledger.list_events(status=PaymentEventStatus.UNCERTAIN))[0].idempotency_key == (
        "payout:p1:f1"
    )

    event = await ledger.reconcile(
        "payout:p1:f1",
        outcome=PaymentEventStatus.CONFIRMED,
        actor="admin-1",
        reason="tx found on explorer",
        external_ref="0xabc",
    )
    assert event.status is PaymentEventStatus.CONFIRMED
    assert [c.status for c in event.status_history] == [
        PaymentEventStatus.PENDING,
        PaymentEventStatus.UNCERTAIN,
        PaymentEventStatus.CONFIRMED,
    ]
    assert (await ledger.balance("user-1")).available == D("8")


async def test_failed_event_cannot_be_confirmed(ledger: LedgerService) -> None:
    await _card_purchase(ledger, "k1", "3")
    await ledger.fail("k1", reason="card declined")
    with pytest.raises(InvalidStatusTransitionError):
        await ledger.confirm("k1")
    assert (await ledger.balance("user-1")).available == D("0")


async def test_sweep_flags_only_stale_pending_without_reference(ledger: LedgerService) -> None:
    await _card_purchase(ledger, "no-ref", "1")
    await ledger.record_event(
        idempotency_key="with-ref",
        rail=PaymentRail.ONCHAIN,
        purpose=PaymentPurpose.TRANSFER,
        amount=D("1"),
        external_ref="0xabc",
    )
    await _card_purchase(ledger, "fresh", "1")

    later = utc_now() + timedelta(hours=1)
    # Only events created before the cutoff are stale; keep "fresh" after it.
    await ledger._events.update_one(  # noqa: SLF001 - test setup
        {"idempotency_key": "fresh"}, {"$set": {"created_at": later}}
    )
    report = await ledger.run_reconciliation(now=later)

    assert report.marked_uncertain == ("no-ref",)
    assert (await ledger.get_event("with-ref")).status is PaymentEventStatus.PENDING


# ----------------------------------------------------------------------
# Holds, captures and releases
# ----------------------------------------------------------------------


async def test_hold_capture_release_flow(ledger: LedgerService) -> None:
    await _funded(ledger, "100")

    await ledger.hold("user-1", D("40"), hold_id="job-1", job_id="job-1")
    await ledger.capture("job-1", D("25"), idempotency_key="capture:job-1")
    released = await ledger.release("job-1", idempotency_key="release:job-1")

    assert released is not None and released.amount == D("15")
    balance = await ledger.balance("user-1")
    assert (balance.available, balance.held, balance.spent) == (D("75"), D("0"), D("25"))
    await _assert_no_drift(ledger)


async def test_hold_rejects_insufficient_credit(ledger: LedgerService) -> None:
    await _funded(ledger, "10")
    with pytest.raises(InsufficientCreditError):
        await ledger.hold("user-1", D("10.01"), hold_id="job-1")
    with pytest.raises(InsufficientCreditError):
        await ledger.hold("nobody", D("1"), hold_id="job-2")


async def test_concurrent_holds_never_overspend(ledger: LedgerService) -> None:
    await _funded(ledger, "100")

    results = await asyncio.gather(
        *(ledger.hold("user-1", D("30"), hold_id=f"job-{i}") for i in range(10)),
        return_exceptions=True,
    )

    assert sum(not isinstance(r, Exception) for r in results) == 3
    assert all(isinstance(r, InsufficientCreditError) for r in results if isinstance(r, Exception))
    balance = await ledger.balance("user-1")
    assert (balance.available, balance.held) == (D("10"), D("90"))
    await _assert_no_drift(ledger)


async def test_concurrent_double_capture_only_succeeds_once(ledger: LedgerService) -> None:
    await _funded(ledger, "50")
    await ledger.hold("user-1", D("50"), hold_id="job-1")

    results = await asyncio.gather(
        *(ledger.capture("job-1", D("50"), idempotency_key=f"capture-{i}") for i in range(10)),
        return_exceptions=True,
    )

    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert all(isinstance(r, HoldExceededError) for r in results if isinstance(r, Exception))
    assert (await ledger.balance("user-1")).spent == D("50")
    await _assert_no_drift(ledger)


async def test_concurrent_replays_of_one_capture_write_one_entry(ledger: LedgerService) -> None:
    await _funded(ledger, "50")
    await ledger.hold("user-1", D("50"), hold_id="job-1")

    results = await asyncio.gather(
        *(ledger.capture("job-1", D("50"), idempotency_key="capture:job-1") for _ in range(10))
    )

    assert len({r.entry_id for r in results}) == 1
    entries = await ledger.entries("user-1")
    captures = [e for e in entries if e.entry_type is LedgerEntryType.CAPTURE]
    assert len(captures) == 1
    await _assert_no_drift(ledger)


async def test_concurrent_double_release_only_returns_once(ledger: LedgerService) -> None:
    await _funded(ledger, "50")
    await ledger.hold("user-1", D("50"), hold_id="job-1")

    results = await asyncio.gather(
        *(ledger.release("job-1", idempotency_key=f"release-{i}") for i in range(10)),
        return_exceptions=True,
    )

    released = [r for r in results if r is not None and not isinstance(r, Exception)]
    assert len(released) == 1 and released[0].amount == D("50")
    balance = await ledger.balance("user-1")
    assert (balance.available, balance.held) == (D("50"), D("0"))
    await _assert_no_drift(ledger)


async def test_capture_rebuilds_a_hold_guard_lost_in_a_crash(ledger: LedgerService) -> None:
    await _funded(ledger, "20")
    await ledger.hold("user-1", D("20"), hold_id="job-1")
    await ledger.capture("job-1", D("5"), idempotency_key="capture:a")
    # Simulate a crash between inserting the hold entry and its guard.
    await ledger._db[CREDIT_HOLDS].delete_many({})  # noqa: SLF001 - test setup

    await ledger.capture("job-1", D("15"), idempotency_key="capture:b")
    with pytest.raises(HoldExceededError):
        await ledger.capture("job-1", D("0.01"), idempotency_key="capture:c")
    assert (await ledger.balance("user-1")).spent == D("20")


async def test_reconciliation_reports_guard_drift(ledger: LedgerService) -> None:
    await _funded(ledger, "20")
    # Simulate a crash after the ledger insert but before the guard update.
    await ledger._db[CREDIT_LEDGER].insert_one(  # noqa: SLF001 - test setup
        {
            "entry_id": "x",
            "idempotency_key": "orphan",
            "account_id": "user-1",
            "entry_type": "credit",
            "amount": Decimal128("5"),
            "asset": "USDC",
            "created_at": utc_now(),
        }
    )
    report = await ledger.run_reconciliation()
    assert [d.account_id for d in report.drifted_accounts] == ["user-1"]
    assert report.drifted_accounts[0].ledger.available == D("25")
    assert report.drifted_accounts[0].guard_available == D("20")


@pytest.mark.parametrize("seed", range(5))
async def test_random_concurrent_operations_keep_guards_in_sync(
    ledger: LedgerService, seed: int
) -> None:
    """Property: after random concurrent traffic the guards still equal the ledger sums."""
    rng = random.Random(seed)
    await _funded(ledger, "500")
    hold_ids: list[str] = []

    async def one_op(i: int) -> None:
        op = rng.choice(["credit", "hold", "capture", "release"])
        amount = D(rng.randint(1, 4000)) / D(100)
        try:
            if op == "credit":
                await ledger.credit("user-1", amount, idempotency_key=f"c-{seed}-{i}")
            elif op == "hold":
                hold_id = f"h-{seed}-{i}"
                await ledger.hold("user-1", amount, hold_id=hold_id)
                hold_ids.append(hold_id)
            elif hold_ids:
                target = rng.choice(hold_ids)
                if op == "capture":
                    await ledger.capture(target, amount, idempotency_key=f"cap-{seed}-{i}")
                else:
                    await ledger.release(target, idempotency_key=f"rel-{seed}-{i}")
        except (InsufficientCreditError, HoldExceededError):
            pass

    for batch in range(10):
        await asyncio.gather(*(one_op(batch * 10 + i) for i in range(10)))

    balance = await ledger.balance("user-1")
    assert balance.available >= 0 and balance.held >= 0
    await _assert_no_drift(ledger)
