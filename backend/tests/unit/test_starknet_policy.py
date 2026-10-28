"""Offline checks for the Starknet session policy, paymaster gate, and read adapter."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.starknet import (
    SN_SEPOLIA_CHAIN_ID,
    StarknetExplorerAdapter,
    StarknetRpcAdapter,
)
from quantum_backend_v2.starknet.paymaster import (
    PaymasterSponsorError,
    build_sponsor_request,
    sponsored_call,
)
from quantum_backend_v2.starknet.policy import (
    PolicyRejectedError,
    authorize,
    policy_from_agent_config,
    revoke,
)
from quantum_backend_v2.starknet.session import (
    encrypt_session_key,
    generate_session_keypair,
    public_session,
    session_document,
)

OWNER = "0x1"
TOKEN = "0x49d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7"
OTHER = "0x2"
NOW = 1_700_000_000


def _policy(**overrides):
    values = dict(
        max_per_proposal=Decimal("10"),
        daily_budget=Decimal("25"),
        owner=OWNER,
        token=TOKEN,
        recipient=OTHER,
        expires_at=NOW + 200_000,
        session_public_key="0xabc",
        decimals=6,
        now=NOW,
    )
    values.update(overrides)
    return policy_from_agent_config(**values)


def test_config_fields_map_onto_per_call_and_daily_caps():
    policy = _policy()
    assert policy.max_per_call == 10_000_000
    assert policy.daily_limit == 25_000_000
    assert policy.revoked is False


def test_spend_within_policy_then_reject_per_call_and_daily_and_rollover():
    policy = _policy()
    once = authorize(policy, amount=10_000_000, token=TOKEN, recipient=OTHER, now=NOW)
    assert once.spent_today == 10_000_000
    with pytest.raises(PolicyRejectedError, match="per_call"):
        authorize(once, amount=10_000_001, token=TOKEN, recipient=OTHER, now=NOW)
    twice = authorize(once, amount=10_000_000, token=TOKEN, recipient=OTHER, now=NOW)
    with pytest.raises(PolicyRejectedError, match="daily"):
        authorize(twice, amount=10_000_000, token=TOKEN, recipient=OTHER, now=NOW)
    next_day = authorize(twice, amount=10_000_000, token=TOKEN, recipient=OTHER, now=NOW + 86_400)
    assert next_day.spent_today == 10_000_000


def test_expiry_revoke_and_target_are_rejected():
    policy = _policy()
    with pytest.raises(PolicyRejectedError, match="expired"):
        authorize(policy, amount=1, token=TOKEN, recipient=OTHER, now=policy.expires_at)
    with pytest.raises(PolicyRejectedError, match="revoked"):
        authorize(revoke(policy), amount=1, token=TOKEN, recipient=OTHER, now=NOW)
    with pytest.raises(PolicyRejectedError, match="token"):
        authorize(policy, amount=1, token=OWNER, recipient=OTHER, now=NOW)
    with pytest.raises(PolicyRejectedError, match="recipient"):
        authorize(policy, amount=1, token=TOKEN, recipient=OWNER, now=NOW)


def test_contract_reverts_with_the_same_codes():
    contract = Path(__file__).resolve().parents[2] / "contracts/starknet/src/spending_policy.cairo"
    source = contract.read_text()
    for code in ("per_call", "daily", "expired", "revoked"):
        assert f"'{code}'" in source
    assert "fn spend" in source and "fn revoke_session" in source


def test_paymaster_sponsors_registration_only():
    request = build_sponsor_request(
        entrypoint="register_session", account_address=OWNER, calldata=["0x1"]
    )
    assert request["method"] == "paymaster_buildTransaction"
    assert request["params"]["execution_mode"] == "sponsored"
    for entrypoint in ("spend", "revoke_session", "register_session_admin"):
        with pytest.raises(PaymasterSponsorError, match="onboarding only"):
            build_sponsor_request(entrypoint=entrypoint, account_address=OWNER, calldata=[])


def test_sponsored_call_sends_the_key_header():
    seen = {}

    def post(url, body, headers):
        seen["url"] = url
        seen["header"] = headers["x-paymaster-api-key"]
        return {"ok": True}

    result = sponsored_call(
        entrypoint="deploy_account",
        account_address=OWNER,
        calldata=[],
        api_key="portal-key",
        post=post,
    )
    assert result == {"ok": True}
    assert seen["url"] == "https://sepolia.paymaster.avnu.fi"
    assert seen["header"] == "portal-key"


def test_generate_session_keypair_returns_hex_pair():
    private_hex, public_hex = generate_session_keypair()
    assert 1 <= len(private_hex) <= 64
    int(private_hex, 16)
    assert public_hex.startswith("0x")
    assert 3 <= len(public_hex) <= 66
    int(public_hex, 16)


def test_public_session_omits_the_private_key(monkeypatch):
    monkeypatch.setenv("WALLET_ENCRYPTION_KEY", "test-secret")
    policy = _policy()
    stored = session_document(policy, encrypt_session_key("aa"), decimals=6)
    visible = public_session(stored, now=NOW)
    assert visible is not None
    assert visible["status"] == "active"
    assert "session_key_encrypted" not in visible
    assert "aa" not in str(visible)


def test_registry_lists_starknet_sepolia_without_wallet_operations():
    chain = load_chain_registry().resolve("starknet-sepolia")
    assert chain.chain_id == "starknet:SN_SEPOLIA"
    assert chain.family == "starknet"
    assert chain.native_token.symbol == "STRK"
    assert set(chain.capabilities) == {"explorer_url", "verify_transaction"}
    assert chain.provider_aliases.agentkit is None


class _Rpc:
    def __init__(self, responses):
        self.responses = responses

    def request(self, method, params):
        value = self.responses[method]
        if isinstance(value, Exception):
            raise value
        return value


def test_adapter_confirms_success_and_rejects_a_reverted_receipt():
    chain = load_chain_registry().resolve("starknet:SN_SEPOLIA")
    tx = "0xabc"
    ok = StarknetRpcAdapter(
        chain,
        _Rpc(
            {
                "starknet_chainId": hex(SN_SEPOLIA_CHAIN_ID),
                "starknet_getTransactionReceipt": {
                    "execution_status": "SUCCEEDED",
                    "finality_status": "ACCEPTED_ON_L2",
                    "block_number": 10,
                },
                "starknet_blockNumber": 10,
            }
        ),
    )
    confirmed = ok.verify_transaction(tx)
    assert confirmed.status == "confirmed" and confirmed.confirmations == 1
    failed = StarknetRpcAdapter(
        chain,
        _Rpc(
            {
                "starknet_chainId": hex(SN_SEPOLIA_CHAIN_ID),
                "starknet_getTransactionReceipt": {
                    "execution_status": "REVERTED",
                    "block_number": 4,
                },
            }
        ),
    )
    assert failed.verify_transaction(tx).status == "failed"
    url = StarknetExplorerAdapter(chain).explorer_url("transaction", tx)
    assert url == f"https://sepolia.voyager.online/tx/{tx}"
