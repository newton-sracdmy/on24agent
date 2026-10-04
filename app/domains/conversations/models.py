"""SQLAlchemy models for Unified Inbox, Messages, Teams, SLAs, Routing, and CSAT."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import (
    ConversationPriority,
    ConversationStatus,
    MessageContentType,
    MessageDeliveryStatus,
    MessageSenderType,
    RoutingStrategy,
    SLABreachStatus,
    SLAPriorityTier,
)


class Team(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Departmental or skill-based teams (e.g. Sales, Tier 2 Support, Arabic Voice Ops)."""
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    members: Mapped[List["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_team_name"),
    )


class TeamMember(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "team_members"

    team_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_team_lead: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )


class BusinessHours(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Working schedules used for SLA calculation and out-of-hours automation."""
    __tablename__ = "business_hours"

    name: Mapped[str] = mapped_column(String(100), default="Default Hours", nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    schedule_json: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{\"monday\": {\"start\": \"09:00\", \"end\": \"18:00\"}}'::jsonb"),
        nullable=False,
    )
    holidays_json: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )


class SLAPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Service Level Agreement targets for first response and complete resolution."""
    __tablename__ = "sla_policies"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    priority_tier: Mapped[str] = mapped_column(
        String(50),
        default=SLAPriorityTier.NORMAL.value,
        server_default=text("'normal'"),
        nullable=False,
    )
    first_response_time_seconds: Mapped[int] = mapped_column(
        Integer, default=900, nullable=False, comment="e.g. 15 minutes = 900s"
    )
    resolution_time_seconds: Mapped[int] = mapped_column(
        Integer, default=14400, nullable=False, comment="e.g. 4 hours = 14400s"
    )
    business_hours_only: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    escalation_rule_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class RoutingRule(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Automated conversation routing logic (round-robin, skill-based, AI-first)."""
    __tablename__ = "routing_rules"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    conditions_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(
        String(50),
        default=RoutingStrategy.AI_FIRST.value,
        server_default=text("'ai_first'"),
        nullable=False,
    )
    target_team_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """Omnichannel conversation thread aggregating messages across any channel."""
    __tablename__ = "conversations"

    contact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("channel_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_agent_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True, comment="AI Bot ID if handled by AI"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=ConversationStatus.OPEN.value,
        server_default=text("'open'"),
        nullable=False,
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(50),
        default=ConversationPriority.MEDIUM.value,
        server_default=text("'medium'"),
        nullable=False,
    )
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    service_window_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="WhatsApp 24h customer care window deadline",
    )
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    sla_policy_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sla_policies.id", ondelete="SET NULL"), nullable=True
    )
    sla_breach_status: Mapped[str] = mapped_column(
        String(50),
        default=SLABreachStatus.WITHIN_SLA.value,
        server_default=text("'within_sla'"),
        nullable=False,
        index=True,
    )
    sla_first_response_breached: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    sla_resolution_breached: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True,
    )
    unread_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)

    contact: Mapped["Contact"] = relationship("Contact")
    channel_account: Mapped["ChannelAccount"] = relationship("ChannelAccount")
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_conversations_org_status_last_msg", "organization_id", "status", "last_message_at"),
        Index("ix_conversations_org_assigned", "organization_id", "assigned_user_id"),
    )


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Inbound and outbound messages with attachments and delivery receipts."""
    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sender_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    content_type: Mapped[str] = mapped_column(
        String(50),
        default=MessageContentType.TEXT.value,
        server_default=text("'text'"),
        nullable=False,
    )
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    delivery_status: Mapped[str] = mapped_column(
        String(50),
        default=MessageDeliveryStatus.SENT.value,
        server_default=text("'sent'"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True, comment="Channel ID (e.g. wamid.HBgL...)"
    )
    reply_to_message_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    attachments: Mapped[List["MessageAttachment"]] = relationship(
        "MessageAttachment", back_populates="message", cascade="all, delete-orphan"
    )
    reactions: Mapped[List["MessageReaction"]] = relationship(
        "MessageReaction", back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )


class MessageAttachment(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "message_attachments"

    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    message: Mapped["Message"] = relationship("Message", back_populates="attachments")


class MessageReaction(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "message_reactions"

    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    contact_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reaction_emoji: Mapped[str] = mapped_column(String(10), nullable=False)

    message: Mapped["Message"] = relationship("Message", back_populates="reactions")


class CannedResponse(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Pre-written message templates and quick replies for live human agents."""
    __tablename__ = "canned_responses"

    shortcut_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    attachments_json: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    team_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "shortcut_code", name="uq_org_canned_shortcut"),
    )


class SatisfactionRating(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """CSAT survey response collected upon conversation resolution."""
    __tablename__ = "satisfaction_ratings"

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    contact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating_score: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1 to 5 stars"
    )
    feedback_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    survey_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """In-app alert for agents (e.g. SLA breach warning, assignment, new message)."""
    __tablename__ = "notifications"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
    )
