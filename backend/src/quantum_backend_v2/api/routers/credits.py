"""Prepaid-credit endpoints (#10).

Users read their own balance. The frontend's Stripe webhook records paid
credit packs through an internal route guarded by a shared secret, so card
data never reaches this service: only the Checkout Session id and the pack's
credit amount, which the webhook resolves from Stripe's own line items.
"""

from __future__ import annotations

import hmac
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel

from quantum_backend_v2.api.deps.auth import CurrentUser
from quantum_backend_v2.api.errors.models import ErrorCode, PlatformException, conflict
from quantum_backend_v2.payments.credits import CreditPurchase, record_credit_purchase
from quantum_backend_v2.payments.errors import IdempotencyConflictError
from quantum_backend_v2.payments.ledger import LedgerService
from quantum_backend_v2.payments.models import CreditBalance

_BILLING_SECRET_HEADER = "X-Billing-Internal-Secret"


class CreditBalanceResponse(BaseModel):
    """The caller's balance and what a circuit job costs."""

    balance: CreditBalance
    circuit_job_cost: Decimal


class CreditPurchaseResponse(BaseModel):
    """Result of recording a paid credit pack."""

    idempotency_key: str
    created: bool
    balance: CreditBalance


def build_credits_router(
    *,
    ledger_service: LedgerService,
    circuit_job_cost: Decimal,
    billing_internal_secret: str | None = None,
) -> APIRouter:
    """Build the credits router. The purchase route exists only when a secret is set."""
    router = APIRouter(prefix="/api/v1", tags=["credits"])

    @router.get(
        "/credits/balance",
        response_model=CreditBalanceResponse,
        summary="Your credit balance, derived from the ledger",
    )
    async def get_balance(current_user: CurrentUser) -> CreditBalanceResponse:
        return CreditBalanceResponse(
            balance=await ledger_service.balance(current_user.user_id),
            circuit_job_cost=circuit_job_cost,
        )

    if billing_internal_secret is not None:

        async def require_billing_secret(
            supplied: Annotated[str | None, Header(alias=_BILLING_SECRET_HEADER)] = None,
        ) -> None:
            if supplied is None or not hmac.compare_digest(supplied, billing_internal_secret):
                raise PlatformException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    error=ErrorCode.UNAUTHORIZED,
                    message="Invalid billing credentials.",
                )

        @router.post(
            "/internal/billing/credit-purchases",
            response_model=CreditPurchaseResponse,
            include_in_schema=False,
        )
        async def record_purchase(
            body: CreditPurchase,
            _: None = Depends(require_billing_secret),
        ) -> CreditPurchaseResponse:
            try:
                result = await record_credit_purchase(ledger_service, body)
            except IdempotencyConflictError as exc:
                raise conflict(str(exc)) from None
            return CreditPurchaseResponse(
                idempotency_key=result.event.idempotency_key,
                created=result.created,
                balance=await ledger_service.balance(body.account_id),
            )

    return router
