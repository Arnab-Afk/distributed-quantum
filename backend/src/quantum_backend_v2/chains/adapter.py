"""Local explorer links only. Wallet/payment adapters belong to later slices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from quantum_backend_v2.chains.models import ChainSpec, DisabledNetworkError

ExplorerKind = Literal["transaction", "address", "block"]


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
