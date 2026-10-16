"""FastAPI router endpoints for AI Agents, Prompts, Instruction Studio, and Versions."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.agents import rate_limit
from app.domains.agents.models import AgentConfig
from app.domains.agents.schemas import (
    AgentConfigCreate,
    AgentConfigResponse,
    AgentVersionCreate,
    AgentVersionResponse,
    InstructionBuilderPayload,
    InstructionCompileResponse,
    InstructionDeployRequest,
    InstructionGenerateRequest,
    InstructionStudioResponse,
    InstructionTestRequest,
    InstructionTestResponse,
)
from app.domains.agents.service import AgentService

router = APIRouter()


# ==============================================================================
# Instruction Builder Studio Endpoints
# ==============================================================================

@router.get("/instructions", response_model=APIResponse[InstructionStudioResponse])
async def get_instruction_studio(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[InstructionStudioResponse]:
    """Retrieve the current instruction configuration, active agent, and preset templates."""
    service = AgentService(db)
    state = await service.get_builder_state(user_context.organization_id)
    return APIResponse.ok(data=state)


@router.post("/instructions/compile", response_model=APIResponse[InstructionCompileResponse])
async def compile_instructions(
    payload: InstructionBuilderPayload,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
) -> APIResponse[InstructionCompileResponse]:
    """Compile modular builder fields into a structured system prompt with token estimation."""
    result = AgentService.compile_instruction_prompt(payload)
    return APIResponse.ok(data=result)


@router.post("/instructions/generate", response_model=APIResponse[InstructionBuilderPayload])
async def generate_instructions(
    payload: InstructionGenerateRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
) -> APIResponse[InstructionBuilderPayload]:
    """Auto-generate an entire agent instruction set from a 1-sentence business description."""
    await rate_limit.ensure_llm_call_allowed(user_context.organization_id, "generate")
    draft = await AgentService.generate_ai_instructions(payload)
    return APIResponse.ok(data=draft)


@router.post("/instructions/deploy", status_code=status.HTTP_201_CREATED, response_model=APIResponse[AgentVersionResponse])
async def deploy_instructions(
    payload: InstructionDeployRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AgentVersionResponse]:
    """Deploy and publish instructions to live WhatsApp, Messenger, and Instagram bots."""
    service = AgentService(db)
    published_version = await service.deploy_instructions(user_context.organization_id, payload)
    return APIResponse.ok(data=AgentVersionResponse.model_validate(published_version))


@router.post("/instructions/test", response_model=APIResponse[InstructionTestResponse])
async def test_instructions(
    payload: InstructionTestRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[InstructionTestResponse]:
    """Test response generation in an isolated sandbox with RAG grounding."""
    await rate_limit.ensure_llm_call_allowed(user_context.organization_id, "test")
    service = AgentService(db)
    result = await service.simulate_test_response(user_context.organization_id, payload)
    return APIResponse.ok(data=result)


# ==============================================================================
# Agent Config & Version Management Endpoints
# ==============================================================================

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
