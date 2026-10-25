"""Chain adapters: offline explorer links and read-only EVM RPC queries.

Signing stays with the wallet provider in AgentKitService; no adapter holds keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from quantum_backend_v2.chains.models import Capability, ChainSpec, DisabledNetworkError

if TYPE_CHECKING:
    from web3 import Web3

ExplorerKind = Literal["transaction", "address", "block"]
TransactionStatus = Literal["not_found", "pending", "failed", "confirmed"]

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_BALANCE_OF = "0x70a08231"


class UnsupportedOperationError(ValueError):
    """An adapter operation is not enabled for this network."""


@dataclass(frozen=True)
class EvmExplorerAdapter:
    chain: ChainSpec

    def explorer_url(self, kind: ExplorerKind, value: str) -> str:
        if not self.chain.enabled:
            raise DisabledNetworkError("network is disabled")
        if "explorer_url" not in self.chain.capabilities:
            raise UnsupportedOperationError("explorer links are unavailable")
        if kind == "transaction":
            pattern, field = r"0x[0-9a-fA-F]{64}", "tx_hash"
            template = self.chain.explorers.transaction
        elif kind == "address":
            pattern, field = r"0x[0-9a-fA-F]{40}", "address"
            template = self.chain.explorers.address
        elif kind == "block":
            pattern, field = r"(?:0|[1-9][0-9]*)", "block_number"
            template = self.chain.explorers.block
        else:
            raise UnsupportedOperationError("unknown explorer link kind")
        if re.fullmatch(pattern, value) is None:
            raise ValueError("invalid explorer reference")
        return template.format(**{field: value})


class ChainMismatchError(ValueError):
    """The RPC endpoint serves a different chain than the registry entry."""


@dataclass(frozen=True)
class Balance:
    native: Decimal
    stablecoin: Decimal | None


@dataclass(frozen=True)
class StablecoinTransfer:
    """A stablecoin transfer a transaction is expected to contain."""

    sender: str
    recipient: str
    amount: Decimal


@dataclass(frozen=True)
class TransactionVerification:
    status: TransactionStatus
    block_number: int | None = None
    confirmations: int = 0
    # None when no transfer was expected.
    transfer_matched: bool | None = None

    @property
    def verified(self) -> bool:
        return self.status == "confirmed" and self.transfer_matched is not False


@dataclass
class EvmRpcAdapter:
    """Read-only queries against one registry chain through an injected Web3 client."""

    chain: ChainSpec
    web3: Web3
    _chain_checked: bool = field(default=False, init=False, repr=False)

    def get_balance(self, address: str) -> Balance:
        self._require("get_balance")
        owner = _checked(_ADDRESS, address, "invalid address")
        self._check_chain()
        native = self.web3.eth.get_balance(self.web3.to_checksum_address(owner))
        stablecoin = None
        if self.chain.stablecoin is not None:
            raw = self.web3.eth.call(
                {
                    "to": self.web3.to_checksum_address(self.chain.stablecoin.address),
                    "data": _BALANCE_OF + owner[2:].lower().zfill(64),
                }
            )
            stablecoin = _scaled(int.from_bytes(raw, "big"), self.chain.stablecoin.decimals)
        return Balance(
            native=_scaled(native, self.chain.native_token.decimals), stablecoin=stablecoin
        )

    def verify_transaction(
        self,
        tx_hash: str,
        *,
        expected_transfer: StablecoinTransfer | None = None,
        min_confirmations: int = 1,
    ) -> TransactionVerification:
        """Report whether a transaction succeeded, optionally checking a stablecoin transfer."""
        from web3.exceptions import TransactionNotFound

        self._require("verify_transaction")
        if min_confirmations < 1:
            raise ValueError("min_confirmations must be at least 1")
        reference = _checked(_TX_HASH, tx_hash, "invalid transaction hash")
        if expected_transfer is not None and self.chain.stablecoin is None:
            raise UnsupportedOperationError("this network has no stablecoin to verify")
        self._check_chain()
        try:
            receipt = self.web3.eth.get_transaction_receipt(reference)
        except TransactionNotFound:
            try:
                self.web3.eth.get_transaction(reference)
            except TransactionNotFound:
                return TransactionVerification(status="not_found")
            return TransactionVerification(status="pending")

        block = int(receipt["blockNumber"])
        if int(receipt["status"]) != 1:
            return TransactionVerification(status="failed", block_number=block)
        confirmations = max(0, int(self.web3.eth.block_number) - block + 1)
        status: TransactionStatus = "confirmed" if confirmations >= min_confirmations else "pending"
        matched = None
        if expected_transfer is not None:
            matched = any(self._is_expected(log, expected_transfer) for log in receipt["logs"])
        return TransactionVerification(
            status=status,
            block_number=block,
            confirmations=confirmations,
            transfer_matched=matched,
        )

    def _require(self, operation: Capability) -> None:
        if not self.chain.enabled:
            raise DisabledNetworkError("network is disabled")
        if operation not in self.chain.capabilities:
            raise UnsupportedOperationError("operation is unavailable on this network")

    def _check_chain(self) -> None:
        # A mistyped RPC override must not silently read another network.
        if self._chain_checked:
            return
        if int(self.web3.eth.chain_id) != int(self.chain.chain_id.split(":")[1]):
            raise ChainMismatchError("RPC endpoint serves a different chain")
        self._chain_checked = True

    def _is_expected(self, log: object, expected: StablecoinTransfer) -> bool:
        assert self.chain.stablecoin is not None
        topics = [_hex(topic) for topic in log["topics"]]  # type: ignore[index]
        if (
            str(log["address"]).lower() != self.chain.stablecoin.address.lower()  # type: ignore[index]
            or len(topics) != 3
            or topics[0] != TRANSFER_TOPIC
        ):
            return False
        amount = int(_hex(log["data"]), 16)  # type: ignore[index]
        units = expected.amount * (Decimal(10) ** self.chain.stablecoin.decimals)
        return (
            _topic_address(topics[1])
            == _checked(_ADDRESS, expected.sender, "invalid address").lower()
            and _topic_address(topics[2])
            == _checked(_ADDRESS, expected.recipient, "invalid address").lower()
            and units == units.to_integral_value()
            and amount == int(units)
        )


def _checked(pattern: re.Pattern[str], value: str, message: str) -> str:
    if pattern.fullmatch(value) is None:
        raise ValueError(message)
    return value


def _scaled(raw: int, decimals: int) -> Decimal:
    return Decimal(raw) / (Decimal(10) ** decimals)


def _hex(value: object) -> str:
    text = value.hex() if isinstance(value, bytes | bytearray) else str(value)
    text = text.lower()
    return text if text.startswith("0x") else "0x" + text


def _topic_address(topic: str) -> str:
    return "0x" + topic[-40:]
