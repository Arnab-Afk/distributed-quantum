"""Check provenance anchors on the configured chain (#21)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from requests import Session
from web3 import Web3

from quantum_backend_v2.chains.anchor import AnchorPayload, EvmAnchorAdapter
from quantum_backend_v2.chains.models import ChainSpec
from quantum_backend_v2.chains.rpc import resolve_rpc_url
from quantum_backend_v2.provenance.models import ChainAnchor


class AnchorUnavailableError(OSError):
    """Not final yet, not found or not reachable; verification reports `unavailable`."""


class RegistryAnchorAdapter:
    """`AnchorAdapter` for one registry chain and anchor account; read-only."""

    def __init__(self, chain: ChainSpec, sender: str, env: Mapping[str, str]) -> None:
        if "anchor_root" not in chain.capabilities:
            raise ValueError("network does not support provenance anchoring")
        self.chain = chain
        self._sender = sender
        self._rpc_env = (
            {chain.rpc_env_var: env[chain.rpc_env_var]} if chain.rpc_env_var in env else {}
        )

    async def contains_root(self, anchor: ChainAnchor) -> bool:
        if anchor.chain != self.chain.chain_id:
            return False
        payload = AnchorPayload(anchor.merkle_root, anchor.leaf_count, anchor.hash_profile)
        rpc_url = resolve_rpc_url(self.chain, self._rpc_env)

        def check() -> str:
            with Session() as session:
                web3 = Web3(
                    Web3.HTTPProvider(
                        rpc_url,
                        session=session,
                        request_kwargs={"timeout": 10},
                        exception_retry_configuration=None,
                    )
                )
                adapter = EvmAnchorAdapter(self.chain, web3)
                try:
                    return adapter.check_anchor(anchor.tx_hash, payload, self._sender).status
                except ValueError:
                    raise
                except Exception:
                    # RPC errors can include a credential-bearing endpoint URL.
                    raise AnchorUnavailableError("anchor lookup failed") from None

        status = await asyncio.to_thread(check)
        if status in ("pending", "not_found"):
            # A missing transaction may be pruned history, so it is not proof of absence.
            raise AnchorUnavailableError(f"anchor transaction {status}")
        return status == "confirmed"
