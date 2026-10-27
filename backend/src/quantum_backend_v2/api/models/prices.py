"""Shared API selection for registry-allowlisted price feeds."""

from pydantic import BaseModel, ConfigDict, Field


class ChainlinkPriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: str = Field(default="ethereum-sepolia", min_length=1, max_length=64)
    feed: str = Field(default="eth-usd", min_length=1, max_length=64)
