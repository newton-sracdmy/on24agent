"""Pydantic schemas for AI Agents, Versioning, and Runs."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, field_validator

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


# ==============================================================================
# Instruction Builder Schemas
# ==============================================================================

MAX_LIST_ITEMS = 25
MAX_LIST_ITEM_LENGTH = 500
MAX_PROMPT_LENGTH = 20000


class InstructionBuilderPayload(BaseSchema):
    """Modular components defining an AI Agent's persona and behavioral rules."""
    agent_id: Optional[UUID] = None
    agent_name: str = Field(..., min_length=2, max_length=100)
    role_title: str = Field(..., min_length=2, max_length=100)
    tone_of_voice: str = Field("Friendly & Empathetic", min_length=2, max_length=100)
    language: str = Field("Bengali & English", min_length=2, max_length=100)
    primary_mission: str = Field(..., min_length=5, max_length=2000)
    business_rules: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    constraints_donts: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    escalation_protocol: Optional[str] = Field(None, max_length=1000)
    greeting_message: Optional[str] = Field(None, max_length=1000)

    @field_validator("agent_name", "role_title", "tone_of_voice", "language", "primary_mission", mode="before")
    @classmethod
    def _strip_required(cls, v: Any) -> Any:
        # Strip before length checks so whitespace-only values are rejected
        return v.strip() if isinstance(v, str) else v

    @field_validator("escalation_protocol", "greeting_message", mode="before")
    @classmethod
    def _strip_optional(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("business_rules", "constraints_donts")
    @classmethod
    def _clean_items(cls, items: List[str]) -> List[str]:
        cleaned = [item.strip() for item in items if item and item.strip()]
        for item in cleaned:
            if len(item) > MAX_LIST_ITEM_LENGTH:
                raise ValueError(f"Each item must be at most {MAX_LIST_ITEM_LENGTH} characters")
        return cleaned


class InstructionCompileResponse(BaseSchema):
    """Compiled structured system prompt with token estimation."""
    compiled_prompt: str
    estimated_token_count: int
    word_count: int


class InstructionGenerateRequest(BaseSchema):
    """User input prompt to auto-draft an agent's instruction set with AI."""
    business_description: str = Field(..., min_length=4, max_length=1000)
    target_channel: Optional[str] = "all"
    tone_preference: Optional[str] = "friendly"


class InstructionDeployRequest(BaseSchema):
    """Payload to save and publish an instruction set to live bots."""
    agent_name: str = Field(..., min_length=2, max_length=100)
    builder_payload: InstructionBuilderPayload
    # Omit to have the server compile builder_payload; send it to deploy a hand-edited prompt
    compiled_prompt: Optional[str] = Field(None, max_length=MAX_PROMPT_LENGTH)

    @field_validator("agent_name", mode="before")
    @classmethod
    def _strip_name(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("compiled_prompt")
    @classmethod
    def _non_trivial_prompt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 20:
            raise ValueError("compiled_prompt must be at least 20 characters; omit it to compile server-side")
        return v


class InstructionTestRequest(BaseSchema):
    """Sandbox simulation request to test how the agent responds."""
    test_message: str = Field(..., min_length=1, max_length=2000)
    draft_prompt: str = Field(..., min_length=10, max_length=MAX_PROMPT_LENGTH)
    knowledge_base_id: Optional[UUID] = None

    @field_validator("test_message", mode="before")
    @classmethod
    def _strip_message(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class InstructionTestResponse(BaseSchema):
    """Sandbox simulation response."""
    reply: str
    source: str = "gemini"
    grounded_kb_chunks_count: int = 0


class InstructionStudioResponse(BaseSchema):
    """Studio initialization payload with active agent, payload, and templates."""
    active_agent: Optional[AgentConfigResponse] = None
    current_version: Optional[AgentVersionResponse] = None
    builder_payload: InstructionBuilderPayload
    compiled_prompt: str
    estimated_token_count: int
    word_count: int
    presets: Dict[str, Any]

