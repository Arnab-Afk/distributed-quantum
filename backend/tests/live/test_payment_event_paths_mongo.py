"""Opt-in real MongoDB checks for payment events on the legacy AgentKit paths (#3).

Uses Motor, the driver the legacy services use, against disposable local MongoDB:
QB2_MONGODB_TEST_URI=mongodb://127.0.0.1:27017 uv run pytest tests/live -q
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import AsyncMongoClient

from db.agentkit_collections import PaymentDocument
from quantum_backend_v2.payments.errors import PaymentUncertainError
from quantum_backend_v2.payments.ledger import LedgerService
from quantum_backend_v2.payments.models import PaymentEventStatus, PaymentPurpose
from services.payment_events import begin_payout, settle_failed_send
from services.proposal_service import ProposalService

pytestmark = pytest.mark.anyio

TX = "0x" + "b" * 64
RESEARCHER_WALLET = "0x" + "1" * 40
PROPOSAL_WALLET = "0x" + "2" * 40


@pytest.fixture
async def db() -> AsyncIterator[object]:
    uri = os.getenv("QB2_MONGODB_TEST_URI")
    if not uri:
        pytest.skip("Set QB2_MONGODB_TEST_URI to opt into disposable local MongoDB tests")
    parsed = urlsplit(uri)
    if parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Live payment tests accept only local MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
    beanie_client: AsyncMongoClient = AsyncMongoClient(uri, serverSelectionTimeoutMS=2000)
    name = f"qmesh_payment_paths_test_{uuid4().hex}"
    try:
        # The payout path still builds a legacy PaymentDocument, which needs Beanie;
        # Beanie runs on Async PyMongo, as it does in the app.
        await init_beanie(database=beanie_client[name], document_models=[PaymentDocument])
        yield client[name]
    finally:
        await client.drop_database(name)
        client.close()
        await beanie_client.close()


def _proposal_service(db: object, agentkit: MagicMock) -> ProposalService:
    # Bypass __init__, which builds AWS and MongoDB clients from the environment.
    service = object.__new__(ProposalService)
    service.db = db
    service.ledger = LedgerService(db)
    service._agentkit_service = agentkit
    return service


async def _seed_fragment(db: object) -> None:
    await db.research_proposals.insert_one(  # type: ignore[attr-defined]
        {
            "proposal_id": "p1",
            "researcher_wallet": PROPOSAL_WALLET,
            "fragments": [{"fragment_id": "f1", "budget": "12.5", "claimed_by": "r1"}],
        }
    )
    await db.wallets.insert_one(  # type: ignore[attr-defined]
        {"entity_id": "r1", "default_address": RESEARCHER_WALLET}
    )


def _agentkit(withdraw: AsyncMock) -> MagicMock:
    agentkit = MagicMock()
    agentkit.chain.chain_id = "eip155:84532"
    agentkit.aave_withdraw = withdraw
    return agentkit


async def test_begin_payout_allows_a_new_attempt_only_after_failure(db: object) -> None:
    ledger = LedgerService(db)
    fields = {"purpose": PaymentPurpose.WORKER_PAYOUT, "amount": Decimal("5")}

    first = await begin_payout(ledger, "fragment_payout:p1:f1", **fields)
    assert first == "fragment_payout:p1:f1:1"
    with pytest.raises(ValueError, match="already pending"):
        await begin_payout(ledger, "fragment_payout:p1:f1", **fields)

    await ledger.fail(first, reason="reverted")
    second = await begin_payout(ledger, "fragment_payout:p1:f1", **fields)
    assert second == "fragment_payout:p1:f1:2"

    await ledger.mark_uncertain(second, reason="timeout")
    with pytest.raises(PaymentUncertainError):
        await begin_payout(ledger, "fragment_payout:p1:f1", **fields)


async def test_settle_failed_send_separates_validation_from_unknown_errors(db: object) -> None:
    ledger = LedgerService(db)
    fields = {"purpose": PaymentPurpose.TRANSFER, "amount": Decimal("1")}
    invalid = await begin_payout(ledger, "a", **fields)
    timed_out = await begin_payout(ledger, "b", **fields)

    await settle_failed_send(ledger, invalid, ValueError("amount must be positive"))
    await settle_failed_send(ledger, timed_out, TimeoutError("rpc timed out"))

    assert (await ledger.get_event(invalid)).status is PaymentEventStatus.FAILED
    assert (await ledger.get_event(timed_out)).status is PaymentEventStatus.UNCERTAIN


async def test_fragment_is_paid_once_and_response_is_unchanged(db: object) -> None:
    await _seed_fragment(db)
    withdraw = AsyncMock(return_value={"transaction_hash": TX, "basescan_url": "u"})
    service = _proposal_service(db, _agentkit(withdraw))

    result = await service._pay_fragment_researcher("p1", "f1")

    assert set(result) == {"amount", "transaction_hash", "researcher_wallet", "timestamp"}
    assert result["transaction_hash"] == TX
    event = await service.ledger.get_event("fragment_payout:p1:f1:1")
    assert event.status is PaymentEventStatus.CONFIRMED
    assert event.external_ref == TX
    assert event.chain_id == "eip155:84532"
    assert event.amount == Decimal("12.5")

    # Resubmitting results used to pay the researcher a second time.
    with pytest.raises(ValueError, match="already confirmed"):
        await service._pay_fragment_researcher("p1", "f1")
    assert withdraw.await_count == 1


async def test_uncertain_payout_is_not_retried(db: object) -> None:
    await _seed_fragment(db)
    withdraw = AsyncMock(side_effect=TimeoutError("rpc timed out"))
    service = _proposal_service(db, _agentkit(withdraw))

    with pytest.raises(TimeoutError):
        await service._pay_fragment_researcher("p1", "f1")
    with pytest.raises(PaymentUncertainError):
        await service._pay_fragment_researcher("p1", "f1")

    assert withdraw.await_count == 1
    uncertain = await service.ledger.list_events(status=PaymentEventStatus.UNCERTAIN)
    assert [e.idempotency_key for e in uncertain] == ["fragment_payout:p1:f1:1"]
