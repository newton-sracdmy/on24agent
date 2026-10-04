"""SQLAlchemy models for Custom Tools and external integrations."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
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


class Tool(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Function-calling tools callable by AI agents (e.g. check_order_status, book_appointment)."""
    __tablename__ = "tools"

    organization_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Null for system-provided built-in tools",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    schema_definition: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
        comment="JSON Schema for function calling arguments",
    )
    execution_type: Mapped[str] = mapped_column(
        String(50), default="http", server_default=text("'http'"), nullable=False
    )
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    headers_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_org_tool_slug"),
    )
