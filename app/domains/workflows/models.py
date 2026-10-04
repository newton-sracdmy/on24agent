"""SQLAlchemy models for Workflow Automation Studio, Directed Acyclic Graph (DAG) Nodes, and Execution Engine."""

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
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import (
    Base,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import (
    WorkflowExecutionStatus,
    WorkflowNodeType,
    WorkflowTriggerType,
)


class Workflow(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """Visual automation flow definition container."""
    __tablename__ = "workflows"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    current_version_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    versions: Mapped[List["WorkflowVersion"]] = relationship(
        "WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan", foreign_keys="WorkflowVersion.workflow_id"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_workflow_name"),
    )


class WorkflowVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Immutable snapshot of a visual automation graph."""
    __tablename__ = "workflow_versions"

    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped["Workflow"] = relationship(
        "Workflow", back_populates="versions", foreign_keys=[workflow_id]
    )
    nodes: Mapped[List["WorkflowNode"]] = relationship(
        "WorkflowNode", back_populates="version", cascade="all, delete-orphan"
    )
    edges: Mapped[List["WorkflowEdge"]] = relationship(
        "WorkflowEdge", back_populates="version", cascade="all, delete-orphan"
    )
    triggers: Mapped[List["WorkflowTrigger"]] = relationship(
        "WorkflowTrigger", back_populates="version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version_num"),
    )


class WorkflowNode(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Single action, condition, or branching node in a workflow graph."""
    __tablename__ = "workflow_nodes"

    workflow_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_key: Mapped[str] = mapped_column(String(50), nullable=False)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    position_x: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position_y: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    version: Mapped["WorkflowVersion"] = relationship("WorkflowVersion", back_populates="nodes")


class WorkflowEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Directed connection between workflow nodes."""
    __tablename__ = "workflow_edges"

    workflow_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_node_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    condition_expression: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edge_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    version: Mapped["WorkflowVersion"] = relationship("WorkflowVersion", back_populates="edges")


class WorkflowTrigger(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Event or schedule that initiates a workflow run."""
    __tablename__ = "workflow_triggers"

    workflow_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_filter_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    cron_expression: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    version: Mapped["WorkflowVersion"] = relationship("WorkflowVersion", back_populates="triggers")


class WorkflowExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Execution state machine instance of an automation run."""
    __tablename__ = "workflow_executions"

    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contact_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=WorkflowExecutionStatus.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )
    context_data_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[List["ExecutionStep"]] = relationship(
        "ExecutionStep", back_populates="execution", cascade="all, delete-orphan"
    )


class ExecutionStep(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Execution trace of an individual node."""
    __tablename__ = "execution_steps"

    workflow_execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_nodes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), default="succeeded", nullable=False)
    input_state_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    output_state_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    execution: Mapped["WorkflowExecution"] = relationship("WorkflowExecution", back_populates="steps")
