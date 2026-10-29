"""Opt-in Starknet session for an existing agent. Base USDC funding is unchanged."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bson import Decimal128
from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from db.agentkit_collections import AIAgentDocument
from quantum_backend_v2.api.deps.auth import CurrentUser
from quantum_backend_v2.api.errors.models import ErrorCode, PlatformException
from quantum_backend_v2.starknet.calldata import (
    policy_contract_address,
    register_session_calldata,
    spend_calldata,
)
from quantum_backend_v2.starknet.paymaster import PaymasterSponsorError, build_sponsor_request
from quantum_backend_v2.starknet.policy import (
    PolicyRejectedError,
    authorize,
    policy_from_agent_config,
    token_units,
)
from quantum_backend_v2.starknet.session import (
    encrypt_session_key,
    generate_session_keypair,
    policy_from_document,
    public_session,
    session_document,
)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class OpenSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    token: str
    recipient: str
    expires_at: int = Field(gt=0)
    decimals: int = Field(default=18, ge=0, le=255)


class SpendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: str


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


async def _owned_agent(agent_id: str, user_id: str) -> AIAgentDocument:
    agent = await AIAgentDocument.find_one({"agent_id": agent_id})
    if agent is None:
        raise PlatformException(
            status_code=status.HTTP_404_NOT_FOUND,
            error=ErrorCode.NOT_FOUND,
            message=f"Agent '{agent_id}' not found",
        )
    if agent.owner_id != user_id:
        raise PlatformException(
            status_code=status.HTTP_403_FORBIDDEN,
            error=ErrorCode.FORBIDDEN,
            message="You do not have permission to access this agent",
        )
    return agent


def _bad_request(exc: Exception) -> PlatformException:
    return PlatformException(
        status_code=status.HTTP_400_BAD_REQUEST,
        error=ErrorCode.VALIDATION_ERROR,
        message=str(exc),
    )


@router.post("/{agent_id}/starknet-session", status_code=status.HTTP_201_CREATED)
async def open_starknet_session(
    agent_id: str,
    body: OpenSessionRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Store a session key and the owner-signed registration the paymaster may sponsor."""
    agent = await _owned_agent(agent_id, current_user.user_id)
    now = int(time.time())
    try:
        private_hex, public_hex = generate_session_keypair()
        policy = policy_from_agent_config(
            max_per_proposal=_decimal(agent.config["max_per_proposal"]),
            daily_budget=_decimal(agent.config["daily_budget"]),
            owner=body.owner,
            token=body.token,
            recipient=body.recipient,
            expires_at=body.expires_at,
            session_public_key=public_hex,
            decimals=body.decimals,
            now=now,
        )
        encrypted = encrypt_session_key(private_hex)
    except RuntimeError as exc:
        raise PlatformException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error=ErrorCode.INTERNAL_ERROR,
            message=str(exc),
        ) from None
    except ValueError as exc:
        raise _bad_request(exc) from None
    try:
        contract = policy_contract_address()
    except RuntimeError as exc:
        raise PlatformException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error=ErrorCode.INTERNAL_ERROR,
            message=str(exc),
        ) from None
    stored = session_document(policy, encrypted, decimals=body.decimals)
    await AIAgentDocument.find_one({"agent_id": agent_id}).update(
        {"$set": {"starknet_session": stored, "updated_at": datetime.now(timezone.utc)}}
    )
    calldata = register_session_calldata(policy)
    try:
        sponsor = build_sponsor_request(
            entrypoint="register_session",
            account_address=policy.owner,
            contract_address=contract,
            calldata=calldata,
        )
    except PaymasterSponsorError as exc:
        raise _bad_request(exc) from None
    return {
        "starknet_session": public_session(stored, now=now),
        "register_session": {
            "contract": contract,
            "entrypoint": "register_session",
            "calldata": calldata,
        },
        "paymaster": sponsor,
    }


@router.post("/{agent_id}/starknet-session/spend")
async def spend_starknet_session(
    agent_id: str,
    body: SpendRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Read-only preflight. Spending is recorded on-chain after the owner submits `spend`."""
    agent = await _owned_agent(agent_id, current_user.user_id)
    stored = agent.starknet_session
    if not stored:
        raise PlatformException(
            status_code=status.HTTP_404_NOT_FOUND,
            error=ErrorCode.NOT_FOUND,
            message="Agent has no Starknet session",
        )
    now = int(time.time())
    try:
        policy = policy_from_document(stored)
        decimals = int(stored.get("decimals", 18))
        amount = token_units(Decimal(body.amount), decimals)
        authorize(
            policy,
            amount=amount,
            token=policy.token,
            recipient=policy.recipient,
            now=now,
        )
        contract = policy_contract_address()
    except (PolicyRejectedError, ValueError) as exc:
        raise _bad_request(exc) from None
    except RuntimeError as exc:
        raise PlatformException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error=ErrorCode.INTERNAL_ERROR,
            message=str(exc),
        ) from None
    return {
        "starknet_session": public_session(stored, now=now),
        "spend": {
            "contract": contract,
            "entrypoint": "spend",
            "calldata": spend_calldata(amount),
        },
    }


@router.post("/{agent_id}/starknet-session/revoke")
async def revoke_starknet_session(agent_id: str, current_user: CurrentUser) -> dict[str, Any]:
    """Return the owner revoke call. The database stays active until the chain confirms it."""
    agent = await _owned_agent(agent_id, current_user.user_id)
    stored = agent.starknet_session
    if not stored:
        raise PlatformException(
            status_code=status.HTTP_404_NOT_FOUND,
            error=ErrorCode.NOT_FOUND,
            message="Agent has no Starknet session",
        )
    try:
        contract = policy_contract_address()
    except RuntimeError as exc:
        raise PlatformException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error=ErrorCode.INTERNAL_ERROR,
            message=str(exc),
        ) from None
    pending = dict(stored)
    pending["revocation_pending"] = True
    await AIAgentDocument.find_one({"agent_id": agent_id}).update(
        {"$set": {"starknet_session": pending, "updated_at": datetime.now(timezone.utc)}}
    )
    try:
        build_sponsor_request(
            entrypoint="revoke_session",
            account_address=str(stored["owner"]),
            contract_address=contract,
            calldata=[],
        )
    except PaymasterSponsorError:
        sponsored = False
    else:
        sponsored = True
    return {
        "starknet_session": public_session(pending, now=int(time.time())),
        "revoke_session": {
            "contract": contract,
            "entrypoint": "revoke_session",
            "calldata": [],
        },
        "paymaster_sponsored": sponsored,
    }
