from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from bson import Decimal128
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import services.agentkit_service as wallet_module
import services.marketplace_service as marketplace_module
from quantum_backend_v2.api.deps.auth import require_authenticated
from quantum_backend_v2.api.deps.marketplace import get_marketplace_service
from quantum_backend_v2.api.deps.wallet import get_wallet_service
from quantum_backend_v2.api.errors.models import register_exception_handlers
from quantum_backend_v2.chains.loader import load_chain_registry

ADDRESS = "0x" + "11" * 20
DESTINATION = "0x" + "22" * 20
pytestmark = pytest.mark.anyio


@pytest.fixture
def boundary(monkeypatch):
    db = MagicMock()
    now = datetime.now(timezone.utc)
    worker = dict(
        worker_id="worker",
        wallet_address=DESTINATION,
        pricing={"hadamard": 0.1},
        performance_tier="bronze",
        reputation_score=50.0,
        total_earned=Decimal128("2"),
        jobs_completed=1,
        is_active=True,
        published_at=now,
        updated_at=now,
    )
    db.worker_pricing.find_one = AsyncMock(return_value=worker)
    db.worker_pricing.update_one = AsyncMock()
    db.worker_pricing.find.return_value.sort.return_value.__aiter__.return_value = [worker]
    db.wallets.find_one = AsyncMock(
        return_value={"default_address": ADDRESS, "network": "base-sepolia"}
    )
    for module in (wallet_module, marketplace_module):
        motor = MagicMock()
        motor.return_value.__getitem__.return_value = db
        monkeypatch.setattr(module, "AsyncIOMotorClient", motor)
    provider = Mock()
    monkeypatch.setattr(wallet_module, "CdpEvmWalletProvider", provider)
    return SimpleNamespace(db=db, provider=provider)


def make_app(network="base-sepolia"):
    from api.v1.marketplace import router

    app = FastAPI()
    app.state.chain_registry = load_chain_registry()
    app.state.wallet_chain_id = app.state.chain_registry.resolve(network).chain_id
    app.dependency_overrides[require_authenticated] = lambda: SimpleNamespace(user_id="worker")
    register_exception_handlers(app)
    app.include_router(router)
    return app


async def resolve_service(app):
    request = Request({"type": "http", "app": app})
    wallet = await get_wallet_service(request)
    return await get_marketplace_service(request, wallet)


def test_worker_routes_share_app_configuration(boundary, monkeypatch):
    monkeypatch.setenv("NETWORK", "invalid-process-network")
    app = make_app()
    assert not hasattr(app.state, "marketplace_service")
    with TestClient(app) as client:
        workers = client.get("/api/v1/marketplace/workers")
        assert workers.status_code == 200, workers.text
        service = app.state.marketplace_service
        earnings = client.get("/api/v1/marketplace/worker/worker/earnings")
        assert earnings.status_code == 200, earnings.text
        assert earnings.json()["total_earned"] == 2.0
        registration = client.post(
            "/api/v1/marketplace/register-pricing",
            json={
                "worker_id": "worker",
                "pricing": {"hadamard": 0.2},
                "performance_tier": "silver",
            },
        )
        assert registration.status_code == 201, registration.text
        assert registration.json()["pricing"] == {"hadamard": 0.2}
        service.estimate_job_cost = AsyncMock(
            return_value={
                "total_usdc": 0.1,
                "breakdown": [],
                "operation_counts": {"hadamard": 1},
                "workers_required": ["worker"],
            }
        )
        circuit = 'OPENQASM 2.0; include "qelib1.inc"; qreg q[1]; h q[0];'
        estimate = client.post("/api/v1/marketplace/estimate-cost", json={"circuit": circuit})
        assert estimate.status_code == 200, estimate.text
        service.estimate_job_cost.assert_awaited_once_with(circuit=circuit)
        assert app.state.marketplace_service is service
        assert service.agentkit is app.state.wallet_service
        assert service.agentkit.registry is app.state.chain_registry
    boundary.provider.assert_not_called()


async def test_marketplace_isolated_between_apps(boundary):
    base = await resolve_service(make_app())
    ethereum = await resolve_service(make_app("ethereum-sepolia"))
    assert base is not ethereum
    assert base.agentkit.chain.chain_id == "eip155:84532"
    assert ethereum.agentkit.chain.chain_id == "eip155:11155111"


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/workers", "GET", None),
        ("/worker/worker/earnings", "GET", None),
        ("/register-pricing", "POST", {"worker_id": "worker", "pricing": {"hadamard": 0.1}}),
        ("/estimate-cost", "POST", {"circuit": "OPENQASM 2.0; qreg q[1]; h q[0];"}),
    ],
)
def test_auth_failure_does_not_create_marketplace(boundary, path, method, body):
    app = make_app()

    def deny():
        raise HTTPException(status_code=401)

    app.dependency_overrides[require_authenticated] = deny
    with TestClient(app) as client:
        assert client.request(method, "/api/v1/marketplace" + path, json=body).status_code == 401
    assert not hasattr(app.state, "marketplace_service")
    assert not hasattr(app.state, "wallet_service")


async def test_payout_uses_shared_wallet_and_updates_earnings(boundary):
    app = make_app()
    service = await resolve_service(app)
    wallet = await get_wallet_service(Request({"type": "http", "app": app}))
    wallet.transfer_usdc = AsyncMock(
        return_value={"transaction_hash": "tx", "basescan_url": "https://explorer.example/tx/tx"}
    )
    service._create_notification = AsyncMock()
    result = await service.distribute_payment_to_workers(
        "job", [{"worker_id": "worker", "amount": "1.25"}], ADDRESS
    )
    wallet.transfer_usdc.assert_awaited_once_with(
        from_address=ADDRESS,
        to_address=DESTINATION,
        amount=Decimal("1.25"),
        metadata={"type": "worker_payment", "job_id": "job", "worker_id": "worker"},
    )
    assert result["successful_payments"] == 1
    assert result["total_distributed"] == 1.25
    update = boundary.db.worker_pricing.update_one.call_args.args[1]
    assert update["$set"]["total_earned"] == Decimal128("3.25")
    assert update["$inc"]["jobs_completed"] == 1
    service._create_notification.assert_awaited_once()


@pytest.mark.parametrize(
    "network,stored", [("ethereum-sepolia", "base-sepolia"), ("base-sepolia", "ethereum-sepolia")]
)
async def test_payout_network_failure_keeps_earnings_unchanged(boundary, network, stored):
    boundary.db.wallets.find_one.return_value["network"] = stored
    service = await resolve_service(make_app(network))
    service._create_notification = AsyncMock()
    result = await service.distribute_payment_to_workers(
        "job", [{"worker_id": "worker", "amount": "1"}], ADDRESS
    )
    assert result["failed_payments"] == 1
    assert result["successful_payments"] == 0
    error = result["payment_details"][0]["error"]
    assert "unavailable" in error or "does not match" in error
    boundary.provider.assert_not_called()
    boundary.db.worker_pricing.update_one.assert_not_awaited()
    service._create_notification.assert_not_awaited()
