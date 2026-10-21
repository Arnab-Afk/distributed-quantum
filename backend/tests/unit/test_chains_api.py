from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantum_backend_v2.api.routers.chains import build_chains_router
from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.models import ChainRegistry


def make_app(registry):
    app = FastAPI()
    app.include_router(build_chains_router(registry=registry))
    return app


def test_public_chains_without_wallet_credentials(monkeypatch):
    for name in ("CDP_API_KEY_ID", "CDP_API_KEY_SECRET", "CDP_WALLET_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QB2_BASE_SEPOLIA_RPC_URL", "https://user:TOP_SECRET@rpc.example/key")
    with TestClient(make_app(load_chain_registry())) as client:
        response = client.get("/api/v1/chains")
        schema = client.get("/openapi.json").json()
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"default_chain_id", "chains"}
    assert body["default_chain_id"] == "eip155:84532"
    assert [c["chain_id"] for c in body["chains"]] == ["eip155:84532", "eip155:11155111"]
    for chain in body["chains"]:
        assert set(chain) == {
            "chain_id",
            "family",
            "display_name",
            "testnet",
            "native_token",
            "stablecoin",
            "explorers",
            "capabilities",
        }
        assert set(chain["native_token"]) == {"symbol", "decimals"}
        assert set(chain["stablecoin"]) == {"symbol", "decimals", "address"}
        assert chain["capabilities"] == ["explorer_url"]
    for private in ("TOP_SECRET", "rpc_env_var", "QB2_BASE_SEPOLIA_RPC_URL", "provider_aliases"):
        assert private not in response.text
        assert private not in str(schema)
    assert not schema["paths"]["/api/v1/chains"]["get"].get("security")


def test_disabled_networks_are_not_advertised():
    data = load_chain_registry().model_dump()
    data["chains"][1]["enabled"] = False
    with TestClient(make_app(ChainRegistry.model_validate(data))) as client:
        response = client.get("/api/v1/chains")
    assert len(response.json()["chains"]) == 1


def test_registries_are_scoped_to_each_app():
    original = load_chain_registry()
    data = original.model_dump()
    data["default_chain_id"] = "eip155:11155111"
    with (
        TestClient(make_app(original)) as base,
        TestClient(make_app(ChainRegistry.model_validate(data))) as ethereum,
    ):
        assert ethereum.get("/api/v1/chains").json()["default_chain_id"] == "eip155:11155111"
        assert base.get("/api/v1/chains").json()["default_chain_id"] == "eip155:84532"
