"""SQLAlchemy models for External App Integrations (Shopify, CRM, ERP)."""

from datetime import datetime
from typing import List, Optional
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


class Integration(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Connected external SaaS integration (e.g. Shopify, Salesforce, HubSpot)."""
    __tablename__ = "integrations"

    app_slug: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="connected", server_default=text("'connected'"), nullable=False
    )
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    actions: Mapped[List["IntegrationAction"]] = relationship(
        "IntegrationAction", back_populates="integration", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "app_slug", name="uq_org_integration_app"),
    )


class IntegrationAction(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "integration_actions"

    integration_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_key: Mapped[str] = mapped_column(String(100), nullable=False)
    http_method: Mapped[str] = mapped_column(String(10), default="POST", nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    integration: Mapped["Integration"] = relationship("Integration", back_populates="actions")


class IntegrationEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "integration_events"

    integration_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="processed", nullable=False)
