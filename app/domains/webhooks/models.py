"""SQLAlchemy models for Outbound Webhook Subscriptions, Delivery Retries, and Event Types."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
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
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class WebhookEventType(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """System-level catalog of available webhook events (e.g. message.created, conversation.resolved)."""
    __tablename__ = "webhook_event_types"

    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class WebhookEndpoint(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Subscriber URL registered by tenant to receive automated notifications."""
    __tablename__ = "webhook_endpoints"

    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)

    deliveries: Mapped[List["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="endpoint", cascade="all, delete-orphan"
    )


class WebhookEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Fired domain event ready for dispatch to subscriber webhooks."""
    __tablename__ = "webhook_events"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    deliveries: Mapped[List["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="event", cascade="all, delete-orphan"
    )


class WebhookDelivery(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Individual HTTP POST dispatch attempt with status and exponential retry schedule."""
    __tablename__ = "webhook_deliveries"

    webhook_event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("webhook_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", server_default=text("'pending'"), nullable=False
    )
    scheduled_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["WebhookEvent"] = relationship("WebhookEvent", back_populates="deliveries")
    endpoint: Mapped["WebhookEndpoint"] = relationship("WebhookEndpoint", back_populates="deliveries")

    __table_args__ = (
        Index("ix_deliveries_status_retry", "status", "scheduled_retry_at"),
    )
