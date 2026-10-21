"""Exercise the real app factory with external services mocked."""

from __future__ import annotations

import importlib
import sys
from importlib.resources import files
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from quantum_backend_v2.chains.loader import RegistryConfigurationError


@pytest.fixture
def application_factory(monkeypatch):
    # Mock the peer boundary before importing bootstrap so these tests never load
    # native networking dependencies or create a real peer host.
    peers = ModuleType("quantum_backend_v2.libp2p")
    peers.__path__ = [str(files("quantum_backend_v2").joinpath("libp2p"))]
    discovery = ModuleType("quantum_backend_v2.discovery.service")
    wallet = ModuleType("services.agentkit_service")
    wallet.AgentKitService = Mock
    import boto3
    import motor.motor_asyncio

    monkeypatch.setattr(boto3, "client", Mock())
    monkeypatch.setattr(motor.motor_asyncio, "AsyncIOMotorClient", MagicMock())
    original_modules = set(sys.modules)
    monkeypatch.setitem(sys.modules, "quantum_backend_v2.libp2p", peers)
    monkeypatch.setitem(sys.modules, "quantum_backend_v2.discovery.service", discovery)
    monkeypatch.setitem(sys.modules, "services.agentkit_service", wallet)
    try:
        models = importlib.import_module("quantum_backend_v2.libp2p.models")
        peers.Libp2pBootstrapPlan = models.Libp2pBootstrapPlan
        peers.Libp2pRuntimeSummary = models.Libp2pRuntimeSummary
        peers.Libp2pRuntime = Mock
        peers.create_libp2p_bootstrap_plan = Mock()
        peers.create_real_libp2p_runtime = Mock()
        discovery.DiscoveryService = Mock
        discovery.build_discovery_service = Mock(
            return_value=SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
        )
        bootstrap = importlib.import_module("quantum_backend_v2.bootstrap.application")
        persistence = Mock(
            return_value=SimpleNamespace(mongodb=None, startup=AsyncMock(), shutdown=AsyncMock())
        )
        recovery = Mock(
            return_value=SimpleNamespace(
                recover_open_reservations=AsyncMock(return_value=[]),
                recover_in_flight_executions=AsyncMock(return_value=[]),
            )
        )
        with (
            patch.object(bootstrap, "create_persistence_runtime", persistence),
            patch.object(bootstrap, "RuntimeRecoveryService", recovery),
            patch.object(bootstrap, "create_libp2p_plan", peers.create_libp2p_bootstrap_plan),
            patch.object(bootstrap, "create_libp2p_runtime", peers.create_real_libp2p_runtime),
            patch.object(bootstrap, "build_discovery_service", discovery.build_discovery_service),
        ):
            yield bootstrap.create_application, persistence, peers.create_real_libp2p_runtime
    finally:
        # Unload only newly imported application modules. Native libraries such as
        # NumPy cannot safely be unloaded and reimported between test cases.
        for name in set(sys.modules) - original_modules:
            if name in {"api", "services"} or name.startswith(
                ("quantum_backend_v2.", "api.", "services.")
            ):
                module = sys.modules.pop(name)
                parent_name, _, attribute = name.rpartition(".")
                parent = sys.modules.get(parent_name)
                if parent is not None and getattr(parent, attribute, None) is module:
                    delattr(parent, attribute)


def test_application_registers_public_chains_and_honors_override(application_factory, tmp_path):
    create_application, _, _ = application_factory
    registry = tmp_path / "chains.toml"
    registry.write_text(
        files("quantum_backend_v2.chains")
        .joinpath("registry.toml")
        .read_text()
        .replace('default_chain_id = "eip155:84532"', 'default_chain_id = "eip155:11155111"')
    )
    env = {"QB2_AUTH_REQUIRED": "true", "QB2_ENVIRONMENT": "test"}
    with (
        TestClient(create_application(env=env)) as default,
        TestClient(
            create_application(env={**env, "QB2_CHAIN_REGISTRY_PATH": str(registry)})
        ) as overridden,
    ):
        for client, chain_id in ((default, "eip155:84532"), (overridden, "eip155:11155111")):
            response = client.get("/api/v1/chains")
            assert response.status_code == 200
            assert response.json()["default_chain_id"] == chain_id
            assert len(response.json()["chains"]) == 2


@pytest.mark.parametrize("contents", ['default_chain_id = "eip155:1"', "chains = ["])
def test_invalid_registry_stops_bootstrap_before_runtime_creation(
    application_factory, tmp_path, contents
):
    create_application, persistence, peers = application_factory
    path = tmp_path / "invalid.toml"
    path.write_text(contents)
    with pytest.raises(RegistryConfigurationError):
        create_application(env={"QB2_CHAIN_REGISTRY_PATH": str(path)})
    persistence.assert_not_called()
    peers.assert_not_called()
