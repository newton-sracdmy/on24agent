"""Common SQLAlchemy base classes, mixins, and UUIDv7 generator.

Follows SQLAlchemy 2.0 declarative style with strict Mapped[] type annotations.
"""

import time
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def generate_uuid7() -> UUID:
    """Generate a UUIDv7 (time-ordered UUID) per RFC 9562 draft.

    Combines 48 bits of millisecond timestamp with 74 bits of cryptographically
    secure randomness for time-locality in B-tree database indexes.
    """
    timestamp_ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)

    # 48-bit timestamp
    time_high = (timestamp_ms >> 16) & 0xFFFFFFFF
    time_mid = timestamp_ms & 0xFFFF

    # 12-bit rand_a with version 7
    rand_a = int.from_bytes(rand_bytes[:2], byteorder="big") & 0x0FFF
    version_and_rand = 0x7000 | rand_a

    # 62-bit rand_b with variant 2 (RFC 4122 / 9562)
    rand_b_high = (rand_bytes[2] & 0x3F) | 0x80
    rand_b = (
        (rand_b_high << 56)
        | (rand_bytes[3] << 48)
        | (rand_bytes[4] << 40)
        | (rand_bytes[5] << 32)
        | (rand_bytes[6] << 24)
        | (rand_bytes[7] << 16)
        | (rand_bytes[8] << 8)
        | rand_bytes[9]
    )

    int_uuid = (time_high << 96) | (time_mid << 80) | (version_and_rand << 64) | rand_b
    return UUID(int=int_uuid)


class Base(DeclarativeBase):
    """Declarative root class for all database models."""
    pass


class UUIDPrimaryKeyMixin:
    """Provides a time-ordered UUIDv7 primary key for database index locality."""

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )


class TimestampMixin:
    """Provides UTC creation and modification timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


class SoftDeleteMixin:
    """Enables soft deletion with timestamp and boolean flag."""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None


class TenantMixin:
    """Enforces multi-tenancy by requiring an organization_id foreign key.

    All tenant-owned tables MUST inherit from this mixin.
    """

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class AuditMixin:
    """Tracks the user who created or last modified a record."""

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
