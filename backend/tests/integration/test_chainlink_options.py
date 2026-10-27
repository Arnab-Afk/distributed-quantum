"""Opt-in persistence checks using a unique database on a local MongoDB server."""

import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from beanie import init_beanie
from pymongo import AsyncMongoClient

from quantum_backend_v2.application.parity import OptionsJobService
from quantum_backend_v2.chains.prices import PriceObservation, PriceRejectedError
from quantum_backend_v2.persistence.mongodb import OptionsJobDocument, PlatformUserDocument
from quantum_backend_v2.provenance.hashing import bundle_hash, hash_json
from quantum_backend_v2.provenance.models import ProvenanceBundle

MONGODB_URI = os.environ.get("QMESH_TEST_MONGODB_URI")
pytestmark = pytest.mark.skipif(
    not MONGODB_URI, reason="set QMESH_TEST_MONGODB_URI for a local test server"
)


def test_oracle_snapshot_survives_reconnection_and_processing():
    async def run():
        database = "qmesh_oracle_test_" + uuid4().hex
        client = AsyncMongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        observation = PriceObservation(
            chain_id="eip155:11155111",
            feed="0x694AA1769357215DE4FAC081bf1f309aDC325306",
            pair="eth-usd",
            round_id="18446744073709588700",
            answer="232065000000",
            decimals=8,
            value="2320.65000000",
            observed_at=datetime.now(timezone.utc),
            block_number=11996279,
            block_hash="0x" + "ab" * 32,
        )
        source = SimpleNamespace(get_price=AsyncMock(return_value=observation))
        payload = dict(
            option_type="european_call_long",
            current_value=2300,
            strike_or_cost=2400,
            time_to_expiry=1,
            volatility=0.2,
            risk_free_rate=0.05,
            num_uncertainty_qubits=3,
            epsilon=0.1,
            alpha=0.05,
            chainlink_price={"network": "ethereum-sepolia", "feed": "eth-usd"},
        )
        try:
            await init_beanie(
                database=client[database],
                document_models=[OptionsJobDocument, PlatformUserDocument],
            )
            service = OptionsJobService(source)
            submitted = await service.submit(
                option_type=payload["option_type"],
                owner_user_id="oracle-owner",
                request_payload=payload,
            )
            job_id = submitted.id
            snapshot = submitted.request_payload
            await client.close()
            client = AsyncMongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            await init_beanie(
                database=client[database],
                document_models=[OptionsJobDocument, PlatformUserDocument],
            )
            service = OptionsJobService()
            await service.process(job_id=job_id, request_payload={"current_value": 9999})
            completed = await service.get_job_for_owner(job_id, owner_user_id="oracle-owner")
            assert completed.status == "completed", completed.error
            assert completed.request_payload == snapshot
            result = completed.result_payload
            assert result["request"]["current_value"] == 2320.65
            evidence = result.pop("provenance")
            bundle = ProvenanceBundle.model_validate(evidence["bundle"])
            assert bundle_hash(bundle) == evidence["bundle_hash"]
            assert bundle.input_hash == hash_json(snapshot)
            assert bundle.summary["result_hash"] == hash_json(result)
            assert bundle.oracle_refs[0].round_id == observation.round_id
            assert await service.get_job_for_owner(job_id, owner_user_id="other-owner") is None
            await service.process(job_id=job_id, request_payload={})
            unchanged = await OptionsJobDocument.get(job_id)
            assert unchanged.result_payload["provenance"] == evidence
            source.get_price.assert_awaited_once()
            rejecting_service = OptionsJobService(
                SimpleNamespace(get_price=AsyncMock(side_effect=PriceRejectedError("stale")))
            )
            with pytest.raises(PriceRejectedError):
                await rejecting_service.submit(
                    option_type=payload["option_type"],
                    owner_user_id="oracle-owner",
                    request_payload=payload,
                )
            assert await OptionsJobDocument.count() == 1
        finally:
            await client.drop_database(database)
            await client.close()

    asyncio.run(run())


def test_risk_and_portfolio_persist_oracle_inputs():
    from quantum_backend_v2.application.financial_portfolio import (
        PortfolioOptimizationConfig,
        build_portfolio_optimization_artifacts,
    )
    from quantum_backend_v2.application.parity import FinancialJobService, RiskJobService
    from quantum_backend_v2.persistence.mongodb import FinancialJobDocument, RiskJobDocument

    async def run():
        database = "qmesh_oracle_test_" + uuid4().hex
        client = AsyncMongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        documents = [PlatformUserDocument, FinancialJobDocument, RiskJobDocument]
        observation = PriceObservation(
            chain_id="eip155:11155111",
            feed="0x694AA1769357215DE4FAC081bf1f309aDC325306",
            pair="eth-usd",
            round_id="42",
            answer="200000000000",
            decimals=8,
            value="2000.00000000",
            observed_at=datetime.now(timezone.utc),
            block_number=100,
            block_hash="0x" + "ab" * 32,
        )
        source = SimpleNamespace(get_price=AsyncMock(return_value=observation))
        try:
            await init_beanie(database=client[database], document_models=documents)
            risk = await RiskJobService(source).submit(
                risk_model="equity",
                portfolio_size=1,
                owner_user_id="owner",
                request_payload={
                    "risk_model": "equity",
                    "holdings": [
                        {
                            "ticker": "ETH-USD",
                            "weight": 1,
                            "quantity": 2,
                            "current_value": 2000,
                            "chainlink_price": {"network": "ethereum-sepolia", "feed": "eth-usd"},
                        }
                    ],
                    "historical_returns": [[0.01], [-0.02], [0.03], [-0.01]],
                    "num_uncertainty_qubits": 3,
                    "epsilon": 0.1,
                },
            )
            csv_bytes = (
                b"date,ETH-USD,AAPL\n2026-01-01,2000,100\n2026-01-02,2010,102\n"
                b"2026-01-03,2020,101\n2026-01-04,2030,103\n"
                b"2026-01-05,2040,104\n2026-01-06,2050,105\n"
            )
            finance = await FinancialJobService(
                discovery_service=None, libp2p_runtime=None, price_source=source
            ).submit(
                filename="history.csv",
                owner_user_id="owner",
                problem_type="portfolio_optimization",
                config=PortfolioOptimizationConfig(budget=1, parameter_search_steps=3),
                csv_bytes=csv_bytes,
                valuation={
                    "current_value": 2000,
                    "investment_usd": 1000,
                    "chainlink_price": {"network": "ethereum-sepolia", "feed": "eth-usd"},
                },
            )
            await client.close()
            client = AsyncMongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            await init_beanie(database=client[database], document_models=documents)
            await RiskJobService().process(job_id=risk.id, request_payload={})
            await FinancialJobService(discovery_service=None, libp2p_runtime=None).process(
                job_id=finance.id, csv_bytes=b"invalid"
            )
            for model, job_id in [(RiskJobDocument, risk.id), (FinancialJobDocument, finance.id)]:
                completed = await model.get(job_id)
                assert completed.status == "completed", completed.error
                result = dict(completed.result_payload)
                evidence = result.pop("provenance")
                bundle = ProvenanceBundle.model_validate(evidence["bundle"])
                assert bundle_hash(bundle) == evidence["bundle_hash"]
                assert bundle.input_hash == hash_json(completed.request_payload)
                assert bundle.summary["result_hash"] == hash_json(result)
            completed = await FinancialJobDocument.get(finance.id)
            saved = completed.request_payload
            config = dict(saved["config"])
            config.pop("problem_type")
            replay = build_portfolio_optimization_artifacts(
                csv_bytes=saved["csv_text"].encode(),
                job_id=finance.id,
                filename="history.csv",
                config=PortfolioOptimizationConfig(**config),
            ).payload
            for method in ("classical", "quantum"):
                assert replay["benchmark"][method] == completed.result_payload["benchmark"][method]
            assert source.get_price.await_count == 2
        finally:
            await client.drop_database(database)
            await client.close()

    asyncio.run(run())
