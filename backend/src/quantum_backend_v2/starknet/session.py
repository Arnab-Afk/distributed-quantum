"""Session key material for one agent. The owner key never lands here."""

from __future__ import annotations

import base64
import hashlib
import os
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from cryptography.fernet import Fernet

try:
    from starknet_py.net.signer.stark_curve_signer import KeyPair  # type: ignore[import-not-found]
except ImportError:
    KeyPair = None

from quantum_backend_v2.starknet.policy import SpendingPolicy

_HIDDEN = "session_key_encrypted"
_TX_HASH = re.compile(r"0x[0-9a-fA-F]{1,64}")


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


def note_submitted_tx(
    stored: Mapping[str, Any],
    *,
    kind: str,
    tx_hash: str,
    amount: str | None = None,
    now: int,
) -> dict[str, Any]:
    """Remember a hash the owner wallet returned. This does not confirm spend or revoke."""
    if _TX_HASH.fullmatch(tx_hash) is None:
        raise ValueError("invalid transaction hash")
    updated = dict(stored)
    entry: dict[str, Any] = {
        "kind": kind,
        "tx_hash": tx_hash,
        "submitted_at": now,
        "status": "pending",
    }
    if kind == "register":
        updated["register_tx"] = tx_hash
    elif kind == "spend":
        if amount is None or not amount.strip():
            raise ValueError("spend amount is required")
        try:
            parsed = Decimal(amount)
        except InvalidOperation as exc:
            raise ValueError("spend amount must be a number") from exc
        if parsed <= 0:
            raise ValueError("spend amount must be positive")
        updated["last_spend_tx"] = tx_hash
        updated["last_spend_amount"] = amount.strip()
        entry["amount"] = amount.strip()
    elif kind == "revoke":
        updated["revoke_tx"] = tx_hash
    else:
        raise ValueError("unknown transaction kind")
    calls = [dict(row) for row in updated.get("calls") or []]
    if not any(str(row.get("tx_hash")) == tx_hash for row in calls):
        calls.append(entry)
    updated["calls"] = calls
    return updated


def backfill_calls(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Keep older single-hash fields visible in the call list."""
    updated = dict(stored)
    calls = [dict(row) for row in updated.get("calls") or []]
    known = {str(row.get("tx_hash")) for row in calls}
    seeds = (
        ("register", updated.get("register_tx"), None),
        ("spend", updated.get("last_spend_tx"), updated.get("last_spend_amount")),
        ("revoke", updated.get("revoke_tx"), None),
    )
    for kind, tx_hash, amount in seeds:
        if not isinstance(tx_hash, str) or not tx_hash or tx_hash in known:
            continue
        row: dict[str, Any] = {"kind": kind, "tx_hash": tx_hash, "status": "pending"}
        if isinstance(amount, str) and amount:
            row["amount"] = amount
        calls.append(row)
        known.add(tx_hash)
    updated["calls"] = calls
    return updated


def apply_call_status(
    stored: Mapping[str, Any], *, tx_hash: str, status: str, now: int
) -> dict[str, Any]:
    """Record a receipt status. A confirmed revoke is the only path that sets revoked."""
    if status not in {"pending", "confirmed", "failed", "not_found"}:
        raise ValueError("unknown receipt status")
    updated = dict(stored)
    calls: list[dict[str, Any]] = []
    for row in updated.get("calls") or []:
        item = dict(row)
        if item.get("tx_hash") == tx_hash and item.get("status") not in {"confirmed", "failed"}:
            item["status"] = status
            item["checked_at"] = now
        calls.append(item)
    updated["calls"] = calls
    if any(item.get("kind") == "revoke" and item.get("status") == "confirmed" for item in calls):
        updated["revoked"] = True
        updated["revocation_pending"] = False
    return updated


def refresh_call_statuses(
    stored: Mapping[str, Any],
    verify,
    *,
    now: int,
) -> dict[str, Any]:
    """Ask `verify(tx_hash)` for each open call. A lookup error leaves that call pending."""
    updated = backfill_calls(stored)
    for row in list(updated["calls"]):
        if row.get("status") in {"confirmed", "failed"}:
            continue
        tx_hash = str(row.get("tx_hash", ""))
        try:
            status = str(verify(tx_hash))
            updated = apply_call_status(updated, tx_hash=tx_hash, status=status, now=now)
        except Exception:
            continue
    return updated


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

