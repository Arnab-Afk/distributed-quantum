"""Kubo configuration stays optional and never exposes credentials in diagnostics."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quantum_backend_v2.config import AppSettings

SECRET = "fixture-kubo-secret-with-at-least-32-characters"


def test_kubo_defaults_do_not_require_a_running_node_or_secret() -> None:
    settings = AppSettings.from_env({})

    assert settings.kubo.rpc_url == "http://kubo:5001"
    assert settings.kubo.rpc_secret is None
    assert settings.kubo.timeout_seconds == 30
    assert settings.kubo.max_response_bytes == 4 * 1024 * 1024


def test_kubo_environment_is_typed_and_secret_is_masked() -> None:
    settings = AppSettings.from_env(
        {
            "KUBO_RPC_URL": "http://private-content-node:5001/api/v0",
            "KUBO_RPC_SECRET": SECRET,
            "KUBO_RPC_TIMEOUT_SECONDS": "17.5",
            "KUBO_RPC_MAX_RESPONSE_BYTES": "8192",
        }
    )

    assert settings.kubo.rpc_url == "http://private-content-node:5001/api/v0"
    assert settings.kubo.rpc_secret is not None
    assert settings.kubo.rpc_secret.get_secret_value() == SECRET
    assert settings.kubo.timeout_seconds == 17.5
    assert settings.kubo.max_response_bytes == 8192
    for diagnostic in (str(settings), repr(settings), settings.model_dump_json()):
        assert SECRET not in diagnostic


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "301", SECRET])
def test_kubo_timeout_rejects_invalid_values_without_echoing_input(value: str) -> None:
    with pytest.raises(ValidationError) as caught:
        AppSettings.from_env({"KUBO_RPC_SECRET": SECRET, "KUBO_RPC_TIMEOUT_SECONDS": value})

    assert SECRET not in str(caught.value)
    assert SECRET not in repr(caught.value)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", SECRET])
def test_kubo_response_budget_rejects_invalid_values_without_echoing_input(value: str) -> None:
    with pytest.raises(ValidationError) as caught:
        AppSettings.from_env({"KUBO_RPC_SECRET": SECRET, "KUBO_RPC_MAX_RESPONSE_BYTES": value})

    assert SECRET not in str(caught.value)


def test_empty_secret_is_unconfigured_not_a_backend_startup_failure() -> None:
    assert AppSettings.from_env({"KUBO_RPC_SECRET": ""}).kubo.rpc_secret is None
