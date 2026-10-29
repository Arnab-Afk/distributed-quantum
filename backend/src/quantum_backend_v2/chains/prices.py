"""Read registry-allowlisted Chainlink observations at one EVM block."""

from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Any

from pydantic import BaseModel, ConfigDict

from quantum_backend_v2.chains.adapter import EvmRpcAdapter


class PriceUnavailableError(RuntimeError):
    """No usable feed observation; never fall back to a supplied price."""


class PriceRejectedError(ValueError):
    """The requested feed or returned observation violates price policy."""


class PriceObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chain_id: str
    feed: str
    pair: str
    round_id: str
    answer: str
    decimals: int
    value: str
    observed_at: datetime
    block_number: int
    block_hash: str


_FEED_ABI: list[dict[str, Any]] = [
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "name": "latestRoundData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": name, "type": kind}
            for name, kind in (
                ("roundId", "uint80"),
                ("answer", "int256"),
                ("startedAt", "uint256"),
                ("updatedAt", "uint256"),
                ("answeredInRound", "uint80"),
            )
        ],
    },
]


class EvmPriceAdapter(EvmRpcAdapter):
    def get_price(
        self, feed_id: str, reference_value: Decimal, *, now: datetime | None = None
    ) -> PriceObservation:
        self._require("get_price")
        feed = self.chain.price_feeds.get(feed_id)
        if feed is None:
            raise PriceRejectedError("unknown price feed")
        if not reference_value.is_finite() or reference_value <= 0:
            raise PriceRejectedError("reference price must be finite and positive")
        read_time = now or datetime.now(timezone.utc)
        try:
            self._check_chain()
            block = self.web3.eth.get_block("latest")
            block_number = int(block["number"])
            contract = self.web3.eth.contract(
                address=self.web3.to_checksum_address(feed.address), abi=_FEED_ABI
            )
            decimals = int(contract.functions.decimals().call(block_identifier=block_number))
            round_id, answer, started_at, updated_at, _ = contract.functions.latestRoundData().call(
                block_identifier=block_number
            )
            confirmed_block = self.web3.eth.get_block(block_number)
        except Exception:
            raise PriceUnavailableError("price feed read failed") from None
        if confirmed_block["hash"] != block["hash"]:
            raise PriceUnavailableError("price block changed during the read")
        if round_id <= 0 or answer <= 0 or not 0 <= decimals <= 18:
            raise PriceRejectedError("invalid price feed answer")
        age_seconds = read_time.timestamp() - updated_at
        if (
            started_at <= 0
            or updated_at < started_at
            or not 0 <= age_seconds <= feed.max_age_seconds
        ):
            raise PriceRejectedError("price feed round is stale or has invalid timestamps")
        with localcontext() as context:
            context.prec = 100
            value = Decimal(answer).scaleb(-decimals)
            if abs(value - reference_value) * 10000 > reference_value * feed.max_deviation_bps:
                raise PriceRejectedError("price feed exceeds the allowed reference-price deviation")
        return PriceObservation(
            chain_id=self.chain.chain_id,
            feed=feed.address,
            pair=feed_id,
            round_id=str(round_id),
            answer=str(answer),
            decimals=decimals,
            value=str(value),
            observed_at=datetime.fromtimestamp(updated_at, timezone.utc),
            block_number=block_number,
            block_hash="0x" + bytes(block["hash"]).hex(),
        )
