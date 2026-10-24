"""Application-scoped research services sharing the configured wallet service."""

from typing import Annotated

from fastapi import Depends, Request

from quantum_backend_v2.api.deps.wallet import WalletService
from services.ai_agent_service import AIAgentService
from services.proposal_service import ProposalService


async def get_ai_agent_service(request: Request, wallet: WalletService) -> AIAgentService:
    service = getattr(request.app.state, "ai_agent_service", None)
    if service is None:
        service = AIAgentService(agentkit_service=wallet)
        request.app.state.ai_agent_service = service
    return service


AIAgentServiceDep = Annotated[AIAgentService, Depends(get_ai_agent_service)]


async def get_proposal_service(
    request: Request, wallet: WalletService, agents: AIAgentServiceDep
) -> ProposalService:
    service = getattr(request.app.state, "proposal_service", None)
    if service is None:
        service = ProposalService(agentkit_service=wallet, ai_agent_service=agents)
        request.app.state.proposal_service = service
    return service


ProposalServiceDep = Annotated[ProposalService, Depends(get_proposal_service)]
