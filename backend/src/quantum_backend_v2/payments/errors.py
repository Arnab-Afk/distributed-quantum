"""Domain errors raised by the payment ledger."""

from __future__ import annotations


class PaymentLedgerError(Exception):
    """Base class for payment ledger errors."""


class IdempotencyConflictError(PaymentLedgerError):
    """An idempotency key was reused for a different payment or entry."""


class PaymentEventNotFoundError(PaymentLedgerError):
    """No payment event exists for the idempotency key."""


class InvalidStatusTransitionError(PaymentLedgerError):
    """The event cannot move from its current status to the requested one."""


class PaymentUncertainError(PaymentLedgerError):
    """The previous attempt has an unknown outcome; it must be reconciled, not retried."""


class InsufficientCreditError(PaymentLedgerError):
    """The account does not have enough available credit."""


class HoldNotFoundError(PaymentLedgerError):
    """No open hold exists with this id."""


class HoldExceededError(PaymentLedgerError):
    """A capture or release asked for more than the hold has left."""
