"""
Payment-event helpers for the legacy AgentKit payment paths (#3).

These paths move real funds, so the helpers follow two rules:
- Record the event before sending, and never send again for a key that
  already has a live or uncertain event.
- After funds have moved, a failure to update the event is logged, never
  raised: the caller's response must not change. The reconciliation sweep
  flags any event left pending.
"""

import logging
from decimal import Decimal
from typing import Any

from quantum_backend_v2.payments.errors import PaymentLedgerError
from quantum_backend_v2.payments.ledger import LedgerService
from quantum_backend_v2.payments.models import (
    PaymentEventStatus,
    PaymentPurpose,
    PaymentRail,
)

logger = logging.getLogger(__name__)


def chain_id_of(agentkit_service: Any) -> str | None:
    """CAIP-2 chain id of an AgentKitService, or None when it is unavailable."""
    chain_id = getattr(getattr(agentkit_service, "chain", None), "chain_id", None)
    return chain_id if isinstance(chain_id, str) else None


async def begin_payout(
    ledger: LedgerService,
    key_base: str,
    *,
    purpose: PaymentPurpose,
    amount: Decimal,
    **fields: Any,
) -> str:
    """
    Record a pending on-chain payout and return its idempotency key.

    Each attempt is keyed ``<key_base>:<n>``. A new attempt is only allowed
    after every earlier one definitely failed.

    Raises:
        PaymentUncertainError: An earlier attempt has an unknown outcome
        ValueError: An earlier attempt is pending or already paid
    """
    attempt = 1
    while True:
        key = f"{key_base}:{attempt}"
        result = await ledger.record_event(
            idempotency_key=key,
            rail=PaymentRail.ONCHAIN,
            purpose=purpose,
            amount=amount,
            **fields,
        )
        if result.created:
            return key
        if result.event.status is PaymentEventStatus.FAILED:
            attempt += 1
            continue
        raise ValueError(
            f"Payout {key} is already {result.event.status.value}; refusing to pay again"
        )


async def settle_failed_send(ledger: LedgerService, key: str, error: Exception) -> None:
    """
    Record why a send failed. Never raises.

    A ValueError is raised by validation before anything is sent, so the
    payment definitely failed. Any other error may have happened after the
    transaction was broadcast, so the outcome is uncertain.
    """
    reason = f"{type(error).__name__}: {error}"[:500]
    try:
        if isinstance(error, ValueError):
            await ledger.fail(key, reason=reason)
        else:
            await ledger.mark_uncertain(key, reason=reason)
    except Exception:
        logger.exception(f"Failed to record the outcome of payment {key}")


async def confirm_quietly(ledger: LedgerService, key: str, external_ref: str) -> None:
    """Confirm a payment whose funds already moved. Never raises."""
    try:
        await ledger.confirm(key, external_ref=external_ref)
    except Exception:
        logger.exception(f"Failed to confirm payment {key} ({external_ref})")


async def record_settled_quietly(ledger: LedgerService, **fields: Any) -> None:
    """Record a payment that has already settled on its rail. Never raises."""
    try:
        await ledger.record_event(status=PaymentEventStatus.CONFIRMED, **fields)
    except PaymentLedgerError:
        logger.exception(f"Payment event {fields.get('idempotency_key')} conflicts")
    except Exception:
        logger.exception(f"Failed to record payment {fields.get('idempotency_key')}")
