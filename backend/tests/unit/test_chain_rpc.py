from __future__ import annotations

import pytest

from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.models import ChainSpec
from quantum_backend_v2.chains.rpc import RpcConfigurationError, resolve_rpc_url


@pytest.mark.parametrize(
    "network,url",
    [
        ("base-sepolia", "https://sepolia.base.org"),
        ("ethereum-sepolia", "https://sepolia.drpc.org"),
    ],
)
def test_public_rpc_is_the_default(network, url):
    # Same endpoints AgentKit used before the registry, so behaviour is unchanged.
    assert resolve_rpc_url(load_chain_registry().resolve(network), {}) == url


@pytest.mark.parametrize(
    "override",
    ["https://base-sepolia.g.alchemy.com/v2/KEY", "http://127.0.0.1:8545", "http://localhost:8545"],
)
def test_environment_overrides_the_public_rpc(override):
    chain = load_chain_registry().resolve("base-sepolia")
    assert resolve_rpc_url(chain, {"QB2_BASE_SEPOLIA_RPC_URL": f" {override} "}) == override


def test_blank_override_falls_back_to_the_public_rpc():
    chain = load_chain_registry().resolve("base-sepolia")
    assert resolve_rpc_url(chain, {"QB2_BASE_SEPOLIA_RPC_URL": "  "}) == "https://sepolia.base.org"


@pytest.mark.parametrize(
    "override",
    [
        "http://rpc.example/KEY",
        "wss://rpc.example/KEY",
        "rpc.example/KEY",
        "https://",
        "http://[::1",
    ],
)
def test_unsafe_override_is_rejected_without_echoing_it(override):
    chain = load_chain_registry().resolve("base-sepolia")
    with pytest.raises(RpcConfigurationError) as raised:
        resolve_rpc_url(chain, {"QB2_BASE_SEPOLIA_RPC_URL": override})
    assert "QB2_BASE_SEPOLIA_RPC_URL" in str(raised.value)
    assert "KEY" not in str(raised.value)


def test_chain_without_any_rpc_is_rejected():
    data = load_chain_registry().resolve("ethereum-sepolia").model_dump()
    data["public_rpc_url"] = None
    with pytest.raises(RpcConfigurationError, match="QB2_ETHEREUM_SEPOLIA_RPC_URL is not set"):
        resolve_rpc_url(ChainSpec.model_validate(data), {})
