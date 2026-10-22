"""Admin-only payment-event and credit-ledger endpoints (#3).

The ledger is append-only, so this router exposes no way to write entries.
Admins can list events (notably uncertain ones), resolve an event after
checking its rail, run the reconciliation sweep and read derived balances.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from quantum_backend_v2.api.deps.auth import AdminUser
from quantum_backend_v2.api.errors.models import conflict, not_found
from quantum_backend_v2.payments.errors import (
    InvalidStatusTransitionError,
    PaymentEventNotFoundError,
)
from quantum_backend_v2.payments.ledger import LedgerService
from quantum_backend_v2.payments.models import (
    CreditBalance,
    PaymentEvent,
    PaymentEventStatus,
    ReconciliationReport,
)


class ReconcileRequest(BaseModel):
    """An admin's verdict on a pending or uncertain payment."""

    outcome: Literal["confirmed", "failed"]
    reason: str = Field(min_length=1, max_length=1000)
    external_ref: str | None = Field(default=None, max_length=256)


def build_payments_admin_router(*, ledger_service: LedgerService) -> APIRouter:
    """Build the admin payments router."""
    router = APIRouter(prefix="/api/v1/admin/payments", tags=["payments-admin"])

    @router.get(
        "/events",
        response_model=list[PaymentEvent],
        summary="List payment events, newest first",
    )
    async def list_events(
        _: AdminUser,
        status: PaymentEventStatus | None = None,
        job_id: str | None = None,
        proposal_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[PaymentEvent]:
        return await ledger_service.list_events(
            status=status, job_id=job_id, proposal_id=proposal_id, limit=limit
        )

    @router.get(
        "/events/{idempotency_key}",
        response_model=PaymentEvent,
        summary="Get one payment event",
    )
    async def get_event(idempotency_key: str, _: AdminUser) -> PaymentEvent:
        event = await ledger_service.get_event(idempotency_key)
        if event is None:
            raise not_found("Payment event", idempotency_key)
        return event

    @router.post(
        "/events/{idempotency_key}/reconcile",
        response_model=PaymentEvent,
        summary="Resolve a pending or uncertain payment event",
    )
    async def reconcile_event(
        idempotency_key: str, body: ReconcileRequest, admin: AdminUser
    ) -> PaymentEvent:
        try:
            return await ledger_service.reconcile(
                idempotency_key,
                outcome=PaymentEventStatus(body.outcome),
                actor=admin.user_id,
                reason=body.reason,
                external_ref=body.external_ref,
            )
        except PaymentEventNotFoundError:
            raise not_found("Payment event", idempotency_key) from None
        except InvalidStatusTransitionError as exc:
            raise conflict(str(exc)) from None

    @router.post(
        "/reconciliation",
        response_model=ReconciliationReport,
        summary="Run the reconciliation sweep now",
    )
    async def run_reconciliation(_: AdminUser) -> ReconciliationReport:
        return await ledger_service.run_reconciliation()

    @router.get(
        "/accounts/{account_id}/balance",
        response_model=CreditBalance,
        summary="Balance derived from the account's ledger entries",
    )
    async def get_balance(account_id: str, _: AdminUser) -> CreditBalance:
        return await ledger_service.balance(account_id)

    return router
