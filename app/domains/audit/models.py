"""SQLAlchemy models for Audit Logs, Security Events, API Keys, and Transactional Outbox."""

from datetime import datetime, timezone
from typing import Optional
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
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import AuditAction, OutboxEventStatus, SecurityEventType


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Immutable audit trail of state changes and administrative operations."""
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changes_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_org_resource_time", "organization_id", "resource_type", "created_at"),
    )


class SecurityEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Detection records of suspicious requests, prompt injection, or brute-force behavior."""
    __tablename__ = "security_events"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)  # low, medium, high, critical
    details_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)


class LoginAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Security tracking for rate-limiting and account lockout prevention."""
    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_successful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class APIKey(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Workspace developer API keys for programmatic headless integration."""
    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes_json: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class OutboxEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Transactional outbox ensuring atomic persistence and reliable messaging."""
    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=OutboxEventStatus.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_outbox_status_scheduled", "status", "scheduled_at"),
    )


class IdempotencyKey(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Deduplication cache preventing duplicate mutations upon network retries."""
    __tablename__ = "idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_path: Mapped[str] = mapped_column(String(255), nullable=False)
    request_params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_org_idempotency_key"),
    )
