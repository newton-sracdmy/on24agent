"""SQLAlchemy models for Contacts, CRM, Identities, Tags, and Activity Timeline."""

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
from app.constants import ContactEventType, ContactLifecycleStage, IdentityType


class Contact(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """Core CRM contact profile representing a customer across all communication channels."""
    __tablename__ = "contacts"

    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    lifecycle_stage: Mapped[str] = mapped_column(
        String(50),
        default=ContactLifecycleStage.LEAD.value,
        server_default=text("'lead'"),
        nullable=False,
    )
    custom_attributes: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    identities: Mapped[List["ContactIdentity"]] = relationship(
        "ContactIdentity", back_populates="contact", cascade="all, delete-orphan"
    )
    tags: Mapped[List["ContactTag"]] = relationship(
        "ContactTag", back_populates="contact", cascade="all, delete-orphan"
    )
    events: Mapped[List["ContactEvent"]] = relationship(
        "ContactEvent", back_populates="contact", cascade="all, delete-orphan"
    )
    notes: Mapped[List["ContactNote"]] = relationship(
        "ContactNote", back_populates="contact", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_contacts_org_phone", "organization_id", "phone_number"),
        Index("ix_contacts_org_email", "organization_id", "email"),
        Index("ix_contacts_org_stage", "organization_id", "lifecycle_stage"),
    )


class ContactIdentity(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Channel-specific identity mapping (e.g. WhatsApp MSISDN, Telegram User ID)."""
    __tablename__ = "contact_identities"

    contact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    contact: Mapped["Contact"] = relationship("Contact", back_populates="identities")

    __table_args__ = (
        UniqueConstraint("organization_id", "identity_type", "identifier_value", name="uq_org_identity"),
    )


class Tag(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Tags for categorizing contacts and conversations."""
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color_hex: Mapped[str] = mapped_column(
        String(7), default="#6B7280", server_default=text("'#6B7280'"), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_tag_name"),
    )


class ContactTag(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "contact_tags"

    contact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    contact: Mapped["Contact"] = relationship("Contact", back_populates="tags")
    tag: Mapped["Tag"] = relationship("Tag")

    __table_args__ = (
        UniqueConstraint("contact_id", "tag_id", name="uq_contact_tag"),
    )


class CustomField(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Custom attribute definitions for contacts."""
    __tablename__ = "custom_fields"

    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(50), nullable=False)  # text, number, date, bool, select
    options: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "field_key", name="uq_org_custom_field_key"),
    )


class ContactEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Activity timeline tracking customer events across interactions."""
    __tablename__ = "contact_events"

    contact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(50), default="system", server_default=text("'system'"), nullable=False
    )
    event_data: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    contact: Mapped["Contact"] = relationship("Contact", back_populates="events")

    __table_args__ = (
        Index("ix_contact_events_org_contact_time", "organization_id", "contact_id", "created_at"),
    )


class ContactNote(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Internal agent notes on contact profiles."""
    __tablename__ = "contact_notes"

    contact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    contact: Mapped["Contact"] = relationship("Contact", back_populates="notes")

    __table_args__ = (
        Index("ix_contact_notes_org_contact", "organization_id", "contact_id"),
    )
