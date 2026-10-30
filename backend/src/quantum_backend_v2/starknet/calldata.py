"""Calldata for the spending-policy ABI.

A Cairo `u256` is two felts: the low 128 bits, then the high 128 bits.
Field order matches `register_session` and `spend` in spending_policy.cairo.
"""

from __future__ import annotations

import os

from quantum_backend_v2.starknet.policy import SpendingPolicy, felt_address

_U128 = 1 << 128
_REGISTER_FIELDS = (
    "token",
    "recipient",
    "max_per_call",
    "daily_limit",
    "expires_at",
    "session_public_key",
)


def u256_felts(value: int) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value >= 1 << 256:
        raise ValueError("u256 out of range")
    return [str(value & (_U128 - 1)), str(value >> 128)]


def register_session_calldata(policy: SpendingPolicy) -> list[str]:
    return [
        policy.token,
        policy.recipient,
        *u256_felts(policy.max_per_call),
        *u256_felts(policy.daily_limit),
        str(policy.expires_at),
        policy.session_public_key,
    ]


def spend_calldata(amount: int) -> list[str]:
    return u256_felts(amount)


def policy_contract_address() -> str:
    raw = os.getenv("STARKNET_POLICY_CONTRACT", "").strip()
    if not raw:
        raise RuntimeError("STARKNET_POLICY_CONTRACT is not set")
    return felt_address(raw)


def register_session_field_names() -> tuple[str, ...]:
    return _REGISTER_FIELDS
