"""Value selected allocations without changing historical optimization inputs."""

from decimal import Decimal
from typing import Any

from quantum_backend_v2.chains.prices import PriceObservation


def calculate_portfolio_quantities(
    result: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    observation = PriceObservation.model_validate(inputs["price_observation"])
    investment = Decimal(str(inputs["investment_usd"]))
    valuations = {}
    for method in ("classical", "quantum"):
        selected = result["benchmark"][method]["selected_assets"]
        allocation = investment / len(selected) if selected else Decimal(0)
        valuations[method] = [
            {
                "ticker": ticker,
                "allocation_usd": str(allocation),
                "price_usd": observation.value if ticker == "ETH-USD" else None,
                "quantity": str(allocation / Decimal(observation.value))
                if ticker == "ETH-USD"
                else None,
                "status": "valued" if ticker == "ETH-USD" else "unsupported_feed",
            }
            for ticker in selected
        ]
    return {"investment_usd": str(investment), "allocations": valuations}
