"""Session key material for one agent. The owner key never lands here."""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Mapping
from typing import Any

from cryptography.fernet import Fernet

try:
    from starknet_py.net.signer.stark_curve_signer import KeyPair  # type: ignore[import-not-found]
except ImportError:
    KeyPair = None

from quantum_backend_v2.starknet.policy import SpendingPolicy

_HIDDEN = "session_key_encrypted"


def generate_session_keypair() -> tuple[str, str]:
    """Return `(private_hex, public_hex)` from starknet.py. The private half is stored encrypted."""
    if KeyPair is None:
        raise RuntimeError("starknet.py is required to create a session key")
    pair = KeyPair.generate()
    return f"{pair.private_key:x}", f"{pair.public_key:#x}"


def encrypt_session_key(private_hex: str, *, secret: str | None = None) -> str:
    key = secret if secret is not None else os.getenv("WALLET_ENCRYPTION_KEY", "")
    if not key.strip():
        raise RuntimeError("WALLET_ENCRYPTION_KEY is not set")
    fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))
    return fernet.encrypt(private_hex.encode()).decode()


def session_document(
    policy: SpendingPolicy, encrypted_key: str, *, decimals: int
) -> dict[str, Any]:
    return {
        "decimals": decimals,
        "chain_id": "starknet:SN_SEPOLIA",
        "owner": policy.owner,
        "token": policy.token,
        "recipient": policy.recipient,
        "max_per_call": str(policy.max_per_call),
        "daily_limit": str(policy.daily_limit),
        "expires_at": policy.expires_at,
        "revoked": policy.revoked,
        "day_index": policy.day_index,
        "spent_today": str(policy.spent_today),
        "session_public_key": policy.session_public_key,
        "session_key_encrypted": encrypted_key,
    }


def policy_from_document(stored: Mapping[str, Any]) -> SpendingPolicy:
    return SpendingPolicy(
        owner=str(stored["owner"]),
        token=str(stored["token"]),
        recipient=str(stored["recipient"]),
        max_per_call=int(stored["max_per_call"]),
        daily_limit=int(stored["daily_limit"]),
        expires_at=int(stored["expires_at"]),
        revoked=bool(stored["revoked"]),
        day_index=int(stored["day_index"]),
        spent_today=int(stored["spent_today"]),
        session_public_key=str(stored["session_public_key"]),
    )


def public_session(stored: Mapping[str, Any] | None, *, now: int) -> dict[str, Any] | None:
    if not stored:
        return None
    if bool(stored.get("revoked")):
        status = "revoked"
    elif bool(stored.get("revocation_pending")):
        status = "revocation_pending"
    elif int(stored["expires_at"]) <= now:
        status = "expired"
    else:
        status = "active"
    visible = {key: value for key, value in stored.items() if key != _HIDDEN}
    visible["status"] = status
    return visible

