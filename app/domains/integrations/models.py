"""SQLAlchemy models for External App Integrations (Shopify, CRM, ERP)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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

    __table_args__ = (
        UniqueConstraint("organization_id", "app_slug", name="uq_org_integration_app"),
    )
