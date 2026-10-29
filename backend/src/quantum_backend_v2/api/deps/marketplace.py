"""Application-scoped marketplace using the configured wallet service."""

from typing import Annotated

from fastapi import Depends, Request

from quantum_backend_v2.api.deps.wallet import WalletService
from services.marketplace_service import MarketplaceService


async def get_marketplace_service(request: Request, wallet: WalletService) -> MarketplaceService:
    service = getattr(request.app.state, "marketplace_service", None)
    if service is None:
        service = MarketplaceService(agentkit_service=wallet)
        request.app.state.marketplace_service = service
    return service


MarketplaceServiceDep = Annotated[MarketplaceService, Depends(get_marketplace_service)]
