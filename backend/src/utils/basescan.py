"""Compatibility helpers backed by the chain registry's explorer templates."""

from __future__ import annotations

import re

from quantum_backend_v2.chains.adapter import EvmExplorerAdapter
from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.models import ChainRegistry
from quantum_backend_v2.config import load_settings


def _explorer(network: str | None, registry: ChainRegistry | None) -> EvmExplorerAdapter:
    if registry is None:
        settings = load_settings()
        registry = load_chain_registry(settings.chain_registry_path)
        if network is None:
            network = settings.wallet_network
    return EvmExplorerAdapter(registry.resolve(network))


def validate_network(network: str, *, registry: ChainRegistry | None = None) -> None:
    _explorer(network, registry)


def validate_tx_hash(tx_hash: str) -> None:
    if re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash) is None:
        raise ValueError("Invalid transaction hash format")


def validate_address(address: str) -> None:
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", address) is None:
        raise ValueError("Invalid address format")


def get_transaction_url(
    tx_hash: str, network: str | None = None, *, registry: ChainRegistry | None = None
) -> str:
    return _explorer(network, registry).explorer_url("transaction", tx_hash)


def get_address_url(
    address: str, network: str | None = None, *, registry: ChainRegistry | None = None
) -> str:
    return _explorer(network, registry).explorer_url("address", address)


def get_block_url(
    block_number: int, network: str | None = None, *, registry: ChainRegistry | None = None
) -> str:
    return _explorer(network, registry).explorer_url("block", str(block_number))
