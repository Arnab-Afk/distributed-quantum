"""Unit tests for payment-event transitions and ledger balance derivation (#3)."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from quantum_backend_v2.payments.models import (
    ALLOWED_TRANSITIONS,
    LedgerEntry,
    LedgerEntryType,
    PaymentEventStatus,
    derive_balance,
)


def _entry(entry_type: LedgerEntryType, amount: str, *, account: str = "acct-1") -> LedgerEntry:
    return LedgerEntry(
        entry_id=f"e-{random.random()}",
        idempotency_key=f"k-{random.random()}",
        account_id=account,
        entry_type=entry_type,
        amount=Decimal(amount),
    )


class TestStatusTransitions:
    def test_uncertain_never_returns_to_pending(self) -> None:
        assert PaymentEventStatus.PENDING not in ALLOWED_TRANSITIONS[PaymentEventStatus.UNCERTAIN]

    def test_failed_and_refunded_are_terminal(self) -> None:
        assert ALLOWED_TRANSITIONS[PaymentEventStatus.FAILED] == frozenset()
        assert ALLOWED_TRANSITIONS[PaymentEventStatus.REFUNDED] == frozenset()

    def test_only_confirmed_can_be_refunded(self) -> None:
        sources = {
            s for s, targets in ALLOWED_TRANSITIONS.items()
            if PaymentEventStatus.REFUNDED in targets
        }
        assert sources == {PaymentEventStatus.CONFIRMED}


class TestDeriveBalance:
    def test_empty_ledger_is_zero(self) -> None:
        balance = derive_balance("acct-1", [])
        assert balance.available == balance.held == balance.spent == Decimal("0")

    def test_hold_capture_release_flow(self) -> None:
        entries = [
            _entry(LedgerEntryType.CREDIT, "100"),
            _entry(LedgerEntryType.HOLD, "40"),
            _entry(LedgerEntryType.CAPTURE, "25"),
            _entry(LedgerEntryType.RELEASE, "15"),
        ]
        balance = derive_balance("acct-1", entries)
        assert balance.available == Decimal("75")
        assert balance.held == Decimal("0")
        assert balance.spent == Decimal("25")

    def test_rejects_entries_from_another_account(self) -> None:
        with pytest.raises(ValueError):
            derive_balance("acct-1", [_entry(LedgerEntryType.CREDIT, "1", account="acct-2")])

    @pytest.mark.parametrize("seed", range(25))
    def test_sum_invariant_under_random_valid_operations(self, seed: int) -> None:
        """Property: credits always equal available + held + spent, nothing goes negative."""
        rng = random.Random(seed)
        entries: list[LedgerEntry] = []
        holds: list[Decimal] = []
        available = credited = Decimal("0")
        for _ in range(200):
            op = rng.choice(["credit", "hold", "capture", "release"])
            amount = Decimal(rng.randint(1, 5000)) / Decimal(100)
            if op == "credit":
                entries.append(_entry(LedgerEntryType.CREDIT, str(amount)))
                available += amount
                credited += amount
            elif op == "hold" and amount <= available:
                entries.append(_entry(LedgerEntryType.HOLD, str(amount)))
                available -= amount
                holds.append(amount)
            elif op in ("capture", "release") and holds:
                index = rng.randrange(len(holds))
                part = min(amount, holds[index])
                kind = LedgerEntryType.CAPTURE if op == "capture" else LedgerEntryType.RELEASE
                entries.append(_entry(kind, str(part)))
                holds[index] -= part
                if op == "release":
                    available += part
                if holds[index] == 0:
                    holds.pop(index)

            balance = derive_balance("acct-1", entries)
            assert balance.available == available
            assert balance.held == sum(holds, Decimal("0"))
            assert balance.available + balance.held + balance.spent == credited
            assert balance.available >= 0 and balance.held >= 0
