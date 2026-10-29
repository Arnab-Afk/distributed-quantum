"""Anchor payload format and read-only anchor checks against a scripted JSON-RPC node."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest
from web3 import Web3
from web3.providers import BaseProvider

from quantum_backend_v2.application import anchoring
from quantum_backend_v2.application.anchoring import AnchorUnavailableError, RegistryAnchorAdapter
from quantum_backend_v2.chains.adapter import ChainMismatchError, UnsupportedOperationError
from quantum_backend_v2.chains.anchor import PAYLOAD_LENGTH, AnchorPayload, EvmAnchorAdapter
from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.models import ChainRegistry
from quantum_backend_v2.provenance.hashing import bundle_hash
from quantum_backend_v2.provenance.merkle import MerkleTree
from quantum_backend_v2.provenance.models import ChainAnchor
from quantum_backend_v2.provenance.verification import (
    RunEvidence,
    build_result_bundle,
    verify_bundle,
)

SEPOLIA = load_chain_registry().resolve("ethereum-sepolia")
SENDER = "0x" + "a1" * 20
TX = "0x" + "ab" * 32
ROOT = "11" * 32
PAYLOAD = AnchorPayload(ROOT, 3)


class AnchorNode(BaseProvider):
    """A Sepolia node holding one anchor transaction, adjustable per test."""

    def __init__(self) -> None:
        super().__init__()
        self.chain_id = 11155111
        self.transaction: dict[str, Any] | None = {
            "hash": TX,
            "from": SENDER,
            "to": SENDER,
            "value": "0x0",
            "input": "0x" + PAYLOAD.encode().hex(),
            "blockNumber": hex(100),
            "blockHash": "0x" + "cd" * 32,
            "nonce": "0x0",
            "gas": "0x5555",
            "gasPrice": "0x1",
            "transactionIndex": "0x0",
        }
        self.status = 1
        self.finalized = 120
        self.error: Exception | None = None

    def make_request(self, method: str, params: Any) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        if method == "eth_chainId":
            result: Any = hex(self.chain_id)
        elif method == "eth_getTransactionByHash":
            result = self.transaction
        elif method == "eth_getTransactionReceipt":
            result = {
                "transactionHash": TX,
                "transactionIndex": "0x0",
                "blockHash": "0x" + "cd" * 32,
                "blockNumber": hex(100),
                "from": SENDER,
                "to": SENDER,
                "cumulativeGasUsed": "0x5555",
                "gasUsed": "0x5555",
                "logs": [],
                "status": hex(self.status),
            }
        elif method == "eth_getBlockByNumber":
            assert params[0] == "finalized"
            result = {"number": hex(self.finalized), "hash": "0x" + "ef" * 32}
        else:
            raise AssertionError(method)
        return {"jsonrpc": "2.0", "id": 1, "result": result}

    def is_connected(self, show_traceback: bool = False) -> bool:
        return True


def check(node: AnchorNode, payload: AnchorPayload = PAYLOAD, sender: str = SENDER):
    return EvmAnchorAdapter(SEPOLIA, Web3(node)).check_anchor(TX, payload, sender)


def test_payload_round_trips_and_authenticates_batch_size():
    data = PAYLOAD.encode()
    assert len(data) == PAYLOAD_LENGTH == 45
    assert data[:8] == b"QMSHANC1"
    assert AnchorPayload.decode(data) == PAYLOAD
    # Another batch size is a different payload, so a proof cannot claim a larger batch.
    assert AnchorPayload(ROOT, 4).encode() != data


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"QMSHANC1" + bytes(36),
        b"QMSHANC2" + bytes.fromhex(ROOT) + (3).to_bytes(4, "big") + b"\x01",
        b"QMSHANC1" + bytes.fromhex(ROOT) + (0).to_bytes(4, "big") + b"\x01",
        b"QMSHANC1" + bytes.fromhex(ROOT) + (3).to_bytes(4, "big") + b"\x02",
    ],
)
def test_foreign_or_malformed_calldata_is_not_an_anchor(data):
    with pytest.raises(ValueError):
        AnchorPayload.decode(data)


@pytest.mark.parametrize(
    "payload",
    [AnchorPayload("AB" * 32, 3), AnchorPayload(ROOT, 0), AnchorPayload(ROOT, 2**32)],
)
def test_invalid_payloads_cannot_be_encoded(payload):
    with pytest.raises(ValueError):
        payload.encode()


def test_finalized_self_send_with_exact_payload_is_confirmed():
    result = check(AnchorNode())
    assert (result.status, result.block_number) == ("confirmed", 100)


def change(field, value):
    def apply(node):
        node.transaction[field] = value

    return apply


@pytest.mark.parametrize(
    ("mutate", "status"),
    [
        (lambda node: setattr(node, "transaction", None), "not_found"),
        (change("blockNumber", None), "pending"),
        (lambda node: setattr(node, "finalized", 99), "pending"),
        (lambda node: setattr(node, "status", 0), "failed"),
        (change("from", "0x" + "b2" * 20), "mismatch"),
        (change("to", "0x" + "b2" * 20), "mismatch"),
        (change("to", None), "mismatch"),
        (change("value", "0x1"), "mismatch"),
        (change("input", "0x" + AnchorPayload("22" * 32, 3).encode().hex()), "mismatch"),
        (change("input", "0x" + AnchorPayload(ROOT, 4).encode().hex()), "mismatch"),
    ],
)
def test_only_the_exact_finalized_anchor_is_confirmed(mutate, status):
    node = AnchorNode()
    mutate(node)
    assert check(node).status == status


def test_sender_comparison_ignores_checksum_case():
    assert check(AnchorNode(), sender=Web3.to_checksum_address(SENDER)).status == "confirmed"


def test_wrong_chain_and_unsupported_networks_are_refused():
    node = AnchorNode()
    node.chain_id = 84532
    with pytest.raises(ChainMismatchError):
        check(node)
    base = load_chain_registry().resolve("base-sepolia")
    with pytest.raises(UnsupportedOperationError):
        EvmAnchorAdapter(base, Web3(AnchorNode())).check_anchor(TX, PAYLOAD, SENDER)
    with pytest.raises(ValueError):
        check(AnchorNode(), sender="not-an-address")


def test_registry_limits_anchoring_to_verifiable_testnets():
    data = load_chain_registry().model_dump()
    sepolia = next(chain for chain in data["chains"] if chain["chain_id"] == "eip155:11155111")
    sepolia["capabilities"] = ["explorer_url", "anchor_root"]
    with pytest.raises(ValueError, match="requires transaction verification"):
        ChainRegistry.model_validate(data)
    sepolia["capabilities"] = ["explorer_url", "verify_transaction", "anchor_root"]
    sepolia["testnet"] = False
    sepolia["enabled"] = False
    with pytest.raises(ValueError, match="limited to testnets"):
        ChainRegistry.model_validate(data)


# --- RegistryAnchorAdapter: the async AnchorAdapter used by the verify endpoint ---


@pytest.fixture
def node(monkeypatch):
    node = AnchorNode()

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda *args, **kwargs: node)

        def __new__(cls, provider):
            return Web3(provider)

    monkeypatch.setattr(anchoring, "Web3", FakeWeb3)
    return node


def anchor(**changes: Any) -> ChainAnchor:
    values = {
        "chain": "eip155:11155111",
        "tx_hash": TX,
        "merkle_root": ROOT,
        "leaf_index": 0,
        "leaf_count": 3,
        "proof": ("22" * 32, "33" * 32),
        **changes,
    }
    return ChainAnchor(**values)


def contains(item: ChainAnchor) -> bool:
    return asyncio.run(RegistryAnchorAdapter(SEPOLIA, SENDER, {}).contains_root(item))


def test_adapter_confirms_and_rejects(node):
    assert contains(anchor()) is True
    assert contains(anchor(chain="eip155:84532")) is False
    node.transaction["from"] = "0x" + "b2" * 20
    assert contains(anchor()) is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda node: setattr(node, "transaction", None),
        lambda node: setattr(node, "finalized", 99),
        lambda node: setattr(node, "error", RuntimeError("https://user:TOP_SECRET@rpc/key")),
    ],
)
def test_unconfirmed_or_unreachable_anchors_are_unavailable(node, mutate):
    mutate(node)
    with pytest.raises(AnchorUnavailableError) as caught:
        contains(anchor())
    assert "TOP_SECRET" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_adapter_requires_an_anchoring_network():
    with pytest.raises(ValueError):
        RegistryAnchorAdapter(load_chain_registry().resolve("base-sepolia"), SENDER, {})


def evidence(run_id: str) -> RunEvidence:
    return RunEvidence(
        run_id=run_id,
        workflow_definition_id="circuit-execution",
        owner_user_id="owner-1",
        input_snapshot={"circuit": "h q[0];"},
        plan_id="plan-1",
        result={
            "job_id": run_id,
            "fragment_results": [{"fragment_id": "frag-1"}],
            "quantum_result": {"probabilities": {"0": 1.0}},
        },
    )


def test_anchored_bundle_verifies_through_the_existing_report(node):
    created = datetime(2026, 10, 29, tzinfo=timezone.utc)
    runs = [evidence(f"workflow-{index}") for index in range(3)]
    bundles = [build_result_bundle(run, created_at=created) for run in runs]
    tree = MerkleTree([bundle_hash(bundle) for bundle in bundles])
    proof = tree.proof(1)
    node.transaction["input"] = "0x" + AnchorPayload(tree.root, 3).encode().hex()
    anchored = bundles[1].model_copy(
        update={"anchors": (anchor(merkle_root=tree.root, leaf_index=1, proof=proof.siblings),)}
    )
    adapters = {SEPOLIA.chain_id: RegistryAnchorAdapter(SEPOLIA, SENDER, {})}

    async def verify(run):
        return await verify_bundle(
            anchored,
            expected_hash=bundle_hash(bundles[1]),
            run=run,
            anchor_adapters=adapters,
        )

    report = asyncio.run(verify(runs[1]))
    checks = {check.name: check.status for check in report.checks}
    assert checks["anchor_proof"] == checks["anchor_transaction"] == "passed"
    assert report.status == "verified"
    # A changed result breaks the commitment even though the anchor is real.
    changed = replace(
        runs[1],
        result={"job_id": "workflow-1", "fragment_results": [], "quantum_result": {}},
    )
    assert asyncio.run(verify(changed)).status != "verified"
