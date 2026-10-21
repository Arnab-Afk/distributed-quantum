from __future__ import annotations

import pytest

from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.models import ChainRegistry
from utils.basescan import get_address_url, get_block_url, get_transaction_url, validate_address


@pytest.mark.parametrize(
    "network,host",
    [
        ("base-sepolia", "sepolia.basescan.org"),
        ("eip155:84532", "sepolia.basescan.org"),
        ("ethereum-sepolia", "sepolia.etherscan.io"),
        ("eip155:11155111", "sepolia.etherscan.io"),
    ],
)
@pytest.mark.parametrize(
    "function,value,path",
    [
        (get_transaction_url, "0x" + "aa" * 32, "tx"),
        (get_address_url, "0x" + "bb" * 20, "address"),
        (get_block_url, 123, "block"),
    ],
)
def test_legacy_helpers_resolve_registry_aliases(function, value, path, network, host):
    assert (
        function(value, network, registry=load_chain_registry()) == f"https://{host}/{path}/{value}"
    )


@pytest.mark.parametrize("network", ["", "base-mainnet", "eip155:1", "secret-token", "typo"])
def test_helpers_reject_unknown_network_without_fallback(network):
    with pytest.raises(ValueError, match="unknown network") as error:
        get_block_url(1, network, registry=load_chain_registry())
    assert network == "" or network not in str(error.value)


def test_helpers_reject_disabled_network():
    data = load_chain_registry().model_dump()
    data["chains"][1]["enabled"] = False
    with pytest.raises(ValueError, match="disabled"):
        get_block_url(1, "ethereum-sepolia", registry=ChainRegistry.model_validate(data))


def test_helper_default_uses_injected_registry():
    data = load_chain_registry().model_dump()
    data["default_chain_id"] = "eip155:11155111"
    assert (
        get_block_url(1, registry=ChainRegistry.model_validate(data))
        == "https://sepolia.etherscan.io/block/1"
    )


@pytest.mark.parametrize("block", [-1, True, 1.5, "01"])
def test_helper_rejects_invalid_block_reference(block):
    with pytest.raises(ValueError):
        get_block_url(block, registry=load_chain_registry())


def test_address_validation_rejects_trailing_newline():
    with pytest.raises(ValueError):
        validate_address("0x" + "aa" * 20 + "\n")
