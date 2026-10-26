"""Bind an options result to the persisted input and exact oracle observation."""

from typing import Any

from quantum_backend_v2.chains.prices import PriceObservation
from quantum_backend_v2.provenance.hashing import bundle_hash, hash_json
from quantum_backend_v2.provenance.models import OracleReference, ProvenanceBundle


def build_options_provenance(
    job_id: str, owner_user_id: str, inputs: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    observation = PriceObservation.model_validate(inputs["price_observation"])
    bundle = ProvenanceBundle(
        bundle_id="provenance-" + job_id,
        workflow_run_id=job_id,
        workflow_definition_id="options-pricing",
        owner_user_id=owner_user_id,
        input_hash=hash_json(inputs),
        oracle_refs=(
            OracleReference(
                provider="chainlink",
                feed=observation.chain_id + "/" + observation.feed,
                round_id=observation.round_id,
                value=observation.value,
                observed_at=observation.observed_at,
            ),
        ),
        summary={
            "result_hash": hash_json(result),
            "price_observation": observation.model_dump(mode="json"),
        },
    )
    return {"bundle": bundle.model_dump(mode="json"), "bundle_hash": bundle_hash(bundle)}
