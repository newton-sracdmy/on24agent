"""SQLAlchemy models for Channel integrations and accounts."""

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
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import CapabilityType, ChannelAccountStatus, ChannelType


class Channel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """System-level registry of supported communication channels."""
    __tablename__ = "channels"

    type: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    accounts: Mapped[List["ChannelAccount"]] = relationship(
        "ChannelAccount", back_populates="channel", cascade="all, delete-orphan"
    )


class ChannelAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """Tenant-specific connected channel account (e.g. WhatsApp Business account, Telegram bot)."""
    __tablename__ = "channel_accounts"

    channel_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_identifier: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Phone number ID, Bot token username, or Page ID"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=ChannelAccountStatus.CONNECTED.value,
        server_default=text("'connected'"),
        nullable=False,
    )
    encrypted_credentials: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Fernet-encrypted API tokens, app secrets, or private keys"
    )
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    settings: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    channel: Mapped["Channel"] = relationship("Channel", back_populates="accounts")
    capabilities: Mapped[List["ChannelAccountCapability"]] = relationship(
        "ChannelAccountCapability", back_populates="channel_account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "channel_id", "account_identifier", name="uq_org_channel_account"),
        Index("ix_channel_accounts_org_status", "organization_id", "status"),
    )


class ChannelAccountCapability(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Specific capabilities enabled on a tenant channel account."""
    __tablename__ = "channel_account_capabilities"

    channel_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("channel_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    configuration: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    channel_account: Mapped["ChannelAccount"] = relationship(
        "ChannelAccount", back_populates="capabilities"
    )

    __table_args__ = (
        UniqueConstraint("channel_account_id", "capability", name="uq_channel_capability"),
    )
