"""EvmRpcAdapter against a scripted JSON-RPC provider (no network)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from web3 import Web3
from web3.providers import BaseProvider

from quantum_backend_v2.chains.adapter import (
    TRANSFER_TOPIC,
    ChainMismatchError,
    EvmRpcAdapter,
    StablecoinTransfer,
    UnsupportedOperationError,
)
from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.models import ChainSpec, DisabledNetworkError

BASE_SEPOLIA_CHAIN_ID = 84532
USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
SENDER = "0x" + "11" * 20
RECIPIENT = "0x" + "22" * 20
TX = "0x" + "ab" * 32
BLOCK_HASH = "0x" + "cd" * 32


def _word(value: int) -> str:
    return "0x" + format(value, "064x")


def _address_topic(address: str) -> str:
    return "0x" + address[2:].lower().zfill(64)


class ScriptedProvider(BaseProvider):
    """Answers JSON-RPC methods from a dict and records every call."""

    def __init__(self, results: dict[str, Any]) -> None:
        super().__init__()
        self.results = {"eth_chainId": hex(BASE_SEPOLIA_CHAIN_ID), **results}
        self.calls: list[tuple[str, Any]] = []

    def make_request(self, method: str, params: Any) -> dict[str, Any]:
        self.calls.append((method, params))
        result = self.results.get(method)
        if callable(result):
            result = result(params)
        return {"jsonrpc": "2.0", "id": 1, "result": result}

    def is_connected(self, show_traceback: bool = False) -> bool:
        return True


def _transfer_log(sender: str, recipient: str, units: int, token: str = USDC) -> dict[str, Any]:
    return {
        "address": token,
        "topics": [TRANSFER_TOPIC, _address_topic(sender), _address_topic(recipient)],
        "data": _word(units),
        "blockNumber": hex(100),
        "blockHash": BLOCK_HASH,
        "transactionHash": TX,
        "transactionIndex": "0x0",
        "logIndex": "0x0",
        "removed": False,
    }


def _receipt(status: int = 1, logs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "transactionHash": TX,
        "transactionIndex": "0x0",
        "blockHash": BLOCK_HASH,
        "blockNumber": hex(100),
        "from": SENDER,
        "to": USDC,
        "cumulativeGasUsed": "0x5208",
        "gasUsed": "0x5208",
        "effectiveGasPrice": "0x1",
        "contractAddress": None,
        "logs": logs or [],
        "logsBloom": "0x" + "00" * 256,
        "status": hex(status),
        "type": "0x2",
    }


def _adapter(
    network: str = "base-sepolia", **results: Any
) -> tuple[EvmRpcAdapter, ScriptedProvider]:
    provider = ScriptedProvider(results)
    return EvmRpcAdapter(load_chain_registry().resolve(network), Web3(provider)), provider


def test_balance_reads_native_and_stablecoin_with_registry_decimals():
    adapter, provider = _adapter(eth_getBalance=hex(15 * 10**17), eth_call=_word(2_500_000))

    balance = adapter.get_balance(SENDER)

    assert balance.native == Decimal("1.5")
    assert balance.stablecoin == Decimal("2.5")
    call = next(params for method, params in provider.calls if method == "eth_call")
    assert call[0]["to"].lower() == USDC.lower()
    assert call[0]["data"] == "0x70a08231" + SENDER[2:].zfill(64)


def test_confirmed_transfer_is_verified():
    adapter, _ = _adapter(
        eth_getTransactionReceipt=_receipt(logs=[_transfer_log(SENDER, RECIPIENT, 5_000_000)]),
        eth_blockNumber=hex(102),
    )

    result = adapter.verify_transaction(
        TX,
        expected_transfer=StablecoinTransfer(SENDER, RECIPIENT, Decimal("5")),
        min_confirmations=3,
    )

    assert (result.status, result.block_number, result.confirmations) == ("confirmed", 100, 3)
    assert result.transfer_matched is True
    assert result.verified


@pytest.mark.parametrize(
    "log",
    [
        _transfer_log(SENDER, RECIPIENT, 4_999_999),
        _transfer_log(RECIPIENT, SENDER, 5_000_000),
        _transfer_log(SENDER, RECIPIENT, 5_000_000, token="0x" + "33" * 20),
    ],
    ids=["wrong-amount", "wrong-direction", "other-token"],
)
def test_transfer_that_does_not_match_is_not_verified(log):
    adapter, _ = _adapter(eth_getTransactionReceipt=_receipt(logs=[log]), eth_blockNumber=hex(100))

    result = adapter.verify_transaction(
        TX, expected_transfer=StablecoinTransfer(SENDER, RECIPIENT, Decimal("5"))
    )

    assert result.status == "confirmed"
    assert result.transfer_matched is False
    assert not result.verified


def test_reverted_transaction_fails():
    adapter, _ = _adapter(eth_getTransactionReceipt=_receipt(status=0), eth_blockNumber=hex(110))
    result = adapter.verify_transaction(TX)
    assert result.status == "failed"
    assert not result.verified


def test_too_few_confirmations_is_pending():
    adapter, _ = _adapter(eth_getTransactionReceipt=_receipt(), eth_blockNumber=hex(100))
    assert adapter.verify_transaction(TX, min_confirmations=2).status == "pending"


def test_mempool_and_unknown_transactions():
    pending_tx = {
        "hash": TX,
        "nonce": "0x0",
        "blockHash": None,
        "blockNumber": None,
        "transactionIndex": None,
        "from": SENDER,
        "to": RECIPIENT,
        "value": "0x0",
        "gas": "0x5208",
        "gasPrice": "0x1",
        "input": "0x",
        "type": "0x0",
        "v": "0x1b",
        "r": "0x1",
        "s": "0x1",
    }
    pending, _ = _adapter(eth_getTransactionReceipt=None, eth_getTransactionByHash=pending_tx)
    unknown, _ = _adapter(eth_getTransactionReceipt=None, eth_getTransactionByHash=None)

    assert pending.verify_transaction(TX).status == "pending"
    assert unknown.verify_transaction(TX).status == "not_found"


def test_rpc_serving_another_chain_is_refused():
    adapter, provider = _adapter(eth_getBalance="0x0")
    provider.results["eth_chainId"] = hex(1)
    with pytest.raises(ChainMismatchError):
        adapter.get_balance(SENDER)
    assert [method for method, _ in provider.calls] == ["eth_chainId"]


def test_chain_id_is_checked_once_per_adapter():
    adapter, provider = _adapter(eth_getBalance="0x0", eth_call=_word(0))
    adapter.get_balance(SENDER)
    # A later change is not re-checked; adapters are built per request.
    provider.results["eth_chainId"] = hex(1)
    adapter.get_balance(SENDER)


@pytest.mark.parametrize(
    "call",
    [
        lambda a: a.get_balance("0x1234"),
        lambda a: a.verify_transaction("0x1234"),
        lambda a: a.verify_transaction(TX, min_confirmations=0),
    ],
)
def test_invalid_input_is_rejected_before_any_rpc_call(call):
    adapter, provider = _adapter()
    with pytest.raises(ValueError):
        call(adapter)
    assert provider.calls == []


def test_capabilities_are_enforced():
    # Ethereum Sepolia verifies transactions but has no wallet balance support.
    adapter, provider = _adapter("ethereum-sepolia")
    with pytest.raises(UnsupportedOperationError):
        adapter.get_balance(SENDER)
    assert provider.calls == []


def test_disabled_chain_is_refused():
    data = load_chain_registry().resolve("ethereum-sepolia").model_dump()
    data["enabled"] = False
    adapter = EvmRpcAdapter(ChainSpec.model_validate(data), Web3(ScriptedProvider({})))
    with pytest.raises(DisabledNetworkError):
        adapter.verify_transaction(TX)
