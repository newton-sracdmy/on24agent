"""SQLAlchemy models for WhatsApp Templates, Audience Segments, Broadcast Campaigns, and Delivery Tracking."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import (
    DateTime,
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
    CampaignRecipientStatus,
    CampaignStatus,
    TemplateApprovalStatus,
    TemplateCategory,
)


class MessageTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """WhatsApp Cloud API HSM (Highly Structured Message) template."""
    __tablename__ = "message_templates"

    channel_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("channel_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    category: Mapped[str] = mapped_column(
        String(50),
        default=TemplateCategory.MARKETING.value,
        server_default=text("'marketing'"),
        nullable=False,
    )
    components_json: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
        comment="Header, Body, Footer, and Button component definitions",
    )
    meta_template_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default=TemplateApprovalStatus.DRAFT.value,
        server_default=text("'draft'"),
        nullable=False,
        index=True,
    )
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("channel_account_id", "name", "language", name="uq_channel_template_lang"),
    )


class CampaignSegment(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Audience segment defined by dynamic contact criteria and tags."""
    __tablename__ = "campaign_segments"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    filter_criteria_json: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
        comment="JSON rule tree for matching contacts (e.g. stage, tags, last active)",
    )
    cached_contact_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Campaign(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Broadcast marketing or alert campaign dispatched across channel accounts."""
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("channel_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("message_templates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    segment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("campaign_segments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=CampaignStatus.DRAFT.value,
        server_default=text("'draft'"),
        nullable=False,
        index=True,
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    total_recipients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    read_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(10, 4), default=0.0, nullable=False)

    recipients: Mapped[List["CampaignRecipient"]] = relationship(
        "CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignRecipient(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Individual contact target within a campaign broadcast."""
    __tablename__ = "campaign_recipients"

    campaign_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=CampaignRecipientStatus.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="recipients")

    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_recipient"),
    )
