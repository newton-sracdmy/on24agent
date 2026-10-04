"""SQLAlchemy models for AI Agents, Versioning, Guardrails, Execution Runs, and Observability."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import (
    AgentExecutionMode,
    AgentRunStatus,
    GuardrailAction,
)


class AgentConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Mutable root container for an AI Agent's settings and published status."""
    __tablename__ = "agent_configs"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(
        String(50),
        default=AgentExecutionMode.AUTONOMOUS.value,
        server_default=text("'autonomous'"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    current_version_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    versions: Mapped[List["AgentVersion"]] = relationship(
        "AgentVersion", back_populates="agent_config", cascade="all, delete-orphan", foreign_keys="AgentVersion.agent_config_id"
    )
    guardrails: Mapped[List["AgentGuardrail"]] = relationship(
        "AgentGuardrail", back_populates="agent_config", cascade="all, delete-orphan"
    )
    tools: Mapped[List["AgentTool"]] = relationship(
        "AgentTool", back_populates="agent_config", cascade="all, delete-orphan"
    )
    knowledge_bases: Mapped[List["AgentKnowledgeBase"]] = relationship(
        "AgentKnowledgeBase", back_populates="agent_config", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_agent_name"),
    )


class AgentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Immutable snapshot of an Agent's prompt, model, parameters, and tool bindings."""
    __tablename__ = "agent_versions"

    agent_config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    temperature: Mapped[float] = mapped_column(
        Float, default=0.7, server_default=text("0.7"), nullable=False
    )
    max_tokens: Mapped[int] = mapped_column(
        Integer, default=1024, server_default=text("1024"), nullable=False
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    agent_config: Mapped["AgentConfig"] = relationship(
        "AgentConfig", back_populates="versions", foreign_keys=[agent_config_id]
    )

    __table_args__ = (
        UniqueConstraint("agent_config_id", "version_number", name="uq_agent_version_num"),
    )


class AgentTool(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "agent_tools"

    agent_config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    agent_config: Mapped["AgentConfig"] = relationship("AgentConfig", back_populates="tools")

    __table_args__ = (
        UniqueConstraint("agent_config_id", "tool_id", name="uq_agent_tool"),
    )


class AgentKnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "agent_knowledge_bases"

    agent_config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    agent_config: Mapped["AgentConfig"] = relationship("AgentConfig", back_populates="knowledge_bases")

    __table_args__ = (
        UniqueConstraint("agent_config_id", "knowledge_base_id", name="uq_agent_kb"),
    )


class AgentGuardrail(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Safety and compliance filters (PII redaction, prompt injection defense, topic bounds)."""
    __tablename__ = "agent_guardrails"

    agent_config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern_or_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(
        String(50),
        default=GuardrailAction.BLOCK.value,
        server_default=text("'block'"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    agent_config: Mapped["AgentConfig"] = relationship("AgentConfig", back_populates="guardrails")


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """End-to-end trace of a single AI agent execution invocation."""
    __tablename__ = "agent_runs"

    agent_config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_version_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(50), default="message", nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default=AgentRunStatus.QUEUED.value,
        server_default=text("'queued'"),
        nullable=False,
        index=True,
    )
    input_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    output_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    llm_requests: Mapped[List["LLMRequest"]] = relationship(
        "LLMRequest", back_populates="agent_run", cascade="all, delete-orphan"
    )
    tool_executions: Mapped[List["ToolExecution"]] = relationship(
        "ToolExecution", back_populates="agent_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_agent_runs_org_conv", "organization_id", "conversation_id"),
    )


class LLMRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Individual API request sent to upstream LLM provider within an agent run."""
    __tablename__ = "llm_requests"

    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    agent_run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="llm_requests")
    attempts: Mapped[List["LLMRequestAttempt"]] = relationship(
        "LLMRequestAttempt", back_populates="llm_request", cascade="all, delete-orphan"
    )


class LLMRequestAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Retry attempts for transient network or rate-limit failures."""
    __tablename__ = "llm_request_attempts"

    llm_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    llm_request: Mapped["LLMRequest"] = relationship("LLMRequest", back_populates="attempts")


class ToolExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Trace of tool/function calls executed by AI agents during runs."""
    __tablename__ = "tool_executions"

    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    input_parameters: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    output_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="succeeded", nullable=False)
    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    agent_run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="tool_executions")
