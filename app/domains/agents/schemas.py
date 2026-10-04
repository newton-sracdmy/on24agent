"""Pydantic schemas for AI Agents, Versioning, and Runs."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field

from app.common.schemas import BaseSchema
from app.constants import AgentExecutionMode, AgentRunStatus, GuardrailAction


class AgentConfigCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    mode: AgentExecutionMode = AgentExecutionMode.AUTONOMOUS


class AgentVersionCreate(BaseSchema):
    system_prompt: str = Field(..., min_length=10)
    model_id: UUID
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, ge=1, le=16384)
    tool_ids: List[UUID] = Field(default_factory=list)
    knowledge_base_ids: List[UUID] = Field(default_factory=list)


class AgentVersionResponse(BaseSchema):
    id: UUID
    agent_config_id: UUID
    version_number: int
    system_prompt: str
    model_id: UUID
    temperature: float
    max_tokens: int
    is_published: bool
    published_at: Optional[datetime] = None
    created_at: datetime


class AgentConfigResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    name: str
    description: Optional[str] = None
    mode: str
    is_active: bool
    current_version_id: Optional[UUID] = None
    created_at: datetime


class AgentRunResponse(BaseSchema):
    id: UUID
    agent_config_id: UUID
    conversation_id: UUID
    status: str
    input_prompt: str
    output_response: Optional[str] = None
    latency_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
