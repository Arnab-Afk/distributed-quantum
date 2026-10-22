from __future__ import annotations

import pytest

from quantum_backend_v2.chains.adapter import EvmExplorerAdapter, UnsupportedOperationError
from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.models import ChainSpec, DisabledNetworkError


@pytest.mark.parametrize(
    "network,host",
    [
        ("base-sepolia", "sepolia.basescan.org"),
        ("ethereum-sepolia", "sepolia.etherscan.io"),
    ],
)
@pytest.mark.parametrize(
    "kind,path,value",
    [
        ("transaction", "tx", "0x" + "ab" * 32),
        ("address", "address", "0x" + "CD" * 20),
        ("block", "block", "0"),
        ("block", "block", "12345"),
    ],
)
def test_explorer_links(network, host, kind, path, value):
    adapter = EvmExplorerAdapter(load_chain_registry().resolve(network))
    assert adapter.explorer_url(kind, value) == f"https://{host}/{path}/{value}"


@pytest.mark.parametrize(
    "kind,value",
    [
        ("transaction", "0x1234"),
        ("address", "0x" + "gg" * 20),
        ("address", "../../something"),
        ("block", "-1"),
        ("block", "1?key=SECRET"),
        ("block", "01"),
        ("block", "1\n"),
    ],
)
def test_bad_explorer_reference_is_rejected(kind, value):
    adapter = EvmExplorerAdapter(load_chain_registry().resolve())
    with pytest.raises(ValueError, match="invalid explorer reference"):
        adapter.explorer_url(kind, value)


def test_unavailable_explorer_operation():
    data = load_chain_registry().resolve().model_dump()
    data["capabilities"] = []
    adapter = EvmExplorerAdapter(ChainSpec.model_validate(data))
    with pytest.raises(UnsupportedOperationError):
        adapter.explorer_url("block", "1")


def test_adapter_cannot_bypass_disabled_network():
    data = load_chain_registry().resolve().model_dump()
    data["enabled"] = False
    adapter = EvmExplorerAdapter(ChainSpec.model_validate(data))
    with pytest.raises(DisabledNetworkError):
        adapter.explorer_url("block", "1")
