"""FastAPI router endpoints for AI Agents, Prompts, and Versions."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.agents.models import AgentConfig
from app.domains.agents.schemas import (
    AgentConfigCreate,
    AgentConfigResponse,
    AgentVersionCreate,
    AgentVersionResponse,
)
from app.domains.agents.service import AgentService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=APIResponse[AgentConfigResponse])
async def create_agent(
    payload: AgentConfigCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AgentConfigResponse]:
    """Create a new AI Agent profile."""
    service = AgentService(db)
    agent = await service.create_agent(user_context.organization_id, payload)
    return APIResponse.ok(data=AgentConfigResponse.model_validate(agent))


@router.get("/", response_model=APIResponse[List[AgentConfigResponse]])
async def list_agents(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[List[AgentConfigResponse]]:
    """List all AI Agents configured for this workspace."""
    query = select(AgentConfig).where(AgentConfig.organization_id == user_context.organization_id)
    res = await db.execute(query)
    agents = res.scalars().all()
    return APIResponse.ok(data=[AgentConfigResponse.model_validate(a) for a in agents])


@router.post("/{agent_id}/versions", status_code=status.HTTP_201_CREATED, response_model=APIResponse[AgentVersionResponse])
async def create_version(
    agent_id: UUID,
    payload: AgentVersionCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AgentVersionResponse]:
    """Create a new immutable version snapshot for an AI Agent."""
    service = AgentService(db)
    version = await service.create_version(user_context.organization_id, agent_id, payload)
    return APIResponse.ok(data=AgentVersionResponse.model_validate(version))


@router.post("/{agent_id}/versions/{version_id}/publish", response_model=APIResponse[AgentVersionResponse])
async def publish_version(
    agent_id: UUID,
    version_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AgentVersionResponse]:
    """Publish an agent version to handle live customer traffic."""
    service = AgentService(db)
    version = await service.publish_version(user_context.organization_id, agent_id, version_id)
    return APIResponse.ok(data=AgentVersionResponse.model_validate(version))
