"""Resolve optional oracle inputs once, before persisting an options job."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Protocol

from requests import Session
from web3 import Web3

from quantum_backend_v2.chains.models import ChainRegistry
from quantum_backend_v2.chains.prices import (
    EvmPriceAdapter,
    PriceObservation,
    PriceUnavailableError,
)
from quantum_backend_v2.chains.rpc import resolve_rpc_url


class PriceSource(Protocol):
    async def get_price(
        self, network: str, feed: str, reference_value: Decimal
    ) -> PriceObservation: ...


class ChainlinkPriceSource:
    def __init__(self, registry: ChainRegistry, env: Mapping[str, str]) -> None:
        self._registry = registry
        self._rpc_env = {
            chain.rpc_env_var: env[chain.rpc_env_var]
            for chain in registry.chains
            if chain.rpc_env_var in env
        }

    async def get_price(
        self, network: str, feed: str, reference_value: Decimal
    ) -> PriceObservation:
        chain = self._registry.resolve(network)
        rpc_url = resolve_rpc_url(chain, self._rpc_env)

        def read_price() -> PriceObservation:
            with Session() as session:
                web3 = Web3(
                    Web3.HTTPProvider(
                        rpc_url,
                        session=session,
                        request_kwargs={"timeout": 10},
                        exception_retry_configuration=None,
                    )
                )
                return EvmPriceAdapter(chain, web3).get_price(feed, reference_value)

        return await asyncio.to_thread(read_price)


async def resolve_options_price(
    payload: dict[str, Any], source: PriceSource | None
) -> dict[str, Any]:
    resolved = dict(payload)
    # Evidence comes from our read, never from caller-provided metadata.
    resolved.pop("price_observation", None)
    selection = resolved.get("chainlink_price")
    if selection is None:
        return resolved
    if source is None:
        raise PriceUnavailableError("oracle price source is not configured")
    observation = await source.get_price(
        selection["network"], selection["feed"], Decimal(str(payload["current_value"]))
    )
    resolved["reference_value"] = str(payload["current_value"])
    resolved["current_value"] = float(observation.value)
    resolved["price_observation"] = observation.model_dump(mode="json")
    return resolved
