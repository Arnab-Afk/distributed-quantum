"""One wallet service per application, using its validated chain configuration."""

from typing import Annotated

from fastapi import Depends, Request

from services.agentkit_service import AgentKitService


async def get_wallet_service(request: Request) -> AgentKitService:
    service = getattr(request.app.state, "wallet_service", None)
    if service is None:
        service = AgentKitService(
            registry=request.app.state.chain_registry,
            network=request.app.state.wallet_chain_id,
        )
        request.app.state.wallet_service = service
    return service


WalletService = Annotated[AgentKitService, Depends(get_wallet_service)]
