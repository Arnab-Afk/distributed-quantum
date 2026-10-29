"""Provenance Merkle-root anchor transactions on EVM chains (#21).

An anchor is a zero-value transaction from the configured anchor account to itself.
Its calldata carries a version tag, the batch's SHA-256 Merkle root, the batch size
and the hash profile, so the size is authenticated together with the root.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from eth_typing import HexStr

from quantum_backend_v2.chains.adapter import EvmRpcAdapter

MAGIC = b"QMSHANC1"
# Calldata profile byte -> provenance hash profile. New profiles need a new byte.
HASH_PROFILES = {1: "qmesh-provenance-sha256-v1"}
PAYLOAD_LENGTH = len(MAGIC) + 32 + 4 + 1
_ROOT = re.compile(r"[0-9a-f]{64}")
_TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")

AnchorStatus = Literal["confirmed", "pending", "not_found", "failed", "mismatch"]


@dataclass(frozen=True)
class AnchorPayload:
    merkle_root: str
    leaf_count: int
    hash_profile: str = HASH_PROFILES[1]

    def encode(self) -> bytes:
        if _ROOT.fullmatch(self.merkle_root) is None:
            raise ValueError("Merkle root must be a lowercase 32-byte hex digest")
        if not 0 < self.leaf_count < 2**32:
            raise ValueError("Batch size must fit in 32 bits")
        profile = next(
            (key for key, name in HASH_PROFILES.items() if name == self.hash_profile), None
        )
        if profile is None:
            raise ValueError("Unsupported hash profile")
        return (
            MAGIC
            + bytes.fromhex(self.merkle_root)
            + self.leaf_count.to_bytes(4, "big")
            + bytes([profile])
        )

    @classmethod
    def decode(cls, data: bytes) -> AnchorPayload:
        if len(data) != PAYLOAD_LENGTH or not data.startswith(MAGIC):
            raise ValueError("Not a provenance anchor payload")
        body = data[len(MAGIC) :]
        profile = HASH_PROFILES.get(body[36])
        leaf_count = int.from_bytes(body[32:36], "big")
        if profile is None or leaf_count == 0:
            raise ValueError("Not a provenance anchor payload")
        return cls(merkle_root=body[:32].hex(), leaf_count=leaf_count, hash_profile=profile)


@dataclass(frozen=True)
class AnchorCheck:
    status: AnchorStatus
    block_number: int | None = None


class EvmAnchorAdapter(EvmRpcAdapter):
    """Read-only anchor checks; signing lives with the anchor sender, not here."""

    def check_anchor(self, tx_hash: str, payload: AnchorPayload, sender: str) -> AnchorCheck:
        """Report `confirmed` only for a finalized, successful self-send carrying `payload`."""
        from web3.exceptions import TransactionNotFound

        self._require("anchor_root")
        if _TX_HASH.fullmatch(tx_hash) is None or _ADDRESS.fullmatch(sender) is None:
            raise ValueError("invalid anchor reference")
        expected = payload.encode()
        self._check_chain()
        try:
            transaction = self.web3.eth.get_transaction(HexStr(tx_hash))
        except TransactionNotFound:
            return AnchorCheck(status="not_found")
        block = transaction.get("blockNumber")
        if block is None:
            return AnchorCheck(status="pending")
        receipt = self.web3.eth.get_transaction_receipt(HexStr(tx_hash))
        if int(receipt["status"]) != 1:
            return AnchorCheck(status="failed", block_number=int(block))
        account = sender.lower()
        if (
            str(transaction["from"]).lower() != account
            or str(transaction.get("to") or "").lower() != account
            or int(transaction["value"]) != 0
            or bytes(transaction["input"]) != expected
        ):
            return AnchorCheck(status="mismatch", block_number=int(block))
        # A finalized block cannot be reorganized out; earlier confirmations can.
        if int(block) > int(self.web3.eth.get_block("finalized")["number"]):
            return AnchorCheck(status="pending", block_number=int(block))
        return AnchorCheck(status="confirmed", block_number=int(block))
