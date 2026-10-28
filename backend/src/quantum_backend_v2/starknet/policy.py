"""Spending rules shared with the Sepolia policy contract.

The contract is the enforcement point. These checks are the same decisions:
a stolen session key can call only `spend`, and `spend` reverts past the caps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal

_FELT = re.compile(r"^0x[0-9a-fA-F]{1,64}$")
_DAY = 86_400


class PolicyRejectedError(ValueError):
    """A spend the policy contract reverts. `code` matches the Cairo assert."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SpendingPolicy:
    owner: str
    token: str
    recipient: str
    max_per_call: int
    daily_limit: int
    expires_at: int
    revoked: bool
    day_index: int
    spent_today: int
    session_public_key: str


def token_units(amount: Decimal, decimals: int) -> int:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not 0 <= decimals <= 255:
        raise ValueError("invalid token decimals")
    scaled = amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError("amount is finer than the token decimals")
    return int(scaled)


def felt_address(value: str) -> str:
    if _FELT.fullmatch(value) is None or int(value, 16) == 0:
        raise ValueError("invalid starknet address")
    return "0x" + format(int(value, 16), "x")


def policy_from_agent_config(
    *,
    max_per_proposal: Decimal,
    daily_budget: Decimal,
    owner: str,
    token: str,
    recipient: str,
    expires_at: int,
    session_public_key: str,
    decimals: int,
    now: int,
) -> SpendingPolicy:
    """Map agent config fields onto the on-chain per-call and per-day caps."""
    if max_per_proposal > daily_budget:
        raise ValueError("max_per_proposal cannot exceed daily_budget")
    if expires_at <= now:
        raise ValueError("session expiry must be in the future")
    if not session_public_key:
        raise ValueError("session public key is required")
    return SpendingPolicy(
        owner=felt_address(owner),
        token=felt_address(token),
        recipient=felt_address(recipient),
        max_per_call=token_units(max_per_proposal, decimals),
        daily_limit=token_units(daily_budget, decimals),
        expires_at=expires_at,
        revoked=False,
        day_index=now // _DAY,
        spent_today=0,
        session_public_key=session_public_key,
    )


def authorize(
    policy: SpendingPolicy,
    *,
    amount: int,
    token: str,
    recipient: str,
    now: int,
) -> SpendingPolicy:
    """Return the policy after a successful spend. Raises PolicyRejectedError otherwise."""
    if policy.revoked:
        raise PolicyRejectedError("revoked")
    if now >= policy.expires_at:
        raise PolicyRejectedError("expired")
    if felt_address(token) != policy.token:
        raise PolicyRejectedError("token")
    if felt_address(recipient) != policy.recipient:
        raise PolicyRejectedError("recipient")
    if amount <= 0 or amount > policy.max_per_call:
        raise PolicyRejectedError("per_call")
    day = now // _DAY
    spent = 0 if day != policy.day_index else policy.spent_today
    if spent + amount > policy.daily_limit:
        raise PolicyRejectedError("daily")
    return replace(policy, day_index=day, spent_today=spent + amount)


def revoke(policy: SpendingPolicy) -> SpendingPolicy:
    return replace(policy, revoked=True)
