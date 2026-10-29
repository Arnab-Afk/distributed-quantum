"""Feed validation and persisted oracle input regression tests."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from eth_abi import encode
from web3 import Web3
from web3.providers import BaseProvider

from quantum_backend_v2.application.finance_provenance import build_finance_provenance
from quantum_backend_v2.application.price_sources import resolve_price_input
from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.prices import (
    EvmPriceAdapter,
    PriceRejectedError,
    PriceUnavailableError,
)
from quantum_backend_v2.provenance.hashing import bundle_hash
from quantum_backend_v2.provenance.models import ProvenanceBundle

NOW = 1_780_000_000
BLOCK_HASH = "0x" + "ab" * 32


class FeedProvider(BaseProvider):
    def __init__(self, *, answer=2000 * 10**8, updated=NOW, decimals=8, round_id=42):
        super().__init__()
        self.round = (round_id, answer, min(updated, NOW - 10), updated, round_id)
        self.decimals = decimals
        self.calls = []
        self.chain_id = 11155111
        self.reorg = False
        self.fail = False

    def make_request(self, method, params):
        self.calls.append((method, params))
        if self.fail:
            raise RuntimeError("https://secret-provider/token")
        if method == "eth_chainId":
            result = hex(self.chain_id)
        elif method == "eth_getBlockByNumber":
            result = {
                "number": "0x64",
                "hash": BLOCK_HASH if not self.reorg or params[0] == "latest" else "0x" + "cd" * 32,
                "timestamp": hex(NOW),
            }
        elif method == "eth_call":
            if params[0]["data"] == "0x313ce567":
                result = "0x" + encode(["uint8"], [self.decimals]).hex()
            else:
                result = (
                    "0x"
                    + encode(["uint80", "int256", "uint256", "uint256", "uint80"], self.round).hex()
                )
        else:
            raise AssertionError(method)
        return {"jsonrpc": "2.0", "id": 1, "result": result}


def read_price(provider, reference="2000", feed="eth-usd"):
    return EvmPriceAdapter(
        load_chain_registry().resolve("ethereum-sepolia"), Web3(provider)
    ).get_price(feed, Decimal(reference), now=datetime.fromtimestamp(NOW, timezone.utc))


def test_exact_observation_and_pinned_calls():
    provider = FeedProvider(answer=200012345678)
    observation = read_price(provider)
    assert observation.value == "2000.12345678"
    assert observation.answer == "200012345678"
    assert observation.round_id == "42"
    assert observation.block_hash == BLOCK_HASH
    assert observation.chain_id == "eip155:11155111"
    assert all(params[1] == "0x64" for method, params in provider.calls if method == "eth_call")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"answer": 0},
        {"answer": -1},
        {"round_id": 0},
        {"decimals": 19},
        {"updated": NOW - 3601},
        {"updated": NOW + 1},
        {"updated": 0},
        {"answer": 2400 * 10**8 + 1},
    ],
)
def test_rejects_unusable_observations(kwargs):
    with pytest.raises(PriceRejectedError):
        read_price(FeedProvider(**kwargs))


def test_accepts_policy_boundaries():
    assert (
        read_price(FeedProvider(updated=NOW - 3600, answer=2400 * 10**8)).value == "2400.00000000"
    )


@pytest.mark.parametrize(
    "reference,feed", [("NaN", "eth-usd"), ("0", "eth-usd"), ("2000", "unknown")]
)
def test_invalid_request_does_not_contact_rpc(reference, feed):
    provider = FeedProvider()
    with pytest.raises(PriceRejectedError):
        read_price(provider, reference, feed)
    assert provider.calls == []


@pytest.mark.parametrize("fault", ["reorg", "fail", "chain_id"])
def test_rpc_failure_has_no_fallback_or_secret(fault):
    provider = FeedProvider()
    setattr(provider, fault, 1 if fault == "chain_id" else True)
    with pytest.raises(PriceUnavailableError) as error:
        read_price(provider)
    assert "secret" not in str(error.value)


def test_resolved_inputs_and_provenance_bind_exact_round():
    observation = read_price(FeedProvider())
    source = SimpleNamespace(get_price=AsyncMock(return_value=observation))
    payload = {
        "current_value": 2100,
        "chainlink_price": {"network": "ethereum-sepolia", "feed": "eth-usd"},
        "price_observation": {"forged": True},
    }
    resolved = asyncio.run(resolve_price_input(payload, source))
    assert resolved["current_value"] == 2000
    assert resolved["reference_value"] == "2100"
    assert resolved["price_observation"] == observation.model_dump(mode="json")
    assert payload["current_value"] == 2100
    evidence = build_finance_provenance(
        "opt-test", "owner", resolved, {"value": 123}, workflow="options-pricing"
    )
    bundle = ProvenanceBundle.model_validate(evidence["bundle"])
    assert bundle.oracle_refs[0].round_id == "42"
    assert bundle.oracle_refs[0].value == observation.value
    assert bundle_hash(bundle) == evidence["bundle_hash"]
    source.get_price.assert_awaited_once()


def test_manual_input_never_reads_or_accepts_supplied_evidence():
    source = SimpleNamespace(get_price=AsyncMock())
    assert asyncio.run(
        resolve_price_input({"current_value": 2000, "price_observation": {}}, source)
    ) == {"current_value": 2000}
    source.get_price.assert_not_called()


def test_job_execution_uses_persisted_observation(monkeypatch):
    from quantum_backend_v2.application import parity, real_options_pricing

    class MemoryJob(SimpleNamespace):
        records = {}

        async def insert(self):
            self.records[self.id] = self

        async def save(self):
            self.records[self.id] = self

        @classmethod
        async def get(cls, job_id):
            return cls.records.get(job_id)

    monkeypatch.setattr(parity, "OptionsJobDocument", MemoryJob)
    monkeypatch.setattr(parity, "_ensure_platform_user", AsyncMock())
    received = []

    def price(payload):
        received.append(payload)
        return {"value": payload["current_value"] / 10}

    monkeypatch.setattr(real_options_pricing, "price_options", price)
    source = SimpleNamespace(get_price=AsyncMock(return_value=read_price(FeedProvider())))
    service = parity.OptionsJobService(source)

    async def run():
        doc = await service.submit(
            option_type="european_call_long",
            owner_user_id="owner",
            request_payload={
                "current_value": 2100,
                "chainlink_price": {"network": "ethereum-sepolia", "feed": "eth-usd"},
            },
        )
        await service.process(job_id=doc.id, request_payload={"current_value": 9999})
        assert doc.status == "completed"
        assert received[0]["current_value"] == 2000
        assert doc.result_payload["provenance"]["bundle"]["oracle_refs"][0]["round_id"] == "42"
        await service.process(job_id=doc.id, request_payload={})
        assert len(received) == 1

    asyncio.run(run())
    source.get_price.assert_awaited_once()


def test_oracle_request_scope_and_manual_compatibility():
    from pydantic import ValidationError

    from quantum_backend_v2.api.models.options import OptionsJobRequest

    payload = dict(
        option_type="european_call_long",
        current_value=2000,
        strike_or_cost=2100,
        time_to_expiry=1,
        volatility=0.2,
        risk_free_rate=0.05,
    )
    assert OptionsJobRequest(**payload).chainlink_price is None
    assert OptionsJobRequest(**payload, chainlink_price={}).chainlink_price.feed == "eth-usd"
    payload["option_type"] = "expand"
    with pytest.raises(ValidationError, match="european calls"):
        OptionsJobRequest(**payload, chainlink_price={})


@pytest.mark.parametrize(
    "error,expected",
    [
        (PriceRejectedError("stale observation"), 422),
        (PriceUnavailableError("private provider detail"), 503),
    ],
)
def test_api_reports_feed_errors_without_creating_background_work(error, expected):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from quantum_backend_v2.api.deps.auth import require_authenticated
    from quantum_backend_v2.api.routers.options import build_options_router

    service = SimpleNamespace(submit=AsyncMock(side_effect=error), process=AsyncMock())
    app = FastAPI()
    app.dependency_overrides[require_authenticated] = lambda: SimpleNamespace(user_id="owner")
    app.include_router(build_options_router(options_job_service=service))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/options/submit",
            json={
                "option_type": "european_call_long",
                "current_value": 2000,
                "strike_or_cost": 2100,
                "time_to_expiry": 1,
                "volatility": 0.2,
                "risk_free_rate": 0.05,
                "chainlink_price": {},
            },
        )
    assert response.status_code == expected
    assert "private provider detail" not in response.text
    service.process.assert_not_called()


def test_saved_observation_reproduces_pricing_results():
    from quantum_backend_v2.api.models.options import OptionsAnalysisResult
    from quantum_backend_v2.application.real_options_pricing import price_options

    source = SimpleNamespace(get_price=AsyncMock(return_value=read_price(FeedProvider())))
    payload = dict(
        option_type="european_call_long",
        current_value=2100,
        strike_or_cost=2100,
        time_to_expiry=1,
        volatility=0.2,
        risk_free_rate=0.05,
        num_uncertainty_qubits=3,
        epsilon=0.1,
        alpha=0.05,
        chainlink_price={"network": "ethereum-sepolia", "feed": "eth-usd"},
    )
    saved = asyncio.run(resolve_price_input(payload, source))
    first = price_options(saved)
    second = price_options(saved)
    for key in first.keys() - {"analysis_duration_ms", "generated_at"}:
        assert first[key] == second[key]
    assert first["request"] == second["request"] == saved
    first["provenance"] = build_finance_provenance(
        "opt-replay", "owner", saved, first, workflow="options-pricing"
    )
    assert OptionsAnalysisResult.model_validate(first).provenance is not None
    source.get_price.assert_awaited_once()


def test_risk_feed_valuation_and_replay():
    from quantum_backend_v2.api.models.risk import RiskJobRequest
    from quantum_backend_v2.application.price_sources import resolve_risk_prices
    from quantum_backend_v2.application.risk_engine import price_risk

    request = RiskJobRequest.model_validate(
        {
            "holdings": [
                {
                    "ticker": "ETH-USD",
                    "weight": 1,
                    "quantity": 2,
                    "current_value": 2000,
                    "chainlink_price": {},
                }
            ],
            "historical_returns": [[0.01], [-0.02], [0.03], [-0.01], [0.02]],
            "num_uncertainty_qubits": 3,
            "epsilon": 0.1,
        }
    )
    source = SimpleNamespace(get_price=AsyncMock(return_value=read_price(FeedProvider())))
    saved = asyncio.run(resolve_risk_prices(request.model_dump(), source))
    assert saved["portfolio_value_usd"] == 4000
    first, second = price_risk(saved), price_risk(saved)
    for key in first.keys() - {"analysis_duration_ms", "generated_at"}:
        assert first[key] == second[key]
    assert first["quantum_cvar_99_usd"] == first["quantum_cvar_99"] * 4000
    source.get_price.assert_awaited_once()


def test_portfolio_valuation_preserves_selection_and_marks_unsupported():
    from quantum_backend_v2.application.portfolio_valuation import calculate_portfolio_quantities

    result = {
        "benchmark": {
            "classical": {"selected_assets": ["ETH-USD", "AAPL"]},
            "quantum": {"selected_assets": ["AAPL"]},
        }
    }
    inputs = {
        "investment_usd": 1000,
        "price_observation": read_price(FeedProvider()).model_dump(mode="json"),
    }
    valuation = calculate_portfolio_quantities(result, inputs)
    eth, stock = valuation["allocations"]["classical"]
    assert Decimal(eth["allocation_usd"]) == 500
    assert Decimal(eth["quantity"]) == Decimal("0.25")
    assert stock["quantity"] is None
    assert stock["status"] == "unsupported_feed"
    assert result["benchmark"]["quantum"]["selected_assets"] == ["AAPL"]


@pytest.mark.parametrize(
    "change",
    [
        {"historical_returns": None},
        {"historical_returns": [[float("nan")]] * 4},
        {"risk_model": "credit"},
        {"historical_returns": [[0.1, 0.2]] * 4},
    ],
)
def test_risk_requires_complete_historical_inputs(change):
    from pydantic import ValidationError

    from quantum_backend_v2.api.models.risk import RiskJobRequest

    payload = {
        "holdings": [
            {
                "ticker": "ETH-USD",
                "weight": 1,
                "quantity": 2,
                "current_value": 2000,
                "chainlink_price": {},
            }
        ],
        "historical_returns": [[0.01], [-0.02], [0.03], [-0.01]],
    }
    with pytest.raises(ValidationError):
        RiskJobRequest.model_validate({**payload, **change})


def test_live_risk_csv_is_resolved_and_invalid_history_rejected():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from quantum_backend_v2.api.deps.auth import require_authenticated
    from quantum_backend_v2.api.routers.risk import build_risk_router

    service = SimpleNamespace(
        submit=AsyncMock(
            return_value=SimpleNamespace(
                id="risk-test", status="queued", risk_model="equity", portfolio_size=1
            )
        ),
        process=AsyncMock(),
    )
    app = FastAPI()
    app.dependency_overrides[require_authenticated] = lambda: SimpleNamespace(user_id="owner")
    app.include_router(build_risk_router(risk_job_service=service))
    data = {"use_chainlink": "true", "quantity": "2", "current_value": "2000"}
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/risk/submit-csv",
            data=data,
            files={
                "file": (
                    "eth.csv",
                    "date,close\n2026-01-01,2000\n2026-01-02,2010\n2026-01-03,2020\n2026-01-04,2005\n2026-01-05,2015\n",
                )
            },
        )
        assert response.status_code == 201, response.text
        payload = service.submit.call_args.kwargs["request_payload"]
        assert len(payload["historical_returns"]) == 4
        assert payload["holdings"][0]["quantity"] == 2
        response = client.post(
            "/api/v1/risk/submit-csv",
            data=data,
            files={"file": ("eth.csv", "ticker,weight\nETH-USD,1\n")},
        )
        assert response.status_code == 422
        response = client.post(
            "/api/v1/risk/submit-csv",
            data=data,
            files={"file": ("eth.csv", "date,close\n2026-01-01,2000,unexpected\n")},
        )
        assert response.status_code == 422
    service.submit.assert_awaited_once()


@pytest.mark.parametrize("rows", [[], [[0.01]], [[0.01]] * 3])
def test_manual_risk_rejects_insufficient_supplied_history(rows):
    from pydantic import ValidationError

    from quantum_backend_v2.api.models.risk import RiskJobRequest

    with pytest.raises(ValidationError):
        RiskJobRequest(holdings=[{"ticker": "ETH-USD", "weight": 1}], historical_returns=rows)


@pytest.mark.parametrize(
    "csv_text",
    [
        "date,close\n2026-01-01," + "1" * 131073,
        "date,close,volume\n2026-01-01,2000,100",
        "date,close,close\n2026-01-01,1000,2000",
        "date,close, Close \n2026-01-01,1000,2000",
        'date,close\n2026-01-01,"2000',
        "date,close\n2026-01-01,2000\n2026-01-02,2010\n"
        "2026-01-04,2020\n2026-01-05,2030\n2026-01-06,2040",
    ],
)
def test_live_risk_csv_rejects_ambiguous_or_malformed_history(csv_text):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from quantum_backend_v2.api.deps.auth import require_authenticated
    from quantum_backend_v2.api.routers.risk import build_risk_router

    service = SimpleNamespace(submit=AsyncMock(), process=AsyncMock())
    app = FastAPI()
    app.dependency_overrides[require_authenticated] = lambda: SimpleNamespace(user_id="owner")
    app.include_router(build_risk_router(risk_job_service=service))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/risk/submit-csv",
            data={"use_chainlink": "true", "quantity": "2", "current_value": "2000"},
            files={"file": ("history.csv", csv_text)},
        )
    assert response.status_code == 422
    service.submit.assert_not_called()


def test_portfolio_summary_identifies_full_result_hash_and_retrieval():
    from quantum_backend_v2.application.parity import _build_financial_summary_payload
    from quantum_backend_v2.provenance.hashing import hash_json

    inputs = {"price_observation": read_price(FeedProvider()).model_dump(mode="json")}
    result = {"quantum_execution": {"quantum_result": {"probabilities": {"00": 1.0}}}}
    evidence = build_finance_provenance(
        "fin-review", "owner", inputs, result, workflow="portfolio-optimization"
    )
    full_hash = hash_json(result)
    result["provenance"] = evidence
    summary = _build_financial_summary_payload(result)
    commitment = summary["provenance"]["bundle"]["summary"]
    assert commitment["result_hash"] == full_hash
    assert commitment["result_hash_scope"] == "full_result_excluding_provenance"
    assert commitment["result_url"] == "/api/v1/finance/fin-review?result_detail=full"
    assert summary["quantum_execution"]["quantum_result"]["probabilities"] is None
    assert result["quantum_execution"]["quantum_result"]["probabilities"] == {"00": 1.0}
    bundle = ProvenanceBundle.model_validate(evidence["bundle"])
    assert bundle_hash(bundle) == evidence["bundle_hash"]
