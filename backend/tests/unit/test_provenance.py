"""Executable contract for provenance hashing, proofs and legacy bundles."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantum_backend_v2.provenance.hashing import bundle_hash, canonical_json, hash_json
from quantum_backend_v2.provenance.merkle import MerkleProof, MerkleTree, verify_proof
from quantum_backend_v2.provenance.models import (
    ChainAnchor,
    OracleReference,
    ProvenanceBundle,
    ProvenanceEvent,
    ProvenanceEventKind,
)


def legacy_bundle() -> ProvenanceBundle:
    return ProvenanceBundle(
        bundle_id="bundle-1",
        workflow_run_id="workflow-1",
        workflow_definition_id="definition-1",
        owner_user_id="owner-1",
        created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
    )


def test_canonical_json_golden_file() -> None:
    path = Path(__file__).parents[1] / "fixtures" / "provenance_canonical.json"
    for vector in json.loads(path.read_text(encoding="utf-8")):
        assert canonical_json(vector["input"]) == vector["canonical"].encode("utf-8")
        assert hash_json(vector["input"]) == vector["sha256"]


def test_canonical_json_golden() -> None:
    value = {"z": [True, None, -0.0, 1.25], "é": "量子", "a": {"b": 2, "a": 1}}
    expected = '{"a":{"a":1,"b":2},"z":[true,null,-0.0,1.25],"é":"量子"}'.encode()
    assert canonical_json(value) == expected
    assert hash_json(value) == hashlib.sha256(expected).hexdigest()
    assert canonical_json(dict(reversed(list(value.items())))) == expected


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), Decimal("1.1"), {1: "x"}, (1, 2)]
)
def test_unsupported_json_rejected(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_json(value)


def test_legacy_bundle_round_trip() -> None:
    old = legacy_bundle().model_dump(
        mode="json",
        exclude={
            "input_hash",
            "plan_id",
            "fragment_result_hashes",
            "oracle_refs",
            "storage",
            "anchors",
        },
    )
    loaded = ProvenanceBundle.model_validate(old)
    assert loaded.storage == ()
    assert loaded.anchors == ()
    assert ProvenanceBundle.model_validate_json(loaded.model_dump_json()) == loaded


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), Decimal("1.1"), {1: "x"}]
)
@pytest.mark.parametrize("location", ["summary", "event"])
def test_bundle_rejects_lossy_json_conversion(value: object, location: str) -> None:
    evidence = {"nested": [value]}
    bundle = legacy_bundle()
    if location == "summary":
        bundle = bundle.model_copy(update={"summary": evidence})
    else:
        event = ProvenanceEvent(
            event_id="event-001",
            workflow_run_id=bundle.workflow_run_id,
            kind=ProvenanceEventKind.RESULT_AGGREGATED,
            payload=evidence,
        )
        bundle = bundle.model_copy(update={"events": (event,)})
    with pytest.raises((TypeError, ValueError)):
        bundle_hash(bundle)


def test_attachment_metadata_does_not_change_commitment() -> None:
    bundle = legacy_bundle()
    attached = ProvenanceBundle.model_validate(
        {
            **bundle.model_dump(),
            "storage": [{"backend": "ipfs", "cid": "bafy-example"}],
            "anchors": [
                {
                    "chain": "eip155:11155111",
                    "tx_hash": "0xexample",
                    "merkle_root": "a" * 64,
                    "leaf_index": 0,
                    "leaf_count": 1,
                    "proof": [],
                }
            ],
        }
    )
    assert bundle_hash(attached) == bundle_hash(bundle)
    assert bundle_hash(bundle.model_copy(update={"summary": {"changed": True}})) != bundle_hash(
        bundle
    )


def test_bundle_hash_golden() -> None:
    # Independent Node-crypto vector: fixes defaults, timestamps and envelope too.
    assert bundle_hash(legacy_bundle()) == (
        "dfa26130fd51ede287dd0364965cf7272930f4bc5a1af7f486e2f57284dbcb24"
    )


def test_future_optional_fields_do_not_silently_redefine_v1() -> None:
    class FutureBundle(ProvenanceBundle):
        future_field: str = "new-default"

    current = legacy_bundle()
    extended = FutureBundle.model_validate(current.model_dump())
    assert bundle_hash(extended) == bundle_hash(current)


def test_future_nested_model_fields_do_not_silently_redefine_v1() -> None:
    class FutureEvent(ProvenanceEvent):
        future_event_field: str = "new-event-default"

    class FutureOracle(OracleReference):
        future_oracle_field: str = "new-oracle-default"

    class FutureBundle(ProvenanceBundle):
        events: tuple[FutureEvent, ...] = ()
        oracle_refs: tuple[FutureOracle, ...] = ()

    bundle = legacy_bundle()
    timestamp = bundle.created_at
    event = ProvenanceEvent(
        event_id="event-001",
        workflow_run_id=bundle.workflow_run_id,
        kind=ProvenanceEventKind.RESULT_AGGREGATED,
        payload={"result": 42},
        occurred_at=timestamp,
    )
    oracle = OracleReference(
        provider="fixture-provider",
        feed="fixture-feed",
        round_id="1",
        value="1.25",
        observed_at=timestamp,
    )
    current = bundle.model_copy(update={"events": (event,), "oracle_refs": (oracle,)})
    extended = FutureBundle.model_validate(current.model_dump())
    assert bundle_hash(extended) == bundle_hash(current)
    changed = current.model_copy(
        update={"events": (event.model_copy(update={"payload": {"result": 43}}),)}
    )
    assert bundle_hash(changed) != bundle_hash(current)


def test_evidence_models_reject_extra_fields_and_invalid_hashes() -> None:
    base = legacy_bundle().model_dump()
    with pytest.raises(ValidationError):
        ProvenanceBundle.model_validate({**base, "input_hash": "invalid"})
    with pytest.raises(ValidationError):
        ProvenanceBundle.model_validate({**base, "storage": [{"backend": "ipfs", "secret": "x"}]})


@pytest.mark.parametrize("size", range(1, 34))
def test_every_merkle_leaf_and_tamper(size: int) -> None:
    hashes = [hash_json({"result": i}) for i in range(size)]
    tree = MerkleTree(hashes)
    for index, digest in enumerate(hashes):
        proof = tree.proof(index)
        assert verify_proof(digest, proof, tree.root)
        assert not verify_proof(hash_json("tampered"), proof, tree.root)
        assert not verify_proof(digest, proof, "0" * 64)
        if proof.siblings:
            tampered = MerkleProof(index, size, ("0" * 64, *proof.siblings[1:]))
            assert not verify_proof(digest, tampered, tree.root)


def reference_merkle_root(digests: list[str]) -> str:
    # RFC 6962 section 2.1's recursive split, independent of level-wise promotion.
    if len(digests) == 1:
        return hashlib.sha256(b"\x00" + bytes.fromhex(digests[0])).hexdigest()
    split = 1 << ((len(digests) - 1).bit_length() - 1)
    left = bytes.fromhex(reference_merkle_root(digests[:split]))
    right = bytes.fromhex(reference_merkle_root(digests[split:]))
    return hashlib.sha256(b"\x01" + left + right).hexdigest()


@pytest.mark.parametrize("size", [34, 63, 64, 65, 127, 128, 129, 257, 513])
def test_large_random_batches_against_independent_reference(size: int) -> None:
    rng = random.Random(size)
    digests = [rng.getrandbits(256).to_bytes(32, "big").hex() for _ in range(size)]
    tree = MerkleTree(digests)
    assert tree.root == reference_merkle_root(digests)
    for index, digest in enumerate(digests):
        proof = tree.proof(index)
        assert verify_proof(digest, proof, tree.root)
        assert not verify_proof(digests[(index + 1) % size], proof, tree.root)
        assert not verify_proof(digest, MerkleProof(index ^ 1, size, proof.siblings), tree.root)


def test_merkle_golden() -> None:
    first, second = hash_json("a"), hash_json("b")
    left = hashlib.sha256(b"\x00" + bytes.fromhex(first)).digest()
    right = hashlib.sha256(b"\x00" + bytes.fromhex(second)).digest()
    assert MerkleTree([first]).root == left.hex()
    assert MerkleTree([first, second]).root == hashlib.sha256(b"\x01" + left + right).hexdigest()
    assert MerkleTree([first, first]).proof(0).leaf_count == 2


def test_merkle_cross_language_golden() -> None:
    # Independently computed with node:crypto SHA-256, not the Python tree helper.
    digests = [
        "ac8d8342bbb2362d13f0a559a3621bb407011368895164b628a54f7fc33fc43c",
        "c100f95c1913f9c72fc1f4ef0847e1e723ffe0bde0b36e5f36c13f81fe8c26ed",
        "879923da020d1533f4d8e921ea7bac61e8ba41d3c89d17a4d14e3a89c6780d5d",
    ]
    root = "e02d91683d90844e76246bb56a8bca1f3bda6139a70e7d4302918a0c9afed136"
    tree = MerkleTree(digests)
    assert tree.root == root
    assert tree.proof(2).siblings == (
        "ad9bbbd7d5560ceafd9174d44e78799a0cb5ad3cd7795d095b4656df27dd715a",
    )


@pytest.mark.parametrize("size", [3, 5, 7, 9, 17, 33])
def test_repeated_trailing_leaf_changes_root(size: int) -> None:
    digests = [hash_json(i) for i in range(size)]
    assert MerkleTree(digests).root != MerkleTree([*digests, digests[-1]]).root


@pytest.mark.parametrize(
    ("size", "lengths"),
    [(3, [2, 2, 1]), (5, [3, 3, 3, 3, 1]), (6, [3, 3, 3, 3, 2, 2])],
)
def test_promoted_nodes_have_no_synthetic_siblings(size: int, lengths: list[int]) -> None:
    digests = [hash_json(i) for i in range(size)]
    tree = MerkleTree(digests)
    for index, length in enumerate(lengths):
        proof = tree.proof(index)
        assert len(proof.siblings) == length
        assert verify_proof(digests[index], proof, tree.root)
        assert not verify_proof(
            digests[index], MerkleProof(index, size, proof.siblings[:-1]), tree.root
        )
        assert not verify_proof(
            digests[index], MerkleProof(index, size, (*proof.siblings, "0" * 64)), tree.root
        )


def test_malformed_path_rejected_before_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_hash(*args: object, **kwargs: object) -> None:
        pytest.fail("Malformed path must be rejected before hashing")

    monkeypatch.setattr(hashlib, "sha256", unexpected_hash)
    # The third leaf in a three-leaf tree needs one sibling, not two.
    assert not verify_proof("0" * 64, MerkleProof(2, 3, ("0" * 64, "0" * 64)), "0" * 64)


def test_membership_proof_does_not_authenticate_supplied_batch_size() -> None:
    digests = [hash_json(i) for i in range(3)]
    tree = MerkleTree(digests)
    proof = tree.proof(0)
    # Opaque siblings do not expose their subtree sizes. Trust the anchor's batch
    # metadata, not an inclusion proof alone, for an exact cardinality claim.
    assert verify_proof(digests[0], proof, tree.root)
    assert verify_proof(digests[0], MerkleProof(0, 4, proof.siblings), tree.root)


def test_proof_anchor_round_trip() -> None:
    digests = [hash_json(i) for i in range(3)]
    tree = MerkleTree(digests)
    proof = tree.proof(2)
    anchor = ChainAnchor(
        chain="eip155:11155111",
        tx_hash="0xexample",
        merkle_root=tree.root,
        leaf_index=proof.leaf_index,
        leaf_count=proof.leaf_count,
        proof=proof.siblings,
    )
    restored = ChainAnchor.model_validate_json(anchor.model_dump_json())
    assert verify_proof(
        digests[2],
        MerkleProof(restored.leaf_index, restored.leaf_count, restored.proof),
        restored.merkle_root,
    )
    for changes in ({"leaf_index": 3}, {"leaf_count": 1}, {"proof": []}, {"leaf_index": True}):
        with pytest.raises(ValidationError):
            ChainAnchor.model_validate({**anchor.model_dump(), **changes})


def test_merkle_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        MerkleTree([])
    with pytest.raises(ValueError):
        MerkleTree(["invalid"])
    tree = MerkleTree([hash_json(1)])
    for index in (-1, 1):
        with pytest.raises(IndexError):
            tree.proof(index)
    assert not verify_proof("bad", tree.proof(0), tree.root)
    assert not verify_proof(hash_json(1), MerkleProof(1, 1, ()), tree.root)
    assert not verify_proof(hash_json(1), MerkleProof(0, 0, ()), tree.root)
    assert not verify_proof(hash_json(1), MerkleProof(0, 1, ("0" * 64,)), tree.root)
