"""Ordered SHA-256 Merkle trees over bundle digests, with positional proofs."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

_DIGEST = re.compile(r"[0-9a-f]{64}")


def _decode(digest: str) -> bytes:
    if _DIGEST.fullmatch(digest) is None:
        raise ValueError("Expected a lowercase, 32-byte hex digest without 0x")
    return bytes.fromhex(digest)


def _parent(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def proof_length(leaf_index: int, leaf_count: int) -> int:
    """Count real siblings on a positional path, excluding odd-node promotions."""
    if leaf_count < 1 or not 0 <= leaf_index < leaf_count:
        raise ValueError("Leaf position is outside this batch")
    length = 0
    while leaf_count > 1:
        if (leaf_index ^ 1) < leaf_count:
            length += 1
        leaf_index //= 2
        leaf_count = (leaf_count + 1) // 2
    return length


@dataclass(frozen=True)
class MerkleProof:
    """Bottom-up sibling hashes, leaf position and original batch size."""

    leaf_index: int
    leaf_count: int
    siblings: tuple[str, ...]


class MerkleTree:
    """Build an ordered tree; promote an odd final node unchanged (RFC 6962 shape)."""

    def __init__(self, bundle_hashes: Sequence[str]) -> None:
        if not bundle_hashes:
            raise ValueError("A Merkle batch must contain at least one bundle")
        # Distinct prefixes prevent an internal node being interpreted as a leaf.
        level = [hashlib.sha256(b"\x00" + _decode(digest)).digest() for digest in bundle_hashes]
        self._levels = [level]
        while len(level) > 1:
            level = [
                _parent(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
                for i in range(0, len(level), 2)
            ]
            self._levels.append(level)

    @property
    def root(self) -> str:
        """Return the lowercase hex root (including leaf framing for singleton trees)."""
        return self._levels[-1][0].hex()

    def proof(self, leaf_index: int) -> MerkleProof:
        """Return an inclusion proof for one zero-based position."""
        count = len(self._levels[0])
        if not 0 <= leaf_index < count:
            raise IndexError("Leaf index is outside this batch")
        index = leaf_index
        siblings = []
        for level in self._levels[:-1]:
            sibling = index ^ 1
            if sibling < len(level):
                siblings.append(level[sibling].hex())
            index //= 2
        return MerkleProof(leaf_index, count, tuple(siblings))


def verify_proof(bundle_digest: str, proof: MerkleProof, root: str) -> bool:
    """Check an ordered proof; malformed digests, positions or paths return false."""
    if proof.leaf_count < 1 or not 0 <= proof.leaf_index < proof.leaf_count:
        return False
    # Check path length before hashing untrusted siblings.
    if len(proof.siblings) != proof_length(proof.leaf_index, proof.leaf_count):
        return False
    try:
        expected = _decode(root)
        node = hashlib.sha256(b"\x00" + _decode(bundle_digest)).digest()
        index, width = proof.leaf_index, proof.leaf_count
        siblings = iter(proof.siblings)
        while width > 1:
            # Promoted nodes consume neither a sibling nor a hash operation.
            if (index ^ 1) < width:
                sibling = _decode(next(siblings))
                node = _parent(sibling, node) if index % 2 else _parent(node, sibling)
            index //= 2
            width = (width + 1) // 2
        return node == expected
    except ValueError:
        return False
