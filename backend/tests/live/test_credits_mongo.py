"""Opt-in real MongoDB checks for card-bought credits and job metering (#10).

QB2_MONGODB_TEST_URI=mongodb://127.0.0.1:27017 uv run pytest tests/live -q
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from quantum_backend_v2.payments.credits import (
    CreditPurchase,
    JobCreditMeter,
    record_credit_purchase,
)
from quantum_backend_v2.payments.errors import InsufficientCreditError
from quantum_backend_v2.payments.ledger import CREDIT_LEDGER, LedgerService
from quantum_backend_v2.payments.models import LedgerEntryType, PaymentEventStatus

pytestmark = pytest.mark.anyio

D = Decimal


@pytest.fixture
async def ledger() -> AsyncIterator[LedgerService]:
    uri = os.getenv("QB2_MONGODB_TEST_URI")
    if not uri:
        pytest.skip("Set QB2_MONGODB_TEST_URI to opt into disposable local MongoDB tests")
    parsed = urlsplit(uri)
    if parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Live credit tests accept only local MongoDB")
    client: AsyncMongoClient = AsyncMongoClient(uri, serverSelectionTimeoutMS=2000)
    name = f"qmesh_credits_test_{uuid4().hex}"
    try:
        service = LedgerService(client[name])
        await service.ensure_indexes()
        yield service
    finally:
        await client.drop_database(name)
        await client.close()


def _purchase(session: str = "cs_test_1", credits: str = "10") -> CreditPurchase:
    return CreditPurchase(
        checkout_session_id=session,
        account_id="user-1",
        credits=D(credits),
        stripe_event_id="evt_1",
        price_id="price_1",
    )


async def _credits(ledger: LedgerService) -> list[Decimal]:
    return [
        e.amount for e in await ledger.entries("user-1") if e.entry_type is LedgerEntryType.CREDIT
    ]


async def test_webhook_delivered_twice_credits_once(ledger: LedgerService) -> None:
    first = await record_credit_purchase(ledger, _purchase())
    second = await record_credit_purchase(ledger, _purchase())

    assert (first.created, second.created) == (True, False)
    assert await _credits(ledger) == [D("10")]
    event = await ledger.get_event("stripe:checkout:cs_test_1")
    assert event.status is PaymentEventStatus.CONFIRMED
    assert event.external_ref == "cs_test_1"


async def test_concurrent_deliveries_credit_once(ledger: LedgerService) -> None:
    await asyncio.gather(*(record_credit_purchase(ledger, _purchase()) for _ in range(10)))

    assert await _credits(ledger) == [D("10")]
    assert (await ledger.balance("user-1")).available == D("10")


async def test_completed_and_async_succeeded_events_for_one_session_credit_once(
    ledger: LedgerService,
) -> None:
    # Different Stripe events, same Checkout Session.
    await record_credit_purchase(
        ledger, _purchase().model_copy(update={"stripe_event_id": "evt_a"})
    )
    await record_credit_purchase(
        ledger, _purchase().model_copy(update={"stripe_event_id": "evt_b"})
    )

    assert await _credits(ledger) == [D("10")]


async def test_redelivery_finishes_a_credit_interrupted_by_a_crash(ledger: LedgerService) -> None:
    await record_credit_purchase(ledger, _purchase())
    # Simulate a crash after the event was stored but before the credit entry.
    await ledger._db[CREDIT_LEDGER].delete_many({})  # noqa: SLF001 - test setup
    await ledger._db["credit_balances"].delete_many({})  # noqa: SLF001 - test setup

    await record_credit_purchase(ledger, _purchase())

    assert await _credits(ledger) == [D("10")]
    assert (await ledger.run_reconciliation()).drifted_accounts == ()


async def test_job_meter_charges_only_completed_jobs(ledger: LedgerService) -> None:
    await record_credit_purchase(ledger, _purchase(credits="5"))
    meter = JobCreditMeter(ledger, cost=D("2"))

    await meter.reserve("user-1", "job-ok")
    await meter.reserve("user-1", "job-bad")
    with pytest.raises(InsufficientCreditError):
        await meter.reserve("user-1", "job-third")

    await meter.settle("job-ok", succeeded=True)
    await meter.settle("job-bad", succeeded=False)
    # Settling again (e.g. a retried background task) changes nothing.
    await meter.settle("job-ok", succeeded=True)
    await meter.settle("job-bad", succeeded=False)

    balance = await ledger.balance("user-1")
    assert (balance.available, balance.held, balance.spent) == (D("3"), D("0"), D("2"))
    assert (await ledger.run_reconciliation()).drifted_accounts == ()


async def test_meter_rejects_a_non_positive_cost(ledger: LedgerService) -> None:
    with pytest.raises(ValueError):
        JobCreditMeter(ledger, cost=D("0"))
