from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from bson import Decimal128
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.agentkit_service as wallet_module
import services.ai_agent_service as agents_module
import services.proposal_service as proposals_module
from quantum_backend_v2.api.deps.research import AIAgentServiceDep, ProposalServiceDep
from quantum_backend_v2.chains.adapter import UnsupportedOperationError
from quantum_backend_v2.chains.loader import load_chain_registry

ADDRESS = "0x" + "11" * 20
DESTINATION = "0x" + "22" * 20
pytestmark = pytest.mark.anyio


@pytest.fixture
def research_boundary(monkeypatch):
    db = MagicMock()
    db.wallets.find_one = AsyncMock(
        return_value={"default_address": ADDRESS, "network": "base-sepolia"}
    )
    db.research_proposals.find_one = AsyncMock(
        return_value={
            "proposal_id": "proposal",
            "researcher_wallet": DESTINATION,
            "status": "active",
            "deadline": datetime.now(timezone.utc) + timedelta(days=1),
            "budget_raised": Decimal128("2"),
            "budget_required": Decimal128("100"),
            "funding_threshold": Decimal128("100"),
            "fragments": [{"fragment_id": "fragment", "budget": "1", "claimed_by": "researcher"}],
        }
    )
    db.ai_agents.find_one = AsyncMock(
        return_value={
            "agent_id": "agent",
            "wallet_address": ADDRESS,
            "total_spent": Decimal128("0"),
            "config": {"max_per_proposal": Decimal128("5")},
        }
    )
    agent = db.ai_agents.find_one.return_value
    db.ai_agents.find_one.side_effect = lambda query, **kwargs: (
        None if "owner_id" in query else agent
    )
    for collection in (db.wallets, db.research_proposals, db.ai_agents, db.payments):
        collection.insert_one = AsyncMock()
        collection.update_one = AsyncMock()
    for module in (agents_module, proposals_module, wallet_module):
        motor = MagicMock()
        motor.return_value.__getitem__.return_value = db
        monkeypatch.setattr(module, "AsyncIOMotorClient", motor)
    monkeypatch.setattr(proposals_module.boto3, "client", Mock())
    ledger = AsyncMock()
    ledger.record_event.return_value = SimpleNamespace(created=True)
    monkeypatch.setattr(proposals_module, "LedgerService", Mock(return_value=ledger))
    provider = Mock()
    monkeypatch.setattr(wallet_module, "CdpEvmWalletProvider", provider)

    def document(**values):
        values.setdefault("created_at", datetime.now(timezone.utc))
        return SimpleNamespace(**values, model_dump=lambda: values)

    monkeypatch.setattr(agents_module, "AIAgentDocument", document)
    monkeypatch.setattr(proposals_module, "PaymentDocument", document)
    return SimpleNamespace(db=db, provider=provider, ledger=ledger)


def make_app(network):
    app = FastAPI()
    app.state.chain_registry = load_chain_registry()
    app.state.wallet_chain_id = app.state.chain_registry.resolve(network).chain_id

    @app.get("/services")
    async def services(agents: AIAgentServiceDep, proposals: ProposalServiceDep):
        return {
            "chain": proposals.agentkit.chain.chain_id,
            "shared": proposals.agentkit is agents.agentkit,
            "shared_agents": proposals._ai_agent_service is agents,
        }

    return app


def test_dependencies_share_wallet_and_isolate_apps(research_boundary, monkeypatch):
    monkeypatch.setenv("NETWORK", "invalid-process-network")
    base = make_app("base-sepolia")
    ethereum = make_app("ethereum-sepolia")
    assert not hasattr(base.state, "proposal_service")
    with TestClient(base) as a, TestClient(ethereum) as b:
        assert a.get("/services").json() == {
            "chain": "eip155:84532",
            "shared": True,
            "shared_agents": True,
        }
        service = base.state.proposal_service
        assert a.get("/services").status_code == 200
        assert base.state.proposal_service is service
        assert b.get("/services").json()["chain"] == "eip155:11155111"
        assert ethereum.state.ai_agent_service is not base.state.ai_agent_service
        assert service.agentkit is base.state.wallet_service


@pytest.mark.parametrize("operation", ["fund", "release", "fragment", "agent_fund"])
@pytest.mark.parametrize(
    "network,stored", [("ethereum-sepolia", "base-sepolia"), ("base-sepolia", "ethereum-sepolia")]
)
async def test_research_flows_reject_network_before_provider(
    research_boundary, network, stored, operation
):
    wallet = wallet_module.AgentKitService(registry=load_chain_registry(), network=network)
    research_boundary.db.wallets.find_one.return_value["network"] = stored
    proposals = proposals_module.ProposalService(agentkit_service=wallet)
    agents = agents_module.AIAgentService(agentkit_service=wallet)
    agents._get_daily_remaining = AsyncMock(return_value=Decimal("5"))
    calls = {
        "fund": lambda: proposals.fund_proposal("proposal", "user", "user", Decimal("1")),
        "release": lambda: proposals._release_all_escrow("proposal"),
        "fragment": lambda: proposals._pay_fragment_researcher("proposal", "fragment"),
        "agent_fund": lambda: agents._execute_funding("agent", "proposal", Decimal("1")),
    }
    with pytest.raises((ValueError, UnsupportedOperationError), match="unavailable|does not match"):
        await calls[operation]()
    research_boundary.provider.assert_not_called()
    research_boundary.db.research_proposals.update_one.assert_not_awaited()
    research_boundary.db.ai_agents.update_one.assert_not_awaited()
    research_boundary.db.payments.insert_one.assert_not_awaited()


async def test_agent_creation_and_funding_use_injected_wallet(research_boundary, monkeypatch):
    wallet = Mock()
    wallet.create_wallet = AsyncMock(return_value={"wallet_address": ADDRESS})
    wallet.transfer_usdc = AsyncMock(return_value={"transaction_hash": "tx"})
    monkeypatch.setattr(
        wallet_module, "AgentKitService", Mock(side_effect=AssertionError("unexpected wallet"))
    )
    agents = agents_module.AIAgentService(agentkit_service=wallet)
    result = await agents.create_agent(
        "owner",
        "agent",
        {
            "auto_fund": True,
            "research_interests": ["quantum"],
            "min_reputation_threshold": 50,
            "max_per_proposal": "5",
            "daily_budget": "10",
        },
    )
    wallet.create_wallet.assert_awaited_once_with(entity_id=result["agent_id"], entity_type="agent")
    agents._get_daily_remaining = AsyncMock(return_value=Decimal("10"))
    await agents._execute_funding("agent", "proposal", Decimal("1"))
    wallet.transfer_usdc.assert_awaited_once_with(
        from_address=ADDRESS,
        to_address=DESTINATION,
        amount=Decimal("1"),
        metadata={"type": "research_funding", "proposal_id": "proposal", "agent_id": "agent"},
    )
    research_boundary.db.ai_agents.update_one.assert_awaited_once()


@pytest.mark.parametrize("operation", ["fund", "release", "fragment"])
async def test_proposal_escrow_uses_injected_wallet(research_boundary, monkeypatch, operation):
    wallet = Mock()
    wallet.aave_supply = AsyncMock(return_value={"transaction_hash": "tx"})
    wallet.aave_withdraw = AsyncMock(return_value={"transaction_hash": "tx"})
    monkeypatch.setattr(
        wallet_module, "AgentKitService", Mock(side_effect=AssertionError("unexpected wallet"))
    )
    proposals = proposals_module.ProposalService(
        agentkit_service=wallet, notification_service=AsyncMock()
    )
    if operation == "fund":
        await proposals.fund_proposal("proposal", "user", "user", Decimal("1"))
        wallet.aave_supply.assert_awaited_once_with(
            wallet_address=ADDRESS, amount=Decimal("1"), on_behalf_of=DESTINATION
        )
    elif operation == "release":
        await proposals._release_all_escrow("proposal")
        wallet.aave_withdraw.assert_awaited_once_with(
            wallet_address=DESTINATION, amount=Decimal("2"), to=DESTINATION
        )
    else:
        await proposals._pay_fragment_researcher("proposal", "fragment")
        wallet.aave_withdraw.assert_awaited_once_with(
            wallet_address=DESTINATION, amount=Decimal("1"), to=ADDRESS
        )
    research_boundary.db.payments.insert_one.assert_awaited_once()


async def test_standalone_proposal_reuses_wallet_across_broadcasts(research_boundary, monkeypatch):
    import asyncio

    wallet = Mock()
    factory = Mock(return_value=wallet)
    monkeypatch.setattr(wallet_module, "AgentKitService", factory)
    proposals = proposals_module.ProposalService()
    tasks = []
    create_task = asyncio.create_task
    monkeypatch.setattr(asyncio, "create_task", lambda coro: tasks.append(create_task(coro)))
    analyze = AsyncMock()
    monkeypatch.setattr(agents_module.AIAgentService, "analyze_proposal", analyze)
    research_boundary.db.ai_agents.find.return_value.to_list = AsyncMock(
        return_value=[{"agent_id": "agent"}]
    )
    for _ in range(2):
        await proposals._broadcast_new_proposal({"proposal_id": "proposal"})
    await asyncio.gather(*tasks)
    assert proposals._ai_agent_service.agentkit is proposals.agentkit is wallet
    factory.assert_called_once_with()
    assert analyze.await_count == 2


def test_agent_route_uses_application_network(research_boundary, monkeypatch):
    from api.v1.agents import router
    from quantum_backend_v2.api.deps.auth import require_authenticated
    from quantum_backend_v2.api.errors.models import register_exception_handlers

    app = make_app("ethereum-sepolia")
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[require_authenticated] = lambda: SimpleNamespace(user_id="owner")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agents",
            json={
                "agent_name": "research agent",
                "config": {
                    "auto_fund": True,
                    "max_per_proposal": "1",
                    "daily_budget": "2",
                    "research_interests": ["quantum"],
                    "min_reputation_threshold": 50,
                },
            },
        )
    assert response.status_code == 400, response.text
    assert "unavailable" in response.text
    assert app.state.ai_agent_service.agentkit is app.state.wallet_service
    research_boundary.provider.assert_not_called()
    research_boundary.db.ai_agents.insert_one.assert_not_awaited()


def test_proposal_route_uses_registry_explorer(research_boundary):
    from api.v1.proposals import router
    from quantum_backend_v2.api.deps.auth import require_authenticated
    from quantum_backend_v2.chains.models import ChainRegistry

    app = make_app("base-sepolia")
    data = app.state.chain_registry.model_dump()
    data["chains"][0]["explorers"]["transaction"] = "https://research.example/tx/{tx_hash}"
    app.state.chain_registry = ChainRegistry.model_validate(data)
    app.include_router(router)
    app.dependency_overrides[require_authenticated] = lambda: SimpleNamespace(user_id="owner")
    tx = "0x" + "ab" * 32
    with TestClient(app) as client:
        client.get("/services")
        proposals = app.state.proposal_service
        proposals._notification_service = AsyncMock()
        app.state.wallet_service.aave_supply = AsyncMock(return_value={"transaction_hash": tx})
        response = client.post("/api/v1/proposals/proposal/fund", json={"amount": "1"})
    assert response.status_code == 201, response.text
    assert response.json()["basescan_url"] == "https://research.example/tx/" + tx
    app.state.wallet_service.aave_supply.assert_awaited_once_with(
        wallet_address=ADDRESS, amount=Decimal("1"), on_behalf_of=DESTINATION
    )


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/v1/agents",
            {
                "agent_name": "agent",
                "config": {
                    "auto_fund": True,
                    "max_per_proposal": "1",
                    "daily_budget": "2",
                    "research_interests": [],
                    "min_reputation_threshold": 0,
                },
            },
        ),
        ("/api/v1/proposals/proposal/fund", {"amount": "1"}),
    ],
)
def test_research_auth_failure_does_not_initialize_services(research_boundary, path, payload):
    from fastapi import HTTPException

    from api.v1 import agents, proposals
    from quantum_backend_v2.api.deps.auth import require_authenticated

    def deny():
        raise HTTPException(status_code=401)

    app = make_app("base-sepolia")
    app.include_router(agents.router)
    app.include_router(proposals.router)
    app.dependency_overrides[require_authenticated] = deny
    with TestClient(app) as client:
        assert client.post(path, json=payload).status_code == 401
    for name in ("wallet_service", "ai_agent_service", "proposal_service"):
        assert not hasattr(app.state, name)
    research_boundary.provider.assert_not_called()


@pytest.mark.parametrize("subject", ["betterauth|owner", "dev-user"])
def test_storage_exports_keep_auth_and_use_app_service(research_boundary, monkeypatch, subject):
    from api.v1.agents import router
    from quantum_backend_v2.api.deps.auth import require_authenticated
    from quantum_backend_v2.api.errors.models import register_exception_handlers
    from services import toju_storage

    storage = AsyncMock()
    storage.list.return_value = []
    storage.decide.return_value = {"status": "cancelled"}
    factory = Mock(return_value=storage)
    monkeypatch.setattr(toju_storage, "TojuStorage", factory)
    app = make_app("base-sepolia")
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[require_authenticated] = lambda: SimpleNamespace(
        user_id="owner", external_subject=subject
    )
    with TestClient(app) as client:
        responses = [
            client.get("/api/v1/agents/agent/exports?session_id=session"),
            client.post(
                "/api/v1/agents/agent/exports/proposal",
                json={"session_id": "session", "decision": "cancel", "sha256": "a" * 64},
            ),
        ]
    if subject.startswith("betterauth|"):
        assert all(r.status_code == 200 for r in responses)
        assert factory.call_count == 2
        factory.assert_called_with(app.state.ai_agent_service.db)
        storage.list.assert_awaited_once_with("owner", "agent", "session")
        storage.decide.assert_awaited_once_with(
            "owner", "agent", "session", "proposal", "cancel", "a" * 64
        )
    else:
        assert all(r.status_code == 401 for r in responses)
        factory.assert_not_called()


async def test_existing_agent_reuse_does_not_create_wallet(research_boundary):
    existing = {
        "agent_id": "existing",
        "owner_id": "owner",
        "agent_name": "agent",
        "wallet_address": ADDRESS,
        "created_at": datetime.now(timezone.utc),
    }
    research_boundary.db.ai_agents.find_one.side_effect = None
    research_boundary.db.ai_agents.find_one.return_value = existing
    wallet = Mock(create_wallet=AsyncMock())
    service = agents_module.AIAgentService(agentkit_service=wallet)
    result = await service.create_agent(
        "owner",
        "agent",
        {
            "auto_fund": True,
            "max_per_proposal": "1",
            "daily_budget": "2",
            "research_interests": [],
            "min_reputation_threshold": 0,
        },
    )
    assert result["agent_id"] == "existing"
    wallet.create_wallet.assert_not_awaited()
    research_boundary.db.ai_agents.insert_one.assert_not_awaited()
