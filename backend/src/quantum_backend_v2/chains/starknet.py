"""Read-only Starknet Sepolia adapter. It does not hold session or owner keys."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from quantum_backend_v2.chains.adapter import (
    ChainMismatchError,
    ExplorerKind,
    TransactionStatus,
    TransactionVerification,
    UnsupportedOperationError,
)
from quantum_backend_v2.chains.models import ChainSpec, DisabledNetworkError

_FELT = re.compile(r"0x[0-9a-fA-F]{1,64}")
_BLOCK = re.compile(r"(?:0|[1-9][0-9]*)")
# shortstring("SN_SEPOLIA")
SN_SEPOLIA_CHAIN_ID = 0x534E5F5345504F4C4941


class JsonRpc(Protocol):
    def request(self, method: str, params: list[object]) -> object: ...


@dataclass(frozen=True)
class StarknetExplorerAdapter:
    chain: ChainSpec

    def explorer_url(self, kind: ExplorerKind, value: str) -> str:
        if self.chain.family != "starknet":
            raise UnsupportedOperationError("explorer links are unavailable")
        if not self.chain.enabled:
            raise DisabledNetworkError("network is disabled")
        if "explorer_url" not in self.chain.capabilities:
            raise UnsupportedOperationError("explorer links are unavailable")
        if kind == "transaction":
            pattern, field_name = _FELT, "tx_hash"
            template = self.chain.explorers.transaction
        elif kind == "address":
            pattern, field_name = _FELT, "address"
            template = self.chain.explorers.address
        elif kind == "block":
            pattern, field_name = _BLOCK, "block_number"
            template = self.chain.explorers.block
        else:
            raise UnsupportedOperationError("unknown explorer link kind")
        if pattern.fullmatch(value) is None:
            raise ValueError("invalid explorer reference")
        return template.format(**{field_name: value})


@dataclass
class StarknetRpcAdapter:
    """Receipt checks through an injected JSON-RPC client."""

    chain: ChainSpec
    rpc: JsonRpc
    _chain_checked: bool = field(default=False, init=False, repr=False)

    def verify_transaction(
        self, tx_hash: str, *, min_confirmations: int = 1
    ) -> TransactionVerification:
        if self.chain.family != "starknet":
            raise UnsupportedOperationError("operation is unavailable on this network")
        if not self.chain.enabled or "verify_transaction" not in self.chain.capabilities:
            raise UnsupportedOperationError("operation is unavailable on this network")
        if min_confirmations < 1:
            raise ValueError("min_confirmations must be at least 1")
        if _FELT.fullmatch(tx_hash) is None:
            raise ValueError("invalid transaction hash")
        self._check_chain()
        try:
            receipt = self.rpc.request("starknet_getTransactionReceipt", [tx_hash])
        except LookupError:
            return TransactionVerification(status="not_found")
        if not isinstance(receipt, dict):
            return TransactionVerification(status="not_found")
        execution = str(receipt.get("execution_status", ""))
        finality = str(receipt.get("finality_status", ""))
        block = receipt.get("block_number")
        block_number = int(block) if isinstance(block, int) else None
        if execution == "REVERTED":
            return TransactionVerification(status="failed", block_number=block_number)
        if execution != "SUCCEEDED" or finality not in {"ACCEPTED_ON_L2", "ACCEPTED_ON_L1"}:
            return TransactionVerification(status="pending", block_number=block_number)
        head = self.rpc.request("starknet_blockNumber", [])
        confirmations = 0
        if isinstance(head, int):
            confirmations = max(0, head - int(block_number or 0) + 1)
        status: TransactionStatus = (
            "confirmed" if confirmations >= min_confirmations else "pending"
        )
        return TransactionVerification(
            status=status, block_number=block_number, confirmations=confirmations
        )

    def _check_chain(self) -> None:
        if self._chain_checked:
            return
        reported = self.rpc.request("starknet_chainId", [])
        if (
            _chain_id(reported) != SN_SEPOLIA_CHAIN_ID
            or self.chain.chain_id != "starknet:SN_SEPOLIA"
        ):
            raise ChainMismatchError("RPC endpoint serves a different chain")
        self._chain_checked = True


def _chain_id(value: object) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16) if text.startswith("0x") else int(text)
