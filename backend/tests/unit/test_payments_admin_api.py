"""HTTP contract of the admin payments router, without a database (#3)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from quantum_backend_v2.api.deps import auth
from quantum_backend_v2.api.errors import register_exception_handlers
from quantum_backend_v2.api.routers.payments_admin import build_payments_admin_router
from quantum_backend_v2.payments.errors import (
    InvalidStatusTransitionError,
    PaymentEventNotFoundError,
)
from quantum_backend_v2.payments.models import (
    CreditBalance,
    PaymentEvent,
    PaymentEventStatus,
    PaymentPurpose,
    PaymentRail,
    ReconciliationReport,
)

pytestmark = pytest.mark.anyio


def _event(key: str, status: PaymentEventStatus) -> PaymentEvent:
    return PaymentEvent(
        idempotency_key=key,
        rail=PaymentRail.ONCHAIN,
        purpose=PaymentPurpose.WORKER_PAYOUT,
        asset="USDC",
        amount=Decimal("12.5"),
        status=status,
    )


class FakeLedger:
    def __init__(self) -> None:
        self.events = {
            "payout:p1:f1": _event("payout:p1:f1", PaymentEventStatus.UNCERTAIN),
            "done": _event("done", PaymentEventStatus.FAILED),
        }
        self.reconcile_calls: list[dict[str, Any]] = []

    async def list_events(self, *, status: Any, job_id: Any, proposal_id: Any, limit: int):
        return [e for e in self.events.values() if status is None or e.status is status][:limit]

    async def get_event(self, key: str) -> PaymentEvent | None:
        return self.events.get(key)

    async def reconcile(self, key: str, **kwargs: Any) -> PaymentEvent:
        self.reconcile_calls.append({"key": key, **kwargs})
        event = self.events.get(key)
        if event is None:
            raise PaymentEventNotFoundError(key)
        if event.status is not PaymentEventStatus.UNCERTAIN:
            raise InvalidStatusTransitionError("already settled")
        return event.model_copy(update={"status": kwargs["outcome"]})

    async def run_reconciliation(self) -> ReconciliationReport:
        return ReconciliationReport(marked_uncertain=("stale-1",))

    async def balance(self, account_id: str) -> CreditBalance:
        return CreditBalance(account_id=account_id, available=Decimal("3"))


def _app(ledger: FakeLedger) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(build_payments_admin_router(ledger_service=ledger))  # type: ignore[arg-type]
    return app


def _client(ledger: FakeLedger) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app(ledger)), base_url="http://test")


async def test_every_endpoint_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_auth_required", True)
    monkeypatch.setattr(auth, "_allow_dev_bearer_tokens", True)
    developer = {"Authorization": "Bearer dev-someone"}
    requests = [
        ("GET", "/api/v1/admin/payments/events"),
        ("GET", "/api/v1/admin/payments/events/done"),
        ("POST", "/api/v1/admin/payments/events/done/reconcile"),
        ("POST", "/api/v1/admin/payments/reconciliation"),
        ("GET", "/api/v1/admin/payments/accounts/user-1/balance"),
    ]
    async with _client(FakeLedger()) as c:
        for method, path in requests:
            body = {"outcome": "failed", "reason": "x"} if method == "POST" else None
            assert (await c.request(method, path, json=body)).status_code == 401
            assert (await c.request(method, path, json=body, headers=developer)).status_code == 403


async def test_admin_lists_uncertain_events_and_reconciles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_auth_required", False)  # dev bypass user is an admin
    ledger = FakeLedger()
    async with _client(ledger) as c:
        listed = await c.get("/api/v1/admin/payments/events", params={"status": "uncertain"})
        assert listed.status_code == 200
        assert [e["idempotency_key"] for e in listed.json()] == ["payout:p1:f1"]
        assert listed.json()[0]["amount"] == "12.5"

        resolved = await c.post(
            "/api/v1/admin/payments/events/payout:p1:f1/reconcile",
            json={"outcome": "confirmed", "reason": "found on explorer", "external_ref": "0xabc"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "confirmed"
        call = ledger.reconcile_calls[0]
        assert call["actor"] == "dev-local"
        assert call["outcome"] is PaymentEventStatus.CONFIRMED

        assert (
            await c.post(
                "/api/v1/admin/payments/events/done/reconcile",
                json={"outcome": "confirmed", "reason": "x"},
            )
        ).status_code == 409
        assert (
            await c.post(
                "/api/v1/admin/payments/events/missing/reconcile",
                json={"outcome": "confirmed", "reason": "x"},
            )
        ).status_code == 404
        assert (await c.get("/api/v1/admin/payments/events/missing")).status_code == 404

        report = await c.post("/api/v1/admin/payments/reconciliation")
        assert report.json()["marked_uncertain"] == ["stale-1"]
        balance = await c.get("/api/v1/admin/payments/accounts/user-1/balance")
        assert balance.json()["available"] == "3"


async def test_reconcile_rejects_outcomes_other_than_confirmed_or_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_auth_required", False)
    async with _client(FakeLedger()) as c:
        response = await c.post(
            "/api/v1/admin/payments/events/payout:p1:f1/reconcile",
            json={"outcome": "pending", "reason": "retry it"},
        )
        assert response.status_code == 422


def test_router_exposes_no_way_to_write_ledger_entries() -> None:
    """The ledger can only grow through payments; the API has no entry writes."""
    router = build_payments_admin_router(ledger_service=FakeLedger())  # type: ignore[arg-type]
    writes = {
        (route.path, method)
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method in {"POST", "PUT", "PATCH", "DELETE"}
    }
    assert writes == {
        ("/api/v1/admin/payments/events/{idempotency_key}/reconcile", "POST"),
        ("/api/v1/admin/payments/reconciliation", "POST"),
    }
